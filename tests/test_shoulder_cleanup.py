import copy
import json
from pathlib import Path
import tempfile
import unittest

from skeleton_plan import build_plan, verify_postconditions
from skeleton_review import analyze_audit
from test_skeleton_plan import tololo_pattern, bone
import test_workflow_readiness as readiness
from tools.skeleton_gate import verify, verify_import, digest


def simulate(audit, plan):
    parents = {b['name']: b.get('parent') for b in audit['bones']}
    for op in plan['operations']:
        assert parents[op['bone']] == op['expected_parent']
        if op['op'] == 'reparent':
            parents[op['bone']] = op['new_parent']
        else:
            assert op['bone'] not in parents.values()
            del parents[op['bone']]
    return parents


class ShoulderCleanupTests(unittest.TestCase):
    def test_missing_postconditions_cannot_be_treated_as_verified(self):
        with self.assertRaisesRegex(ValueError, 'regenerate the plan'):
            verify_postconditions({}, {})

    def test_import_requires_actual_deleted_bones_and_parent_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c, _, _ = readiness.ReadinessTests().fixture(root)
            c['skeleton']['simplify_shoulders'] = True
            audit, roles = tololo_pattern()
            plan = build_plan(audit, roles, simplify_shoulders=True)
            parents = simulate(audit, plan)
            (root/'skeleton_plan.json').write_text(json.dumps(plan))
            fbx = root/'Model.fbx'
            fbx.write_bytes(b'fixture')
            build = root/'ue_build_report.json'
            (root/'runs').mkdir()
            structure = dict(mesh='/Game/Fixture.Fixture', final_bone_parents=parents,
                             postconditions=verify_postconditions(plan, parents))
            def write_build():
                build.write_text(json.dumps(dict(skeletal_mesh='/Game/Fixture.Fixture', skeleton_structure=structure)))
                (root/'runs/1_ue-build.json').write_text(json.dumps(dict(status='executed_needs_review',
                    input_sha256={str(fbx):digest(fbx)}, output_sha256={str(build):digest(build)})))
            write_build()
            verify_import(c, root, 'retarget-pose')
            parents['ShoulderP_L'] = 'UpperBody2'
            write_build()
            with self.assertRaisesRegex(ValueError, 'residual bones'):
                verify_import(c, root, 'retarget-pose')
            del parents['ShoulderP_L']
            parents['Arm_L'] = 'UpperBody2'
            write_build()
            with self.assertRaisesRegex(ValueError, 'wrong parents'):
                verify_import(c, root, 'retarget-pose')

    def test_direct_chain_with_residual_helpers_is_not_finished(self):
        audit, roles = tololo_pattern()
        for b in audit['bones']:
            if b['name'] in ('Shoulder_L', 'Shoulder_R'):
                b['parent'] = 'UpperBody2'
            if b['name'] in ('Arm_L', 'Arm_R'):
                b['parent'] = 'Shoulder_' + b['name'][-1]
        review = analyze_audit(audit, roles)
        self.assertEqual(review['shoulders']['left']['status'], 'residual_shoulder_helpers')
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan['status'], 'ready', plan['blockers'])
        self.assertEqual(set(plan['postconditions']['absent']), {'ShoulderP_L', 'ShoulderC_L', 'ShoulderP_R', 'ShoulderC_R'})
        parents = simulate(audit, plan)
        verify_postconditions(plan, parents)
        parents['ShoulderP_L'] = 'UpperBody2'
        with self.assertRaisesRegex(ValueError, 'residual bones'):
            verify_postconditions(plan, parents)

    def test_partially_simplified_chain_and_explicit_dummy_removal(self):
        audit, roles = tololo_pattern()
        for side, suffix in (('left', 'L'), ('right', 'R')):
            roles[side]['shoulder_helpers'] = ['_dummy_ShoulderC_' + suffix]
            roles[side]['rehome_before_delete'] = {}
            next(b for b in audit['bones'] if b['name'] == 'Shoulder_' + suffix)['parent'] = 'UpperBody2'
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan['status'], 'ready', plan['blockers'])
        self.assertEqual(len(plan['postconditions']['absent']), 6)
        verify_postconditions(plan, simulate(audit, plan))

    def test_weighted_referenced_helper_and_accessory_safety(self):
        audit, roles = tololo_pattern()
        for issue in ('weight', 'constraint', 'attachment'):
            a = copy.deepcopy(audit)
            if issue == 'weight':
                next(b for b in a['bones'] if b['name'] == 'ShoulderC_R')['weight']['sum'] = .1
            elif issue == 'constraint':
                a['bone_references'].append(dict(kind='constraint', target='ShoulderP_L'))
            else:
                a['bones'].append(bone('Badge', 'ShoulderC_R', 1))
            self.assertEqual(build_plan(a, roles, simplify_shoulders=True)['status'], 'blocked')
        audit['bones'].append(bone('Badge', 'ShoulderC_R', 1))
        roles['right']['rehome_before_delete']['Badge'] = 'Shoulder_R'
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(simulate(audit, plan)['Badge'], 'Shoulder_R')

    def test_residual_helpers_cannot_pass_preserve_without_per_bone_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c, audit, decision = readiness.ReadinessTests().fixture(root)
            audit['bones'].append(bone('ShoulderP_L', 'Torso'))
            (root/'skeleton_audit.json').write_text(json.dumps(audit))
            decision['audit_sha256'] = digest(root/'skeleton_audit.json')
            (root/'skeleton_decision.json').write_text(json.dumps(decision))
            with self.assertRaisesRegex(ValueError, 'evidence or optimize'):
                verify(c, root)
            evidence = root/'evidence.json'
            evidence.write_text('{}')
            decision['shoulders']['preservation_evidence'] = [dict(path=str(evidence), sha256=digest(evidence))]
            (root/'skeleton_decision.json').write_text(json.dumps(decision))
            with self.assertRaisesRegex(ValueError, 'every retained shoulder helper'):
                verify(c, root)

    def test_bind_risk_record_cannot_pass_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c, _, _ = readiness.ReadinessTests().fixture(root)
            fbx = root/'Model.fbx'
            fbx.write_bytes(b'fixture')
            build = root/'ue_build_report.json'
            build.write_text(json.dumps(dict(skeletal_mesh='/Game/Fixture.Fixture')))
            (root/'runs').mkdir()
            (root/'runs/1_ue-build.json').write_text(json.dumps(dict(status='executed_with_import_risks',
                input_sha256={str(fbx):digest(fbx)}, output_sha256={str(build):digest(build)})))
            with self.assertRaisesRegex(ValueError, 'no build record'):
                verify_import(c, root, 'retarget-pose')
