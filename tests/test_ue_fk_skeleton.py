"""Clean hierarchy is distinct from keeping helper bones or naming IK endpoints."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from skeleton_plan import build_plan, verify_postconditions
from test_skeleton_plan import tololo_pattern
from test_shoulder_cleanup import simulate
import test_workflow_readiness as readiness
from tools.skeleton_gate import digest, verify


def fixture():
    audit, roles = tololo_pattern()
    audit['control_facts'] = {}
    for side in ('L', 'R'):
        audit['control_facts']['ShoulderP_'+side] = dict(neutral=True, append=None)
        audit['control_facts']['ShoulderC_'+side] = dict(neutral=True,
            append=dict(source='ShoulderP_'+side, rotation=True, translation=False, factor=-1.0))
        audit['bone_references'].append(dict(kind='pmx_append', owner='ShoulderC_'+side, target='ShoulderP_'+side))
    return audit, roles


class UeFkSkeletonTests(unittest.TestCase):
    def test_compensation_pair_and_weighted_twists_can_leave_main_path_without_deletion(self):
        audit, roles = fixture()
        plan = build_plan(audit, roles, simplify_shoulders=True, shoulder_strategy='branch_helpers')
        self.assertEqual(plan['status'], 'ready', plan['blockers'])
        self.assertTrue(all(op['op'] == 'reparent' for op in plan['operations']))
        parents = simulate(audit, plan)
        self.assertEqual(len(parents), len(audit['bones']))
        for side in ('L', 'R'):
            self.assertEqual(parents['Shoulder_'+side], 'UpperBody2')
            self.assertEqual(parents['Arm_'+side], 'Shoulder_'+side)
            self.assertEqual(parents['Elbow_'+side], 'Arm_'+side)
            self.assertEqual(parents['Wrist_'+side], 'Elbow_'+side)
            self.assertEqual(parents['ArmTwist_'+side], 'Arm_'+side)
            self.assertEqual(parents['_dummy_ShoulderC_'+side], 'ShoulderP_'+side)
        verify_postconditions(plan, parents)
        del parents['ShoulderC_R']
        with self.assertRaisesRegex(ValueError, 'missing retained'):
            verify_postconditions(plan, parents)

    def test_branch_mode_checks_unknown_compensation_and_source_pose(self):
        for key in ('neutral', 'append', 'action'):
            audit, roles = fixture()
            if key == 'neutral':
                audit['control_facts']['ShoulderP_L']['neutral'] = False
            elif key == 'append':
                audit['control_facts']['ShoulderC_L']['append']['factor'] = .5
            else:
                audit['bone_references'].append(dict(kind='action_curve', target='ShoulderP_L'))
            plan = build_plan(audit, roles, simplify_shoulders=True, shoulder_strategy='branch_helpers')
            self.assertEqual(plan['status'], 'blocked')
            self.assertEqual(plan['operations'], [])

    def test_branch_does_not_require_deletion_attachment_map(self):
        audit, roles = fixture()
        for side in ('left', 'right'):
            roles[side]['rehome_before_delete'] = {}
        plan = build_plan(audit, roles, simplify_shoulders=True, shoulder_strategy='branch_helpers')
        self.assertEqual(plan['status'], 'ready', plan['blockers'])

    def test_new_clean_goal_rejects_preserve_instead_of_actual_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, audit, decision = readiness.ReadinessTests().fixture(root)
            audit['bones'].append(dict(name='twist', parent='leftupper_arm', weight=dict(sum=10)))
            next(b for b in audit['bones'] if b['name'] == 'leftelbow')['parent'] = 'twist'
            config['skeleton']['goal'] = 'clean_ue_fk'
            (root/'skeleton_audit.json').write_text(json.dumps(audit))
            decision['audit_sha256'] = digest(root/'skeleton_audit.json')
            (root/'skeleton_decision.json').write_text(json.dumps(decision))
            with self.assertRaisesRegex(ValueError, 'actual hierarchy edits'):
                verify(config, root)
