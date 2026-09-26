from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skeleton_plan import build_plan


def bone(name, parent=None, weight=0, children=()):
    return {"name": name, "parent": parent, "children": list(children), "weight": {"sum": weight}}


def tololo_pattern():
    bones = [bone("UpperBody2", children=("ShoulderP_L", "ShoulderP_R"))]
    roles = {"left": {"rehome_before_delete": {"_dummy_ShoulderC_L": "UpperBody2"}},
             "right": {"rehome_before_delete": {"_dummy_ShoulderC_R": "UpperBody2"}}}
    for side in ("L", "R"):
        bones.extend([
            bone(f"ShoulderP_{side}", "UpperBody2", children=(f"Shoulder_{side}", f"_dummy_ShoulderC_{side}")),
            bone(f"Shoulder_{side}", f"ShoulderP_{side}", 1, (f"ShoulderC_{side}",)),
            bone(f"ShoulderC_{side}", f"Shoulder_{side}", children=(f"Arm_{side}",)),
            bone(f"_dummy_ShoulderC_{side}", f"ShoulderP_{side}"),
            bone(f"Arm_{side}", f"ShoulderC_{side}", 1, (f"ArmTwist_{side}",)),
            bone(f"ArmTwist_{side}", f"Arm_{side}", 1, (f"Elbow_{side}",)),
            bone(f"Elbow_{side}", f"ArmTwist_{side}", 1, (f"HandTwist_{side}",)),
            bone(f"HandTwist_{side}", f"Elbow_{side}", 1, (f"Wrist_{side}",)),
            bone(f"Wrist_{side}", f"HandTwist_{side}", 1),
        ])
    return {"blend": "source.blend", "source_file": {"size": 100, "mtime_ns": 1},
            "bones": bones, "bone_references_checked": True,
            "bone_references": [], "unscanned_actions": []}, roles


def add_leg_pattern(audit):
    specs = {}
    for side in ("L", "R"):
        control = [f"Leg_{side}", f"Knee_{side}", f"Ankle_{side}"]
        deform = [f"LegD_{side}", f"KneeD_{side}", f"AnkleD_{side}"]
        butt, tip = f"Butt_{side}", f"AnkleTip_{side}"
        ik = [f"IKParent_{side}", f"IK_{side}", f"IKTip_{side}"]
        audit["bones"].extend([
            bone(f"Waist_{side}", children=(control[0], deform[0])),
            bone(control[0], f"Waist_{side}", children=(control[1], butt)),
            bone(control[1], control[0], children=(control[2],)),
            bone(control[2], control[1], children=(tip,)),
            bone(deform[0], f"Waist_{side}", 1, (deform[1],)),
            bone(deform[1], deform[0], 1, (deform[2],)),
            bone(deform[2], deform[1], 1),
            bone(butt, control[0], 1), bone(tip, control[2], 1),
            bone(ik[0], children=(ik[1],)),
            bone(ik[1], ik[0], children=(ik[2],)),
            bone(ik[2], ik[1]),
        ])
        specs["left" if side == "L" else "right"] = {
            "control_chain": control, "deform_chain": deform,
            "rehome": {butt: deform[0], tip: deform[2]},
            "remove_helpers": list(reversed(ik)),
        }
    return specs


class SkeletonPlanTests(unittest.TestCase):
    def test_leg_cleanup_keeps_weighted_d_chain_and_rehomes_weighted_children(self):
        audit, roles = tololo_pattern()
        specs = add_leg_pattern(audit)
        plan = build_plan(audit, roles, leg_cleanup=specs)
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        deleted = {op["bone"] for op in plan["operations"] if op["op"] == "delete_unweighted_leaf"}
        self.assertIn("Leg_L", deleted)
        self.assertIn("IKParent_R", deleted)
        self.assertNotIn("LegD_L", deleted)
        self.assertEqual(next(op for op in plan["operations"] if op["bone"] == "Butt_L")["new_parent"], "LegD_L")

    def test_leg_cleanup_blocks_weighted_control_unmapped_child_and_bad_helper_order(self):
        audit, roles = tololo_pattern()
        specs = add_leg_pattern(audit)
        next(b for b in audit["bones"] if b["name"] == "Leg_L")["weight"]["sum"] = 0.1
        self.assertEqual(build_plan(audit, roles, leg_cleanup=specs)["status"], "blocked")
        next(b for b in audit["bones"] if b["name"] == "Leg_L")["weight"]["sum"] = 0
        del specs["left"]["rehome"]["Butt_L"]
        self.assertEqual(build_plan(audit, roles, leg_cleanup=specs)["status"], "blocked")
        specs["left"]["rehome"]["Butt_L"] = "LegD_L"
        specs["left"]["remove_helpers"].reverse()
        self.assertEqual(build_plan(audit, roles, leg_cleanup=specs)["status"], "blocked")

    def test_reviewed_pattern_keeps_weighted_twists_and_removes_only_helpers(self):
        audit, roles = tololo_pattern()
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(len(plan["operations"]), 14)
        self.assertEqual({op["bone"] for op in plan["operations"] if op["op"] == "delete_unweighted_leaf"},
                         {"ShoulderP_L", "ShoulderP_R", "ShoulderC_L", "ShoulderC_R"})
        self.assertFalse(any(op["bone"].startswith(("ArmTwist", "HandTwist")) for op in plan["operations"]))

    def test_weighted_helper_blocks_both_sides(self):
        audit, roles = tololo_pattern()
        next(b for b in audit["bones"] if b["name"] == "ShoulderP_L")["weight"]["sum"] = 0.2
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["operations"], [])

    def test_missing_explicit_extra_child_mapping_blocks(self):
        audit, roles = tololo_pattern()
        roles["left"]["rehome_before_delete"] = {}
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("extra child" in reason for reason in plan["blockers"]))

    def test_unscanned_action_or_reference_blocks_deletion(self):
        audit, roles = tololo_pattern()
        audit["unscanned_actions"] = ["MMDAction"]
        self.assertEqual(build_plan(audit, roles, simplify_shoulders=True)["status"], "blocked")
        audit["unscanned_actions"] = []
        audit["bone_references"] = [{"kind": "constraint", "target": "ShoulderC_R"}]
        self.assertEqual(build_plan(audit, roles, simplify_shoulders=True)["status"], "blocked")

    def test_missing_source_identity_blocks_stale_audit(self):
        audit, roles = tololo_pattern()
        del audit["source_file"]
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("source blend" in reason for reason in plan["blockers"]))

    def test_arm_only_edits_require_reference_scan_and_readable_actions(self):
        audit, roles = tololo_pattern()
        audit["bone_references_checked"] = False
        self.assertEqual(build_plan(audit, roles)["status"], "blocked")
        audit["bone_references_checked"] = True
        audit["unscanned_actions"] = ["LayeredPose"]
        self.assertEqual(build_plan(audit, roles)["status"], "blocked")
        audit["unscanned_actions"] = []
        audit["bone_references"] = [{"kind": "action_curve", "target": "Elbow_L"}]
        self.assertEqual(build_plan(audit, roles)["status"], "blocked")

    def test_rehome_to_self_or_descendant_is_rejected(self):
        audit, roles = tololo_pattern()
        roles["left"]["rehome_before_delete"] = {"_dummy_ShoulderC_L": "_dummy_ShoulderC_L"}
        plan = build_plan(audit, roles, simplify_shoulders=True)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(any("invalid rehome" in reason for reason in plan["blockers"]))
        audit["bones"].append(bone("ChildOfDummy", "_dummy_ShoulderC_L"))
        roles["left"]["rehome_before_delete"] = {"_dummy_ShoulderC_L": "ChildOfDummy"}
        self.assertEqual(build_plan(audit, roles, simplify_shoulders=True)["status"], "blocked")

    def test_custom_bone_names_are_accepted_with_explicit_roles(self):
        audit, _ = tololo_pattern()
        remap = {"UpperBody2": "躯干"}
        roles = {"torso": "躯干"}
        for side, suffix in (("left", "L"), ("right", "R")):
            roles[side] = {}
            for key, base in (("shoulder", "Shoulder"), ("upper_arm", "Arm"),
                              ("elbow", "Elbow"), ("wrist", "Wrist")):
                old = f"{base}_{suffix}"
                remap[old] = f"{key}_{side}"
                roles[side][key] = remap[old]
        for item in audit["bones"]:
            item["name"] = remap.get(item["name"], item["name"])
            item["parent"] = remap.get(item["parent"], item["parent"])
            item["children"] = [remap.get(name, name) for name in item["children"]]
        # Only semantic joints were renamed; configured roles still resolve them.
        plan = build_plan(audit, roles)
        self.assertEqual(plan["status"], "ready")
        self.assertTrue(any(op["bone"] == "elbow_left" for op in plan["operations"]))

    def test_arm_only_plan_does_not_require_shoulder_roles(self):
        audit, roles = tololo_pattern()
        for side in ("L", "R"):
            roles["left" if side == "L" else "right"]["shoulder"] = f"NoShoulder_{side}"
        plan = build_plan(audit, roles, simplify_shoulders=False)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(len(plan["operations"]), 4)


if __name__ == "__main__":
    unittest.main()
