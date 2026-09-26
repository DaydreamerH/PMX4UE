from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skeleton_review import analyze_audit


def bone(name, parent=None, weight=0):
    return {"name": name, "parent": parent, "weight": {"sum": weight}}


class SkeletonReviewTests(unittest.TestCase):
    def test_direct_chain_is_only_candidate_not_animation_pass(self):
        bones = [bone("UpperBody2")]
        for side in ("L", "R"):
            bones.extend([
                bone(f"Shoulder_{side}", "UpperBody2", 1),
                bone(f"Arm_{side}", f"Shoulder_{side}", 1),
                bone(f"Elbow_{side}", f"Arm_{side}", 1),
                bone(f"Wrist_{side}", f"Elbow_{side}", 1),
            ])
        report = analyze_audit({"bones": bones})
        self.assertEqual(report["retarget_structure"], "direct_chain_candidate")
        self.assertFalse(report["animation_validated"])

    def test_weighted_twist_and_shoulder_helper_must_not_be_removed(self):
        bones = [bone("UpperBody2")]
        for side in ("L", "R"):
            bones.extend([
                bone(f"ShoulderP_{side}", "UpperBody2", 1),
                bone(f"Shoulder_{side}", f"ShoulderP_{side}", 1),
                bone(f"ShoulderC_{side}", f"Shoulder_{side}"),
                bone(f"Arm_{side}", f"ShoulderC_{side}", 1),
                bone(f"ArmTwist_{side}", f"Arm_{side}", 1),
                bone(f"Elbow_{side}", f"ArmTwist_{side}", 1),
                bone(f"Wrist_{side}", f"Elbow_{side}", 1),
            ])
        report = analyze_audit({"bones": bones})
        self.assertEqual(report["retarget_structure"], "manual_review_required")
        self.assertIn("ShoulderP_L", report["shoulders"]["left"]["weighted_helpers"])
        self.assertIn("ArmTwist_L", report["arms"]["left"]["main_chain"])

    def test_unknown_names_are_manual_not_assumed_safe(self):
        report = analyze_audit({"bones": [bone("上半身"), bone("左腕", "上半身", 1)]})
        self.assertEqual(report["retarget_structure"], "manual_review_required")
        self.assertTrue(report["issues"])

    def test_importer_metadata_is_not_treated_as_missing_bone(self):
        report = analyze_audit({"bones": [], "unmatched_weight_groups": ["mmd_edge_scale", "LooseWeight"]})
        self.assertEqual(report["ignored_metadata_groups"], ["mmd_edge_scale"])
        self.assertTrue(any("LooseWeight" in issue for issue in report["issues"]))
        self.assertFalse(any("mmd_edge_scale" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
