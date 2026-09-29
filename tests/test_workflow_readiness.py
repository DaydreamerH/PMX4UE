import ast
import json
import os
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.skeleton_gate import verify, verify_import, digest
from tools.scene_effect_delivery import review_scene_effects

ROOT = Path(__file__).resolve().parents[1]


class ReadinessTests(unittest.TestCase):
    def test_all_portable_rotators_are_named_or_identity(self):
        for path in (ROOT / "tools").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Attribute) and node.func.attr == "Rotator")
                        or (isinstance(node.func, ast.Name) and node.func.id == "Rotator")):
                    self.assertFalse(node.args, str(path) + ":" + str(node.lineno))

    def test_real_preview_rotation_expression_with_roll_first_binding(self):
        tree = ast.parse((ROOT / "tools/ue_material_preview.py").read_text(encoding="utf-8-sig"))
        expression = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "rotation" for t in n.targets))
        def rotator(roll=0, pitch=0, yaw=0):
            return (roll, pitch, yaw)
        context = {"unreal": SimpleNamespace(Rotator=rotator), "self": SimpleNamespace(daylight=True,
                   sun_rotation=SimpleNamespace(roll=3, pitch=-38, yaw=72)), "light": {}}
        compiled = compile(ast.Expression(expression), "actual-preview-rotation", "eval")
        self.assertEqual(eval(compiled, context), (3, -38, 72))
        context["light"] = {"yaw_offset": 90}
        self.assertEqual(eval(compiled, context), (3, -38, 162))
        context["self"].daylight = False
        context["light"] = {"pitch": -35, "yaw": 45}
        self.assertEqual(eval(compiled, context), (0, -35, 45))

    def fixture(self, root):
        blend = root / "Model.blend"
        blend.write_bytes(b"fixture")
        bones, roles = [{"name": "Torso", "parent": None}], {"torso": "Torso"}
        for side in ("left", "right"):
            roles[side] = {key: side + key for key in ("shoulder", "upper_arm", "elbow", "wrist")}
            parent = "Torso"
            for key in ("shoulder", "upper_arm", "elbow", "wrist"):
                name = roles[side][key]
                bones.append(dict(name=name, parent=parent))
                parent = name
        audit = dict(blend=str(blend), bones=bones, source_file=dict(size=blend.stat().st_size,
                     mtime_ns=blend.stat().st_mtime_ns), bone_references_checked=True)
        audit_path = root / "skeleton_audit.json"
        audit_path.write_text(json.dumps(audit))
        config = dict(character={"id": "Model"}, paths={}, pmx4ue=dict(skeleton_policy="preserve"), skeleton={"roles": roles})
        decision = dict(schema="pmx4ue.skeleton-decision.v1", reviewed=True, audit_sha256=digest(audit_path),
                        source_blend_sha256=digest(blend), roles=roles,
                        arms=dict(action="preserve", reason="Both arm chains already direct"),
                        shoulders=dict(action="preserve", reason="Both shoulder chains already direct"))
        (root / "skeleton_decision.json").write_text(json.dumps(decision))
        return config, audit, decision

    def test_preserve_requires_current_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c, a, d = self.fixture(root)
            self.assertEqual(len(verify(c, root)), 3)
            d["reviewed"] = False
            (root / "skeleton_decision.json").write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, "preserve is not a review"):
                verify(c, root)
            d["reviewed"] = True
            (root / "skeleton_decision.json").write_text(json.dumps(d))
            (root / "Model.blend").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "stale source"):
                verify(c, root)

    def test_preserve_intermediates_requires_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c, a, d = self.fixture(root)
            a["bones"].append(dict(name="twist", parent="leftupper_arm"))
            next(b for b in a["bones"] if b["name"] == "leftelbow")["parent"] = "twist"
            (root / "skeleton_audit.json").write_text(json.dumps(a))
            d["audit_sha256"] = digest(root / "skeleton_audit.json")
            (root / "skeleton_decision.json").write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, "intermediates"):
                verify(c, root)

    def test_optimization_cannot_skip_apply_or_fbx_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c, a, d = self.fixture(root)
            for side in ("left", "right"):
                c["skeleton"]["roles"][side]["upper_twist"] = side + "twist"
                a["bones"].append(dict(name=side + "twist", parent=side + "upper_arm"))
                next(b for b in a["bones"] if b["name"] == side + "elbow")["parent"] = side + "twist"
            (root / "skeleton_audit.json").write_text(json.dumps(a))
            d.update(audit_sha256=digest(root / "skeleton_audit.json"), arms=dict(action="optimize", reason="Twists inline"))
            (root / "skeleton_decision.json").write_text(json.dumps(d))
            c["pmx4ue"].update(skeleton_policy="upper-only", skeleton_reviewed=True)
            from tools.legacy.skeleton_plan import build_plan
            plan = build_plan(a, c["skeleton"]["roles"])
            (root / "skeleton_plan.json").write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "skeleton-apply first"):
                verify(c, root)
            applied = dict(status="validated_variant_exported", operations=plan["operations"], weight_groups_unchanged=True,
                           source_blend=str(root / "Model.blend"), derived_fbx=str(root / "upper_only.fbx"))
            (root / "skeleton_apply.json").write_text(json.dumps(applied))
            (root / "upper_only.fbx").write_bytes(b"fbx")
            with self.assertRaisesRegex(ValueError, "no current successful"):
                verify(c, root)
            (root / "runs").mkdir()
            record = dict(status="executed_needs_review",
                input_sha256={str(root / n): digest(root / n) for n in ("Model.blend", "skeleton_plan.json")},
                output_sha256={str(root / n): digest(root / n) for n in ("upper_only.fbx", "skeleton_apply.json")})
            (root / "runs/1_skeleton-apply.json").write_text(json.dumps(record))
            self.assertIn(str(root / "upper_only.fbx"), verify(c, root))

    def test_scene_effects_not_silently_skipped(self):
        issues = []
        review_scene_effects({}, {}, issues.append)
        self.assertTrue(any("outline" in i for i in issues))
        self.assertTrue(any("rim" in i for i in issues))
        p = {"scene_effects": {k: dict(status="not_selected", reason="Flat reference style", evidence=["design"])
                               for k in ("outline", "rim")}}
        issues = []
        review_scene_effects(p, {"design": ("review", {})}, issues.append)
        self.assertEqual(issues, [])

    def test_import_provenance_rejects_old_target_mesh(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c, _, _ = self.fixture(root)
            (root / "Model.fbx").write_bytes(b"fbx")
            (root / "ue_build_report.json").write_text(json.dumps({"skeletal_mesh": "/Game/Selected.Selected"}))
            (root / "runs").mkdir()
            record = dict(status="executed_needs_review", input_sha256={str(root / "Model.fbx"): digest(root / "Model.fbx")},
                          output_sha256={str(root / "ue_build_report.json"): digest(root / "ue_build_report.json")})
            (root / "runs/1_ue-build.json").write_text(json.dumps(record))
            c["pmx4ue"]["rig_profile"] = str(root / "rig.json")
            (root / "rig.json").write_text(json.dumps({"target": {"mesh": "/Game/Old"}}))
            with self.assertRaisesRegex(ValueError, "target mesh differs"):
                verify_import(c, root, "ik")
            (root / "rig.json").write_text(json.dumps({"target": {"mesh": "/Game/Selected"}}))
            self.assertIn(str(root / "Model.fbx"), verify_import(c, root, "ik"))

    def test_built_outline_without_attachment_does_not_pass(self):
        p = dict(scene_effects=dict(outline=dict(status="reviewed", method="outline", effect="outline",
            reason="Silhouette definition", evidence=["design"], runtime_binding="Overlay on character component"),
            rim=dict(status="not_selected", reason="No rim in selected style", evidence=["design"])),
            effects=[dict(id="outline", status="reviewed", image_sha256=["a", "b"])])
        candidate = dict(case="Outline", camera={"name": "Front"}, light={"name": "Day"}, mode="Lit", image={"sha256": "b"})
        baseline = dict(candidate, case="Baseline", image={"sha256": "a"})
        reports = {"design": ("review", {}), "capture": ("capture", dict(profile=dict(cases=[
            dict(name="Baseline", slots=[]), dict(name="Outline", slots=[], outline="/Game/Outline")]),
            captures=[baseline, candidate]))}
        issues = []
        review_scene_effects(p, reports, issues.append)
        self.assertTrue(any("actual preview attachment" in i for i in issues))
        candidate["scene_effects"] = {"outline": {"ok": True}}
        issues = []
        review_scene_effects(p, reports, issues.append)
        self.assertEqual(issues, [])

    def test_scene_builder_only_builds_selected_assets_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            calls, occupied = [], set()
            ctx = SimpleNamespace(config={"features": {"outline": {"mode": "enabled"}, "depth_rim": {"mode": "disabled"}}},
                names=dict(material_root="/Game/Example/Materials", instance_prefix="MI_Example",
                           outline_asset="M_Outline", rim_asset="M_Rim"), report_path=lambda n: root / n)
            modules = {"unreal": SimpleNamespace(EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda p: p in occupied)),
                       "ue_context": SimpleNamespace(BuildContext=lambda _: ctx),
                       "ue_feature_outline": SimpleNamespace(build=lambda c: calls.append("outline") or {"status": "success"}),
                       "ue_feature_depth_rim": SimpleNamespace(build=lambda c: calls.append("rim") or {"status": "success"})}
            output = root / "scene.json"
            with patch.dict("sys.modules", modules), patch.dict(os.environ, PMX4UE_CONFIG="fixture", PMX4UE_OUTPUT=str(output)):
                runpy.run_path(str(ROOT / "tools/ue_scene_effects.py"))
                self.assertEqual(calls, ["outline"])
                self.assertFalse(json.loads(output.read_text())["applied_to_scene"])
                with patch.dict(os.environ, PMX4UE_OUTPUT=str(root / "another.json")):
                    occupied.add("/Game/Example/Materials/MI_Example_Outline")
                    with self.assertRaisesRegex(RuntimeError, "asset exists"):
                        runpy.run_path(str(ROOT / "tools/ue_scene_effects.py"))
                self.assertEqual(calls, ["outline"])


if __name__ == "__main__":
    unittest.main()
