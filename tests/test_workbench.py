import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pmx4ue as w


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pmx4ue space ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "Blank.uproject"
        self.project.write_text("{}")
        self.pmx = self.root / "model.pmx"
        self.pmx.write_bytes(b"fixture")
        self.config = self.root / "character.json"
        w.initialize(argparse.Namespace(project=str(self.project), pmx=str(self.pmx), source_root=None,
            output=str(self.config), id="Example", variant="v1", scale=.08, blender="Blender.exe", engine="UE"))
        self.c, _, self.a = w.load(self.config)

    def test_no_implicit_source_review(self):
        with self.assertRaisesRegex(ValueError, "scale"):
            w.run(self.c, self.project, self.a, "export")

    def test_material_only_recipe_does_not_require_fbx(self):
        self.c["pmx4ue"].update(material_reviewed=True, material_source_mesh="/Game/PMX4UE/Example/base/Mesh/SK_Example")
        spec = w.run(self.c, self.project, self.a, "material-build")
        self.assertEqual(spec["env"]["MMD2UE_BUILD_MODE"], "material")
        self.assertFalse(any(path.endswith(".fbx") for path in spec["inputs"]))
        self.assertFalse(self.a.exists())

    def test_preflight_is_dry(self):
        spec = w.run(self.c, self.project, self.a, "material-preflight")
        self.assertTrue(spec["env"]["PMX4UE_SCRIPT"].endswith("ue_material_preflight.py"))
        self.assertFalse(self.a.exists())

    def test_material_preview_owns_new_visible_full_editor(self):
        spec = w.run(self.c, self.project, self.a, "material-preview")
        self.assertTrue(spec["argv"][0].endswith("UnrealEditor.exe"))
        # v3 visual evidence must come from a visible viewport, not offscreen capture.
        self.assertNotIn("-RenderOffscreen", spec["argv"])
        self.assertIn("-PMX4UEPreview=" + spec["env"]["PMX4UE_PREVIEW_TOKEN"], spec["argv"])
        self.assertIn(str(self.a / "material_compile.json"), spec["inputs"])
        self.assertFalse(self.a.exists())

    def test_physics_performance_keeps_offscreen_launch(self):
        spec = w.run(self.c, self.project, self.a, "performance")
        self.assertIn("-RenderOffscreen", spec["argv"])
        self.assertFalse(self.a.exists())

    def test_added_stages_are_dry_and_explicit(self):
        for stage, script in [('capabilities','ue_capabilities.py'), ('animation-export','ue_animation_export.py'),
                              ('material-compile','ue_material_compile.py')]:
            spec = w.run(self.c, self.project, self.a, stage)
            self.assertTrue(spec['env']['PMX4UE_SCRIPT'].endswith(script))
        self.assertFalse(self.a.exists())

    def test_head_hair_stage_requires_reviewed_profile_path(self):
        with self.assertRaisesRegex(ValueError, 'head_hair_profile'):
            w.run(self.c, self.project, self.a, 'head-hair')
        self.c['pmx4ue']['head_hair_profile'] = str(self.root/'head_hair.json')
        spec = w.run(self.c, self.project, self.a, 'head-hair')
        self.assertTrue(spec['env']['PMX4UE_SCRIPT'].endswith('ue_head_hair_workflow.py'))
        self.assertEqual(spec['env']['PMX4UE_HEAD_HAIR_PROFILE'], str(self.root/'head_hair.json'))
        self.assertFalse(self.a.exists())

    def test_bind_warning_never_becomes_clean_execution(self):
        def fake_run(*args, **kwargs):
            kwargs['stdout'].write('Imported skeleton has some INVALID BIND POSES\n')
            w.write(self.a/'capabilities.json', {'status':'available'})
            return argparse.Namespace(returncode=0)
        with patch.object(w.subprocess, 'run', side_effect=fake_run):
            result = w.run(self.c, self.project, self.a, 'capabilities', True)
        self.assertEqual(result['status'], 'executed_with_import_risks')
        record = w.read(result['record'])
        self.assertFalse(record['production_accepted'])
        self.assertIn('invalid bind poses', record['import_risks'])

    def test_retarget_pose_stage_is_explicit_and_dry(self):
        spec = w.run(self.c, self.project, self.a, "retarget-pose")
        self.assertTrue(spec["env"]["PMX4UE_SCRIPT"].endswith("ue_retarget_pose.py"))
        self.assertEqual(spec["inputs"], [self.c["pmx4ue"]["retarget_pose_profile"]])
        self.assertFalse(self.a.exists())
        del self.c["pmx4ue"]["retarget_pose_profile"]
        with self.assertRaisesRegex(ValueError, "retarget_pose_profile"):
            w.run(self.c, self.project, self.a, "retarget-pose")

    def test_dry_run_no_writes_and_safe_arguments(self):
        self.c["pmx4ue"]["source_scale_reviewed"] = True
        spec = w.run(self.c, self.project, self.a, "export")
        self.assertIn(str(self.pmx), spec["argv"])
        self.assertIn("cm-native", spec["argv"])
        self.assertFalse(self.a.exists())

    def test_unknown_namespace_rejected(self):
        self.c["paths"]["ue_root"] = "/Game/Production"
        w.write(self.config, self.c)
        with self.assertRaisesRegex(ValueError, "namespace"):
            w.load(self.config)

    def test_upper_only_never_calls_leg_cleanup(self):
        self.c["pmx4ue"].update(skeleton_policy="upper-only", skeleton_reviewed=True)
        self.c["skeleton"] = {"roles": {"left": {}, "right": {}}, "leg_cleanup": {"enabled": True}}
        spec = w.run(self.c, self.project, self.a, "skeleton-plan")
        self.assertNotIn("--simplify-legs", spec["argv"])

    def test_existing_output_not_overwritten(self):
        self.a.mkdir(parents=True)
        (self.a / "audit.json").write_text("original")
        with self.assertRaisesRegex(ValueError, "Outputs exist"):
            w.run(self.c, self.project, self.a, "audit", True)
        self.assertEqual((self.a / "audit.json").read_text(), "original")

    def test_no_build_before_material_review(self):
        with self.assertRaisesRegex(ValueError, "material"):
            w.run(self.c, self.project, self.a, "ue-build")

    def test_ik_execution_cannot_skip_skeleton_review(self):
        w.write(Path(self.c["pmx4ue"]["rig_profile"]), {"reviewed": True})
        with patch.object(w.subprocess, "run") as process:
            with self.assertRaisesRegex(ValueError, "skeleton-audit"):
                w.run(self.c, self.project, self.a, "ik", True)
            process.assert_not_called()

    def test_scene_effect_build_is_explicit_and_dry(self):
        self.c["pmx4ue"]["material_reviewed"] = True
        with self.assertRaisesRegex(ValueError, "Explicitly enable"):
            w.run(self.c, self.project, self.a, "scene-effects-build")
        self.c["features"]["outline"] = {"mode": "enabled"}
        spec = w.run(self.c, self.project, self.a, "scene-effects-build")
        self.assertTrue(spec["env"]["PMX4UE_SCRIPT"].endswith("ue_scene_effects.py"))
        self.assertIn(str(self.a / "material_compile.json"), spec["inputs"])
        self.assertFalse(self.a.exists())

    def test_independent_lock_and_cleanup(self):
        with w.project_lock(self.project):
            with self.assertRaisesRegex(ValueError, "owns"):
                with w.project_lock(self.project):
                    pass
        self.assertFalse((self.project.parent / "Saved/PMX4UE/.agent.lock").exists())

    def test_plugin_copy_dry_run_and_no_overwrite(self):
        result = w.install_plugin(self.project)
        self.assertFalse(Path(result["destination"]).exists())
        Path(result["destination"]).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "exists"):
            w.install_plugin(self.project, True)

    def test_nonzero_exit_recorded_even_with_report(self):
        self.c["pmx4ue"]["source_scale_reviewed"] = True
        with patch.object(w.subprocess, "run", return_value=argparse.Namespace(returncode=5)):
            with self.assertRaisesRegex(ValueError, "Process exited"):
                w.run(self.c, self.project, self.a, "export", True)
        records = list((self.a / "runs").glob("*.json"))
        self.assertEqual(w.read(records[0])["status"], "failed")

    def test_changed_input_reported(self):
        self.a.mkdir(parents=True)
        w.write(self.a / "runs/one.json", dict(stage="export", status="executed_needs_review",
                                              input_sha256={str(self.pmx): w.sha(self.pmx)}))
        self.pmx.write_bytes(b"new")
        self.assertIn(str(self.pmx), w.status(self.a)["runs"][0]["changed_files"])


if __name__ == "__main__":
    unittest.main()
