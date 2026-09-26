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
