"""Checks that a source archive is a self-contained workbench, without requiring Git."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_portable_entry_and_dependencies_present(self):
        for relative in (
            "START_HERE.md", "AGENTS.md", "templates/import-agent.md",
            "docs/fresh-project-runbook.md", "docs/agent-physics-workflow.md",
            "docs/face-sdf-runtime.md", "skills/pmx-to-ue/SKILL.md",
            "tools/ue_entry.py", "tools/ue_bridge.py", "tools/ue_capabilities.py",
            "tools/bone_identity.py", "tools/blender_fbx_bind.py",
            "tools/ue_animation_export.py", "templates/animation_export.example.json",
            "tools/ue_material_compile.py", "tools/ue_physics_performance.py",
            "tools/review_physics_benchmark.py", "tools/ue_face_sdf_workflow.py",
            "tools/face_sdf_profile.py", "templates/face_sdf.example.json",
        ):
            with self.subTest(file=relative):
                self.assertTrue((ROOT/relative).is_file())

    def test_runtime_and_editor_sources_are_included(self):
        source = ROOT/"unreal/PMX4UE/Source"
        for module, stem in (("PMX4UE", "PMX4UEFaceSDFComponent"),
                             ("PMX4UE", "PMX4UEFaceSDFPreviewActor"),
                             ("PMX4UEEditor", "PMX4UEWorkflowTools")):
            for directory, suffix in (("Public", ".h"), ("Private", ".cpp")):
                with self.subTest(module=module, file=stem+suffix):
                    self.assertTrue((source/module/directory/(stem+suffix)).is_file())
        descriptor = json.loads((ROOT/"unreal/PMX4UE/PMX4UE.uplugin").read_text(encoding="utf-8"))
        self.assertEqual(descriptor["VersionName"], "0.2.0")
        self.assertEqual({m["Type"] for m in descriptor["Modules"]}, {"Runtime", "Editor"})

    def test_new_agent_prompt_has_no_origin_project_requirement(self):
        prompt = (ROOT/"templates/import-agent.md").read_text(encoding="utf-8")
        self.assertNotIn("MMD2UE", prompt)
        self.assertNotIn("D:/", prompt)
        self.assertNotIn("D:\\", prompt)
        self.assertIn(".uproject", prompt)

    def test_all_distributed_python_parses_without_importing_engine_modules(self):
        for folder in ("tools", "maintenance", "tests"):
            for path in (ROOT/folder).rglob("*.py"):
                with self.subTest(file=str(path.relative_to(ROOT))):
                    compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
