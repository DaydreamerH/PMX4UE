from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skeleton_ue_mapping import expected_arm_parents, target_chains, variant_has_single_shoulder


class SkeletonUEMappingTests(unittest.TestCase):
    def test_configured_variant_not_substring_controls_shoulder_check(self):
        config = {"skeleton": {"variant": "RigV2", "simplify_shoulders": True}}
        self.assertTrue(variant_has_single_shoulder(config, "RigV2"))
        self.assertFalse(variant_has_single_shoulder(config, "RigV1Shoulder"))
        self.assertIn("Shoulder_L", expected_arm_parents(config, "RigV2"))
        self.assertNotIn("Shoulder_L", expected_arm_parents(config, "RigV1Shoulder"))

    def test_custom_roles_and_spine_override_feed_target_chains(self):
        config = {"skeleton": {
            "variant": "RigV2", "simplify_shoulders": True,
            "roles": {"torso": "躯干", "left": {"shoulder": "左肩", "upper_arm": "左臂", "elbow": "左肘", "wrist": "左手"},
                      "right": {"shoulder": "右肩", "upper_arm": "右臂", "elbow": "右肘", "wrist": "右手"}},
            "retarget": {"target_chains": {"Spine": ["下身", "躯干"]}},
        }}
        chains = target_chains(config, "RigV2")
        self.assertEqual(chains["LeftArm"], ("左臂", "左手"))
        self.assertEqual(chains["RightShoulder"], ("右肩", "右肩"))
        self.assertEqual(chains["Spine"], ("下身", "躯干"))
        self.assertEqual(expected_arm_parents(config, "RigV2")["左臂"], "左肩")

    def test_invalid_chain_override_is_rejected_before_ue(self):
        with self.assertRaises(ValueError):
            target_chains({"skeleton": {"retarget": {"target_chains": {"Spine": ["only_one"]}}}}, "RigV2")

    def test_twist_branch_config_must_be_a_list(self):
        with self.assertRaises(ValueError):
            target_chains({"skeleton": {"roles": {"left": {"upper_twist_branches": "ArmTwist1_L"}}}}, "RigV2")


if __name__ == "__main__":
    unittest.main()
