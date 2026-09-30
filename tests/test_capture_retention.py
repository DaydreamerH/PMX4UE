import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

from tools.capture_retention import apply_plan, make_plan, output_path, remove_native_duplicate, sha

TOKEN = 'a'*32


class CaptureRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)/'Test.uproject'
        self.project.write_text('{}')
        self.root = self.project.parent/'Saved/PMX4UE/Character'
        self.preview = self.root/'v1/material_previews/old'
        self.captures = self.preview/('captures_' + TOKEN)
        self.captures.mkdir(parents=True)
        self.images = []
        for n in range(2):
            path = self.captures/f'PMX4UE_{TOKEN}_{n:04d}.png'
            path.write_bytes(b'synthetic capture ' + bytes([n]))
            self.images.append(path)
        self.report = self.preview/'material_preview.json'
        self.report.write_text(json.dumps(dict(schema='pmx4ue.material-captures.v1', captures=[
            dict(image=dict(path=str(p), sha256=sha(p))) for p in self.images])))
        self.policy = dict(schema='pmx4ue.capture-retention.v1', project=str(self.project),
                           artifact_root=str(self.root), protected_paths=[], external_reference_roots=[],
                           retired_records=[dict(path=str(self.report), sha256=sha(self.report),
                                                 reason='Rejected candidate replaced by reviewed v2')])

    def save_plan(self, plan=None):
        plan = make_plan(self.policy) if plan is None else plan
        path = output_path(self.root/'_capture_retention/plan.json', self.root)
        path.write_text(json.dumps(plan))
        approval = path.with_name('approval.json')
        approval.write_text(json.dumps(dict(plan_sha256=sha(path), approved_by='fixture user',
                                            authorization_basis='synthetic test approval')))
        return path, approval, path.with_name('receipt.json')

    def test_native_duplicate_is_removed_only_after_verified_retained_copy(self):
        native = self.project.parent/'Saved/PMX4UECaptures'/self.images[0].name
        native.parent.mkdir()
        native.write_bytes(self.images[0].read_bytes())
        result = remove_native_duplicate(self.project.parent, native, self.images[0], TOKEN, sha(native))
        self.assertEqual(result['status'], 'removed_verified_native_duplicate')
        self.assertFalse(native.exists())
        self.assertTrue(self.images[0].exists())

    def test_native_mismatch_or_wrong_scope_never_deletes(self):
        native = self.project.parent/'Saved/PMX4UECaptures'/self.images[0].name
        native.parent.mkdir()
        native.write_bytes(b'different')
        for token, retained in ((TOKEN, self.images[0]), ('b'*32, self.images[0]),
                                (TOKEN, self.project)):
            with self.assertRaises(ValueError):
                remove_native_duplicate(self.project.parent, native, retained, token, sha(native))
        self.assertTrue(native.exists())
        native.write_bytes(self.images[0].read_bytes())
        with patch.object(Path, 'unlink', side_effect=PermissionError('fixture busy')):
            result = remove_native_duplicate(self.project.parent, native, self.images[0], TOKEN, sha(native))
        self.assertEqual(result['status'], 'duplicate_retained_cleanup_failed')
        self.assertTrue(native.exists())

    def test_plan_is_read_only_and_protects_current_references_and_pins(self):
        active = self.root/'material-review.md'
        active.write_text('Current selected image: ' + str(self.images[0]))
        self.policy['protected_paths'] = [str(self.images[1])]
        plan = make_plan(self.policy)
        self.assertEqual(plan['candidates'], [])
        self.assertEqual(len(plan['protected']), 2)
        self.assertTrue(all(p.exists() for p in self.images))
        self.assertIn(str(active), plan['reference_sha256'])

    def test_report_references_protect_full_matrix_including_external_records(self):
        review = self.project.parent/'reviews'
        review.mkdir()
        (review/'delivery.json').write_text(json.dumps(dict(report=str(self.report), sha256=sha(self.report))))
        self.policy['external_reference_roots'] = [str(review)]
        self.assertEqual(len(make_plan(self.policy)['protected']), 2)

    def test_runner_record_must_also_be_retired_but_final_delivery_cannot_be(self):
        run = self.root/'v1/runs/old.json'
        run.parent.mkdir()
        run.write_text(json.dumps(dict(stage='material-preview', outputs=[str(self.report)],
                                      capture_sha256={str(p): sha(p) for p in self.images})))
        self.assertEqual(make_plan(self.policy)['candidates'], [])
        self.policy['retired_records'].append(dict(path=str(run), sha256=sha(run), reason='Same obsolete preview'))
        self.assertEqual(len(make_plan(self.policy)['candidates']), 2)
        delivery = self.root/'delivery.json'
        delivery.write_text('{"schema":"pmx4ue.delivery.v2"}')
        self.policy['retired_records'].append(dict(path=str(delivery), sha256=sha(delivery), reason='Cannot exempt delivery'))
        with self.assertRaises(ValueError):
            make_plan(self.policy)

    def test_outside_root_changed_hash_lock_and_missing_reference_root_rejected(self):
        for update in (dict(artifact_root=str(self.root.parent)),
                       dict(external_reference_roots=[str(self.root/'missing')])):
            with self.assertRaises(ValueError):
                make_plan({**self.policy, **update})
        bad = copy.deepcopy(self.policy)
        bad['retired_records'][0]['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            make_plan(bad)
        self.images[0].write_bytes(b'changed')
        with self.assertRaises(ValueError):
            make_plan(self.policy)
        lock = self.root.parent/'.agent.lock'
        lock.write_text('{}')
        with self.assertRaises(ValueError):
            make_plan(self.policy)

    def test_approved_exact_plan_deletes_only_managed_images_and_keeps_audit(self):
        plan, approval, receipt = self.save_plan()
        unrelated = self.root/'source-texture.png'
        unrelated.write_bytes(b'not a capture')
        result = apply_plan(plan, approval, receipt)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['deleted']), 2)
        self.assertFalse(any(p.exists() for p in self.images))
        self.assertTrue(self.report.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(receipt.exists())
        self.assertFalse((self.root.parent/'.agent.lock').exists())

    def test_approval_and_new_reference_or_candidate_changes_stop_deletion(self):
        plan, approval, receipt = self.save_plan()
        original = approval.read_text()
        approval.write_text('{}')
        with self.assertRaises(ValueError):
            apply_plan(plan, approval, receipt)
        approval.write_text(original)
        review = self.root/'new-review.md'
        review.write_text('Preserve ' + str(self.images[0]))
        with self.assertRaises(ValueError):
            apply_plan(plan, approval, receipt)
        self.assertTrue(all(p.exists() for p in self.images))
        self.assertFalse(receipt.exists())
        with self.assertRaises(ValueError):
            output_path(self.root.parent/'unsafe.json', self.root)

    def test_pinned_runner_record_remains_a_live_reference(self):
        run = self.root/'v1/runs/old.json'
        run.parent.mkdir()
        run.write_text(json.dumps(dict(stage='material-preview', outputs=[str(self.report)],
                                      capture_sha256={str(p): sha(p) for p in self.images})))
        self.policy['retired_records'].append(dict(path=str(run), sha256=sha(run), reason='Same preview'))
        self.policy['protected_paths'] = [str(run)]
        self.assertEqual(make_plan(self.policy)['candidates'], [])

    def test_partial_failure_is_journalled_and_stops_without_touching_reports(self):
        plan, approval, receipt = self.save_plan()
        original = Path.unlink
        def fail_second(path, *args, **kwargs):
            if path == self.images[1]:
                raise PermissionError('fixture busy screenshot')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_second):
            result = apply_plan(plan, approval, receipt)
        self.assertEqual(result['status'], 'partial_failure')
        self.assertEqual(len(result['deleted']), 1)
        self.assertTrue(self.images[1].exists())
        self.assertTrue(self.report.exists())
        self.assertEqual(json.loads(receipt.read_text())['status'], 'partial_failure')

    def test_cli_plan_and_approval_apply_use_exact_outputs(self):
        policy = output_path(self.root/'_capture_retention/policy.json', self.root)
        policy.write_text(json.dumps(self.policy))
        plan = policy.with_name('cli-plan.json')
        tool = Path(__file__).resolve().parents[1]/'tools/capture_retention.py'
        command = [sys.executable, '-X', 'utf8', str(tool)]
        result = subprocess.run(command + ['plan', '--policy', str(policy), '--output', str(plan)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(plan.read_text())['candidates']), 2)
        approval = policy.with_name('cli-approval.json')
        approval.write_text(json.dumps(dict(plan_sha256=sha(plan), approved_by='fixture user',
                                            authorization_basis='synthetic test only')))
        receipt = policy.with_name('cli-receipt.json')
        result = subprocess.run(command + ['apply', '--plan', str(plan), '--approval', str(approval),
                                           '--receipt', str(receipt)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(receipt.read_text())['status'], 'completed')

    def test_reparse_or_source_like_image_is_not_a_cleanup_candidate(self):
        original = Path.is_symlink
        def linked(path):
            return path == self.captures or original(path)
        with patch.object(Path, 'is_symlink', linked), self.assertRaises(ValueError):
            make_plan(self.policy)
        source = self.root/'face-texture.png'
        source.write_bytes(b'source-like image')
        self.report.write_text(json.dumps(dict(schema='pmx4ue.material-captures.v1', captures=[
            dict(image=dict(path=str(source), sha256=sha(source)))])))
        self.policy['retired_records'][0]['sha256'] = sha(self.report)
        with self.assertRaises(ValueError):
            make_plan(self.policy)
        self.assertTrue(source.exists())


if __name__ == '__main__':
    unittest.main()
