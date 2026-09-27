import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests/inherited")]
from ue_bridge import resolve, inventory, CAPABILITIES
from pmx_physics_settings import resolve_settings
from pmx_physics_plan import make_plan
from test_pmx_physics_plan import fixture
from bone_identity import collect, unique_map


class PipelineCompletionTests(unittest.TestCase):
    def test_bone_identity_excludes_ambiguous_source_names(self):
        rows = [dict(source_name='左腕',export_bone='Arm_L'), dict(source_name='重複',export_bone='A'),
                dict(source_name='重複',export_bone='B'), dict(source_name='',export_bone='Helper')]
        self.assertEqual(unique_map(rows), ({'左腕':'Arm_L'}, ['重複']))

    def test_bone_identity_uses_import_metadata(self):
        armature = SimpleNamespace(pose=SimpleNamespace(bones=[SimpleNamespace(name='Arm_L',
            mmd_bone=SimpleNamespace(name_j='左腕',bone_id=12)),SimpleNamespace(name='Helper')]))
        rows = collect(armature)
        self.assertEqual(rows[0]['source_bone_id'], 12)
        self.assertEqual(unique_map(rows), ({'左腕':'Arm_L'}, []))
    def test_rest_only_does_not_claim_movement(self):
        inv, profile, mesh = fixture()
        profile.update(rest_only=True, test_animation="")
        plan = make_plan(inv, profile, mesh)
        self.assertTrue(plan["rest_only"])
        self.assertEqual(plan["walk_blueprint"], "")
        self.assertEqual(plan["performance_controls"], {})

    def test_rest_only_rejects_movement_or_perf(self):
        for changes in ({}, {"test_animation":"", "performance_test":{"enabled":True}}):
            args = fixture()
            args[1].update(rest_only=True, **changes)
            with self.assertRaisesRegex(ValueError, "rest_only"):
                make_plan(*args)

    def test_base_bone_must_exist_and_be_nondynamic(self):
        for bone in ("Missing", "Skirt"):
            args = fixture()
            args[1]["simulation"] = {"space":"base_bone", "base_bone":bone}
            with self.assertRaisesRegex(ValueError, "base bone"):
                make_plan(*args)

    def test_base_bone_settings_preserved(self):
        args = fixture()
        before = copy.deepcopy(args)
        args[1]["simulation"] = {"space":"base_bone", "base_bone":"Pelvis", "max_linear_acceleration":2000}
        plan = make_plan(*args)
        self.assertEqual(plan["simulation"]["max_linear_acceleration"], 2000)
        self.assertEqual(args[0], before[0])
        self.assertEqual(args[2], before[2])

    def test_invalid_motion_parameters(self):
        for value in ({"space":"other"}, {"base_bone":"Pelvis"}, {"world_alpha":1.1},
                      {"max_linear_velocity":float("nan")}, {"damping_alpha":-1}, {"max_angular_acceleration":True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_settings({"simulation":value})

    def test_acceptance_requires_repeated_sized_runs(self):
        for value in ({"enabled":True,"repeats":1}, {"enabled":True,"seconds":10}, {"viewport_width":0}):
            with self.assertRaises(ValueError):
                resolve_settings({"performance_test":value})

    def test_provider_selection_and_duplicate_rejection(self):
        suffix, methods = CAPABILITIES["workflow"]
        cls = type("Host", (), {m:staticmethod(lambda:None) for m in methods})
        for prefix in ("MMD2UE", "PMX4UE"):
            module = SimpleNamespace(**{prefix+suffix:cls})
            self.assertIs(resolve("workflow", module), cls)
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            resolve("workflow", SimpleNamespace(**{"MMD2UE"+suffix:cls, "PMX4UE"+suffix:cls}))

    def test_old_module_blocks_instead_of_guessing(self):
        self.assertFalse(inventory(SimpleNamespace())["workflow"]["available"])
        with self.assertRaisesRegex(RuntimeError, "outdated"):
            resolve("workflow", SimpleNamespace(MMD2UEWorkflowTools=object()))

    def test_native_host_plugin_parity(self):
        for directory, extension in (("Public", "h"), ("Private", "cpp")):
            plugin = (ROOT/f"unreal/PMX4UE/Source/PMX4UEEditor/{directory}/PMX4UEWorkflowTools.{extension}").read_text()
            host_path = ROOT.parent/f"Source/MMD2UEEditor/{directory}/MMD2UEWorkflowTools.{extension}"
            if not host_path.exists():
                self.skipTest('Optional MMD2UE host parity; standalone workbench has no host module')
            host = host_path.read_text()
            self.assertEqual(plugin.replace("PMX4UE", "MMD2UE"), host)


if __name__ == "__main__":
    unittest.main()
