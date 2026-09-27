import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.delivery_contract import review_delivery


class DeliveryContractTests(unittest.TestCase):
    def review_with_evidence(self, folder, kind, value, **extra):
        path = Path(folder) / "evidence.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return review_delivery({"schema": "pmx4ue.delivery.v1", "project": "x.uproject", "scope": ["materials"],
            "evidence": [{"id": "e", "kind": kind, "path": str(path.resolve()),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}], **extra}, "x.uproject")

    def test_old_validation_without_effective_inputs_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            report = self.review_with_evidence(folder, "material_validation", {
                "schema": "mmd2ue.ue-validation.v1", "passed": True, "slot_audit": [{"slot": "Hair"}]})
            self.assertTrue(any("effective input audit" in row for row in report["unresolved"]))

    def test_effect_comparison_requires_matching_view(self):
        # Exercise delivery matching alone; PNG validation has separate tests.
        with tempfile.TemporaryDirectory() as folder, patch("tools.delivery_contract.verify_report"):
            capture = {"captures": [
                {"case": "Baseline", "camera": {"name": "Front"}, "light": {"name": "Key"},
                 "mode": "Lit", "image": {"path": "baseline.png", "sha256": "a"}},
                {"case": "Candidate", "camera": {"name": "Side"}, "light": {"name": "Key"},
                 "mode": "Lit", "image": {"path": "candidate.png", "sha256": "b"}}],
                "input_assets": {"game_package_sha256": {}}}
            effect = {"id": "hair", "status": "reviewed", "implementation": "graph",
                      "images_opened": True, "reviewer": "agent", "observation": "changed",
                      "image_sha256": ["a", "b"]}
            report = self.review_with_evidence(folder, "capture", capture, effects=[effect])
            self.assertTrue(any("same-report/view/light/mode" in row for row in report["unresolved"]))
            capture["captures"][1]["camera"]["name"] = "Front"
            report = self.review_with_evidence(folder, "capture", capture, effects=[effect])
            self.assertFalse(any("same-report/view/light/mode" in row for row in report["unresolved"]))

    def test_no_visual_evidence_is_not_completion(self):
        report = review_delivery({"schema": "pmx4ue.delivery.v1", "project": "x.uproject", "scope": ["materials"]}, "x.uproject")
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["visual_accepted"])

    def test_upstream_risk_survives_later_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "build.json"
            path.write_text(json.dumps({"stage": "ue-build", "status": "executed_with_import_risks",
                                        "import_risks": ["zero length normal"]}))
            evidence = {"id": "base", "kind": "run", "path": str(path.resolve()),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            report = review_delivery({"schema": "pmx4ue.delivery.v1", "project": "x.uproject", "scope": ["materials"],
                                      "evidence": [evidence]}, "x.uproject")
            self.assertIn("base:zero length normal", report["import_risks"])
            self.assertTrue(any("Unresolved" in row for row in report["unresolved"]))

    def test_changed_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text("{}")
            report = review_delivery({"schema": "pmx4ue.delivery.v1", "project": "x.uproject", "scope": ["materials"],
                "evidence": [{"id": "old", "kind": "run", "path": str(path.resolve()), "sha256": "wrong"}]}, "x.uproject")
            self.assertIn("Missing/stale evidence: old", report["unresolved"])
