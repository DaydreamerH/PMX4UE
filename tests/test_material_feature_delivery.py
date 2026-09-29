import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from tools.material_feature_delivery import FEATURES, GAME_CHECKS, review_material_features, review_scene_gameplay, review_cost


class MaterialQualityTests(unittest.TestCase):
    def fixture(self):
        profile = dict(material_review_contract=1, material_acceptance="static_lookdev", material_features={}, effects=[])
        cases = {"a": {("capture", "Candidate", "FrontClose", "Day", "Lit")},
                 "b": {("capture", "Candidate", "ObliqueClose", "Day", "Lit")}}
        for name, fields in FEATURES.items():
            profile["material_features"][name] = dict(status="reviewed", slots=[name], reason="Model specific", evidence=["design"],
                effect=name, observations={f: "Fixture observations" for f in fields})
            profile["effects"].append(dict(id=name, status="reviewed", slots=[name], comparison_required=True, image_sha256=["a", "b"]))
        return profile, {n: {} for n in FEATURES}, {"design": ("review", {})}, cases

    def check(self, p, slots, reports, cases):
        issues = []
        review_material_features(p, slots, reports, cases, issues.append)
        return issues

    def test_features_cannot_be_omitted(self):
        p, s, r, c = self.fixture()
        self.assertEqual(self.check(p, s, r, c), [])
        del p["material_features"]["eye_layers"]
        self.assertTrue(any("eye_layers" in x for x in self.check(p, s, r, c)))

    def test_base_color_review_cannot_replace_specialist_review(self):
        p, s, r, c = self.fixture()
        p["material_features"]["hair_clumps"]["observations"] = {}
        self.assertTrue(any("observations" in x for x in self.check(p, s, r, c)))
        c["b"] = c["a"].copy()
        self.assertTrue(any("views" in x for x in self.check(p, s, r, c)))

    def test_existing_slots_cannot_hide_as_na_or_unapproved_limit(self):
        p, s, r, c = self.fixture()
        row = p["material_features"]["stocking_edge"]
        row["status"] = "not_applicable"
        self.assertTrue(any("existing target" in x for x in self.check(p, s, r, c)))
        row["status"] = "accepted_limitation"
        self.assertTrue(any("user approval" in x for x in self.check(p, s, r, c)))
        row["scope_approval"] = "Explicit user request, fixture"
        self.assertEqual(self.check(p, s, r, c), [])

    def test_absent_family_can_be_evidenced_na(self):
        p, s, r, c = self.fixture()
        p["material_features"]["stocking_edge"].update(status="not_applicable", slots=[])
        self.assertEqual(self.check(p, s, r, c), [])

    def test_static_does_not_imply_game_ready(self):
        p = dict(material_acceptance="static_lookdev", scene_effects={n: dict(game_validation=dict(status="pending",
            reason="No runtime test yet", next_action="Run test matrix")) for n in ("outline", "rim")})
        issues = []
        review_scene_gameplay(p, {}, issues.append)
        self.assertEqual(issues, [])
        p["material_acceptance"] = "game_ready"
        review_scene_gameplay(p, {}, issues.append)
        self.assertTrue(any("cannot claim game_ready" in x for x in issues))

    def measurement(self):
        sample = dict(hardware="GPU/CPU fixture", resolution=[1920,1080], quality="High", camera_path="loop", animation="walk",
            actor_count=2, physics="on", exposure_policy="default_scene", engine="5.8", execution_mode="Standalone",
            max_fps=200, vsync=False, duration_seconds=30, warmup_seconds=5, frames=2400,
            frame_p95_ms=10, frame_p99_ms=12, gpu_p95_ms=8, game_p95_ms=5)
        return dict(effects=["outline"], measurements=dict(off=dict(sample, active_effects=[]), on=dict(sample, active_effects=["outline"])),
                    budget=dict(frame_p99_ms=16.67, added_gpu_p95_ms=1))

    def test_performance_budget_conditions_and_invalid_metrics(self):
        for mutate, expected in (
            (lambda r: r["measurements"]["on"].update(max_fps=60), "t.MaxFPS"),
            (lambda r: r["measurements"]["on"].update(resolution=[800,600]), "unmatched"),
            (lambda r: r["measurements"]["on"].update(frame_p99_ms=24), "budget exceeded"),
            (lambda r: r["measurements"]["on"].update(gpu_p95_ms=11), "GPU budget"),
            (lambda r: r["measurements"]["on"].update(frame_p99_ms=None), "invalid")):
            report = self.measurement()
            issues = []
            review_cost(report, "rim", issues.append)
            self.assertEqual(issues, [])
            mutate(report)
            review_cost(report, "rim", issues.append)
            self.assertTrue(any(expected in x for x in issues), issues)

    def test_game_reports_need_raw_evidence_all_checks_and_current_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"Content").mkdir()
            asset = root/"Content/M.uasset"
            asset.write_bytes(b"fixture")
            sha = hashlib.sha256(asset.read_bytes()).hexdigest()
            p = dict(project=str(root/"Game.uproject"), material_acceptance="game_ready",
                assets=[dict(path="/Game/M", sha256=sha)], scene_effects=dict(
                    outline=dict(game_validation=dict(status="reviewed", checks={k:k for k in GAME_CHECKS})),
                    rim=dict(status="not_selected")))
            reports = {"raw": ("raw", None)}
            for check in GAME_CHECKS:
                report = dict(schema="pmx4ue.material-game-test.v1", check=check, project=p["project"], effects=["outline"],
                    passed=True, reviewer="agent", observation="Test fixture", evidence=["raw"], asset_sha256={"/Game/M":sha})
                if check == "performance": report.update(self.measurement())
                reports[check] = ("material_game_test", report)
            issues = []
            review_scene_gameplay(p, reports, issues.append)
            self.assertEqual(issues, [])
            reports["occlusion"][1]["evidence"] = []
            review_scene_gameplay(p, reports, issues.append)
            self.assertTrue(any("raw evidence" in x for x in issues))
            asset.write_bytes(b"changed")
            review_scene_gameplay(p, reports, issues.append)
            self.assertTrue(any("changed/missing asset" in x for x in issues))

    def test_docs_keep_default_exposure(self):
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn("A/B 固定 EV100", (root/"templates/material-review.md").read_text(encoding="utf-8"))
        self.assertNotIn("固定相机/曝光/灯光", (root/"docs/material-families.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
