import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmx_physics_plan import make_plan, permits


def fixture():
    names = ["Pelvis", "L", "R", "Skirt", "Coat"]
    points = [[0, 0, 1], [-.2, 0, .7], [.2, .1, .7], [0, 0, .8], [0, 0, .9]]
    bones = [dict(name=n, position_blender_m=p) for n, p in zip(names, points)]
    mesh = dict(status="inspected", mesh="/Game/Char/SK_Test", bones=[
        dict(name=n, component_scale=[1, 1, 1], parent="Pelvis" if n != "Pelvis" else "") for n in names])
    def body(i, name, bone, mode, group, mask):
        return dict(source_index=i, source_name=name, source_bone=bone, mode=mode, group=group, mask=mask,
                    shape="capsule", size_blender_m=[.05, .1, 0], mass=1, linear_attenuation=.5,
                    angular_attenuation=.5, friction=.5, restitution=0,
                    position_blender_m=[0, 0, 1], rotation_blender_xyzw=[0, 0, 0, 1])
    bodies = [body(0, "Anatomical", "Pelvis", 0, 7, 65535),
              body(1, "LargeClothingHip", "Pelvis", 0, 2, 65531),
              body(2, "Skirt", "Skirt", 1, 2, 65531), body(3, "Coat", "Coat", 1, 6, 65535)]
    def joint(i, a, b):
        return dict(source_index=i, joint_type=0, source_rigid=a, target_rigid=b,
                    position_blender_m=[0, 0, 1], rotation_blender_xyzw=[0, 0, 0, 1],
                    linear_min_m=[0]*3, linear_max_m=[0]*3, angular_min_rad=[-.1]*3,
                    angular_max_rad=[.1]*3, linear_spring=[0]*3, angular_spring=[1]*3)
    inv = dict(schema="mmd2ue.pmx-physics-inventory.v1", source_sha256="hash", source_pmx="test.pmx",
               source_scale=.08, bones=bones, bodies=bodies, joints=[joint(0, 1, 2), joint(1, 0, 3)])
    profile = dict(schema="mmd2ue.pmx-physics-profile.v1", reviewed=True, source_sha256="hash",
        mesh=mesh["mesh"], measurement_anchor="Pelvis", variant="Test_v1", asset_root="/Game/Char/Physics",
        test_animation="/Game/Char/Walk", allow_same_name_bones=True, bone_map={},
        landmarks={n: n for n in names[:3]}, cross_partition_collision="none", cross_partition_reason="Reviewed isolated garments",
        partitions=[dict(name="Skirt", purpose="skirt", dynamic_ids=[2]), dict(name="Coat", purpose="coat", dynamic_ids=[3])],
        conversion=dict(reviewed=True, angular_spring_scale=10000, joint_damping_ratio=.7))
    return inv, profile, mesh


class PhysicsPlanTests(unittest.TestCase):
    def test_masks_are_symmetric_not_different_group_heuristic(self):
        a, b = dict(group=2, mask=64), dict(group=6, mask=4)
        self.assertTrue(permits(a, b))
        b["mask"] = 0
        self.assertFalse(permits(a, b))

    def test_anchor_retained_without_extra_collision_or_skirt_proxy(self):
        args = fixture()
        before = copy.deepcopy(args)
        plan = make_plan(*args)
        self.assertEqual(args, before)
        skirt, coat = plan["partitions"]
        hip = next(b for b in skirt["bodies"] if b["source_index"] == 1)
        dynamic = next(b for b in skirt["bodies"] if not b["kinematic"])
        self.assertFalse(permits(hip, dynamic))
        self.assertEqual(hip["mask"], 65531)
        self.assertNotIn("Skirt", {b["target_bone"] for b in coat["bodies"]})
        self.assertEqual(plan["disabled_cross_dynamic_pairs_by_policy"], 1)
        self.assertEqual(len(skirt["joints"]), 1)

    def reject(self, mutate, message):
        args = fixture()
        mutate(*args)
        with self.assertRaisesRegex(ValueError, message):
            make_plan(*args)

    def test_requires_review(self):
        self.reject(lambda i,p,m: p.update(reviewed=False), "review")

    def test_stale_source(self):
        self.reject(lambda i,p,m: p.update(source_sha256="changed"), "fingerprint")

    def test_non_unit_physics_bone(self):
        self.reject(lambda i,p,m: m["bones"][3].update(component_scale=[100]*3), "Non-unit")

    def test_unmapped_bone(self):
        self.reject(lambda i,p,m: p.update(allow_same_name_bones=False), "Unmapped")

    def test_mode_two_not_guessed(self):
        self.reject(lambda i,p,m: i["bodies"][2].update(mode=2), "mode 2")

    def test_cross_partition_joint_not_silently_removed(self):
        self.reject(lambda i,p,m: i["joints"][0].update(source_rigid=3), "crosses dynamic")

    def test_asymmetric_angular_limits(self):
        self.reject(lambda i,p,m: i["joints"][0].update(angular_min_rad=[0]*3), "Asymmetric")

    def test_duplicate_driver(self):
        self.reject(lambda i,p,m: i["bodies"][3].update(source_bone="Skirt"), "Multiple dynamic")

    def test_dynamic_ancestor_coupling(self):
        self.reject(lambda i,p,m: m["bones"][4].update(parent="Skirt"), "ancestor")

    def test_unreviewed_dynamic(self):
        self.reject(lambda i,p,m: p["partitions"].pop(), "Unreviewed dynamic")

    def test_excluding_anchor_needs_adapter(self):
        self.reject(lambda i,p,m: p["partitions"][0].update(excluded_static={"1":"only coat"}), "anchor")

    def test_unbound_joint(self):
        self.reject(lambda i,p,m: i["joints"][0].update(source_rigid=-1), "unbound")

    def test_negative_dynamic_mass(self):
        self.reject(lambda i,p,m: i["bodies"][2].update(mass=0), "positive mass")

    def test_shared_bone_material_difference(self):
        self.reject(lambda i,p,m: i["bodies"][1].update(friction=.1), "different materials")

    def test_three_independent_partitions(self):
        inv, profile, mesh = fixture()
        third = copy.deepcopy(inv["bodies"][3])
        third.update(source_index=4, source_bone="L", source_name="Tail")
        inv["bodies"].append(third)
        profile["partitions"].append(dict(name="Tail", purpose="tail", dynamic_ids=[4]))
        self.assertEqual(len(make_plan(inv, profile, mesh)["partitions"]), 3)


if __name__ == "__main__":
    unittest.main()
