import copy
import math
import unittest
from tools.retarget_pose_math import axis_angle, forward, plan, verify, swing, rotate


def fixture():
    bones = []
    # Deliberately non-zero reference rotations and a rotated parent.
    for name, parent, pos, q in [
        ("root", -1, (12, 8, 0), axis_angle((0, 0, 1), 25)),
        ("spine", 0, (0, 0, 100), (0, 0, 0, 1)),
        ("upper_l", 1, (0, 20, 0), axis_angle((1, 0, 0), -35)),
        ("elbow_l", 2, (0, 30, 0), axis_angle((1, 0, 0), 15)),
        ("wrist_l", 3, (0, 25, 0), (0, 0, 0, 1)),
        ("upper_r", 1, (0, -20, 0), axis_angle((1, 0, 0), 35)),
        ("elbow_r", 5, (0, -30, 0), axis_angle((1, 0, 0), -15)),
        ("wrist_r", 6, (0, -25, 0), (0, 0, 0, 1)),
        ("leg", 0, (0, 10, 80), (0, 0, 0, 1)),
    ]:
        bones.append(dict(name=name, parent=parent, local_position=pos, ref_rotation=q,
                          offset=(0, 0, 0, 1), ref_scale=(1, 1, 1), local_scale=(1, 1, 1), global_scale=(1, 1, 1)))
    forward(bones)
    return {"bones": bones, "root_offset": [0, 0, 0]}


def spec():
    return dict(auto_arms=True, up_axis=[0, 0, 1], arms=dict(
        left=["upper_l", "elbow_l", "wrist_l"], right=["upper_r", "elbow_r", "wrist_r"]))


class PoseTests(unittest.TestCase):
    def leg_fixture(self):
        data = fixture()
        legs, goals = {}, {}
        root_q = data["bones"][0]["global_rotation"]
        for side, sign in (("left", 1), ("right", -1)):
            base = len(data["bones"])
            chain = [side+label for label in ("_hip", "_knee", "_ankle")]
            for name, parent, pos in zip(chain, [0, base, base+1], [(10*sign, 0, 80), (5*sign, 0, -38), (5*sign, -2, -40)]):
                data["bones"].append(dict(name=name, parent=parent, local_position=pos,
                    ref_rotation=(0, 0, 0, 1), offset=(0, 0, 0, 1), ref_scale=(1, 1, 1),
                    local_scale=(1, 1, 1), global_scale=(1, 1, 1)))
            legs[side] = chain
            goals[side] = [rotate(root_q, (-.025*sign, -.01, -1)), rotate(root_q, (-.025*sign, -.05, -1))]
        forward(data["bones"])
        return data, dict(legs=legs, directions=goals, left_axis=rotate(root_q, (1, 0, 0)),
                          up_axis=[0, 0, 1], max_foot_height_change_cm=2)

    def test_leg_direction_matching_retains_upper_lengths_and_feet(self):
        original, align = self.leg_fixture()
        out = plan(original, dict(leg_alignment=align))
        self.assertEqual(original["bones"][:9], out["bones"][:9])
        self.assertLess(out["stance"]["after"]["ankle_gap_cm"], out["stance"]["before"]["ankle_gap_cm"])
        self.assertLess(max(s["final_degrees"] for s in out["segments"]), .001)
        for a, b in zip(original["bones"], out["bones"]):
            self.assertEqual(a["local_position"], b["local_position"])
            if a["name"].endswith("_ankle"):
                self.assertLess(math.dist(rotate(a["global_rotation"], (0, 0, 1)), rotate(b["global_rotation"], (0, 0, 1))), 1e-8)
        self.assertLess(verify(out, plan(out, dict(leg_alignment=align)))["max_position_error_cm"], 1e-8)

    def test_invalid_leg_goals_and_height(self):
        original, align = self.leg_fixture()
        for failure in [dict(left_axis=[0, 0, 1]), dict(max_foot_height_change_cm=0),
                        dict(directions=dict(left=[[0, 0, 1]]*2, right=[[0, 0, -1]]*2)),
                        dict(legs=dict(left=["left_knee", "left_hip", "left_ankle"], right=align["legs"]["right"]))]:
            with self.assertRaises(ValueError):
                plan(original, dict(leg_alignment={**align, **failure}))

    def test_restore_compensated_leg_preserves_accepted_upper_body(self):
        original = fixture()
        original["bones"][-1]["offset"] = axis_angle((1, 0, 0), 40)
        original["bones"].append(dict(name="ankle", parent=8, local_position=(0, 0, -75),
            ref_rotation=(0, 0, 0, 1), offset=(0, 0, 0, 1), ref_scale=(1, 1, 1),
            local_scale=(1, 1, 1), global_scale=(1, 1, 1)))
        forward(original["bones"])
        settings = dict(restore_reference_rotations=["leg"], posture_checks=[dict(
            start="leg", end="ankle", up_axis=[0, 0, -1], max_tilt_degrees=5)])
        out = plan(original, settings)
        self.assertAlmostEqual(out["posture"]["before"][0]["tilt_degrees"], 40)
        self.assertLess(out["posture"]["after"][0]["tilt_degrees"], .001)
        self.assertEqual(set(out["offsets"]), {"leg"})
        self.assertEqual(original["bones"][:8], out["bones"][:8])

    def test_restore_torso_before_arm_alignment(self):
        original = fixture()
        original["bones"].append(dict(name="neck", parent=1, local_position=(0, 0, 35),
            ref_rotation=(0, 0, 0, 1), offset=(0, 0, 0, 1), ref_scale=(1, 1, 1),
            local_scale=(1, 1, 1), global_scale=(1, 1, 1)))
        original["bones"][1]["offset"] = axis_angle((1, 0, 0), 20)
        forward(original["bones"])
        unchanged = copy.deepcopy(original)
        settings = {**spec(), "posture_checks": [dict(start="spine", end="neck",
            up_axis=[0, 0, 1], max_tilt_degrees=2)]}
        with self.assertRaisesRegex(ValueError, "tilt exceeds"):
            plan(original, settings)
        settings["restore_reference_rotations"] = ["spine"]
        out = plan(original, settings)
        self.assertEqual(original, unchanged)
        self.assertEqual(out["offsets"]["spine"], (0, 0, 0, 1))
        self.assertAlmostEqual(out["posture"]["before"][0]["tilt_degrees"], 20)
        self.assertLess(out["posture"]["after"][0]["tilt_degrees"], .001)
        self.assertLess(max(s["final_degrees"] for s in out["segments"]), .001)
        self.assertLess(verify(out, plan(out, settings))["max_position_error_cm"], 1e-8)
        for a, b in zip(original["bones"], out["bones"]):
            self.assertEqual(a["local_position"], b["local_position"])

    def test_restore_allowlist_validation_and_reset_only(self):
        for restored in ("spine", ["missing"], ["spine", "spine"], [None]):
            with self.assertRaises(ValueError):
                plan(fixture(), {**spec(), "restore_reference_rotations": restored})
        out = plan(fixture(), dict(restore_reference_rotations=["spine"]))
        self.assertEqual(set(out["offsets"]), {"spine"})

    def test_tpose_and_untouched_bones(self):
        original = fixture()
        untouched = copy.deepcopy(original)
        out = plan(original, spec())
        self.assertEqual(original, untouched)
        self.assertEqual(set(out["offsets"]), {"upper_l", "elbow_l", "upper_r", "elbow_r"})
        self.assertLess(max(s["final_degrees"] for s in out["segments"]), .001)
        for a, b in zip(original["bones"], out["bones"]):
            self.assertEqual(a["local_position"], b["local_position"])
        self.assertEqual(original["bones"][-1], out["bones"][-1])

    def test_idempotent(self):
        first = plan(fixture(), spec())
        second = plan(first, spec())
        self.assertLess(verify(first, second)["max_position_error_cm"], 1e-8)

    def test_manual_local_rotation(self):
        out = plan(fixture(), dict(edits=[dict(bone="wrist_l", mode="add_local", axis=[0, 1, 0], degrees=10)]))
        self.assertAlmostEqual(out["offsets"]["wrist_l"][1], math.sin(math.radians(5)))
        self.assertEqual(len(out["offsets"]), 1)

    def test_set_offset_and_invalid_edit(self):
        out = plan(fixture(), dict(edits=[dict(bone="wrist_l", mode="set_offset", quaternion_xyzw=[0, 0, 1, 1])]))
        self.assertAlmostEqual(out["offsets"]["wrist_l"][2], 2**-.5)
        with self.assertRaises(ValueError):
            plan(fixture(), dict(edits=[dict(bone="missing", mode="add_local")]))

    def test_reject_scale_and_native_mismatch(self):
        for key in ("ref_scale", "local_scale", "global_scale"):
            data = fixture()
            data["bones"][0][key] = (100, 100, 100)
            with self.assertRaises(ValueError):
                plan(data, spec())
        data = fixture()
        data["bones"][2]["global_position"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            plan(data, spec())

    def test_bad_chain_axes_and_degenerate(self):
        for change in [dict(up_axis=[0, 0, 0]), dict(left_axis=[0, 0, 1]),
                       dict(arms=dict(left=["elbow_l", "upper_l", "wrist_l"], right=["upper_r", "elbow_r", "wrist_r"]))]:
            with self.assertRaises(ValueError):
                plan(fixture(), {**spec(), **change})
        with self.assertRaises(ValueError):
            swing([1, 0, 0], [-1, 0, 0])

    def test_swing(self):
        self.assertLess(math.dist(rotate(swing([0, 1, 0], [0, 0, 1]), [0, 1, 0]), [0, 0, 1]), 1e-8)

    def test_verify_detects_native_error(self):
        a, b = fixture(), fixture()
        b["bones"][2]["global_position"] = [0, 0, 0]
        with self.assertRaises(ValueError):
            verify(a, b)
