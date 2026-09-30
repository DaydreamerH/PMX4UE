import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.asset_retirement_plan import make_plan


class AssetRetirementPlanTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        project = root / "Sample.uproject"
        project.write_text("{}")
        selected = root / "Content/PMX4UE/Character/final_v2/Materials/MI_Final.uasset"
        obsolete = root / "Content/PMX4UE/Character/obsolete_v1/Materials/MI_Old.uasset"
        for path, data in ((selected, b"final"), (obsolete, b"old")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        delivery = root / "delivery.json"
        delivery.write_text(json.dumps({"schema": "pmx4ue.delivery.v2", "project": str(project),
            "assets": [{"path": "/Game/PMX4UE/Character/final_v2/Materials/MI_Final",
                        "sha256": hashlib.sha256(selected.read_bytes()).hexdigest()}]}))
        candidates = root / "candidates.json"
        data = {"schema": "pmx4ue.retirement-candidates.v1", "project": str(project),
            "candidate_namespace": "/Game/PMX4UE/Character/obsolete_v1", "protected_assets": [],
            "candidates": [{"path": "/Game/PMX4UE/Character/obsolete_v1/Materials/MI_Old",
                            "reason": "Replaced and ready for UE referencer review"}]}
        candidates.write_text(json.dumps(data))
        return delivery, candidates, data, selected, obsolete

    def test_plan_is_read_only_and_marks_referencers_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            delivery, candidates, _, selected, obsolete = self.fixture(folder)
            plan = make_plan(delivery, candidates)
            self.assertEqual(plan["status"], "review_required_no_deletion")
            self.assertEqual(plan["candidates"][0]["ue_referencers"], "pending_read_only_audit")
            self.assertEqual(selected.read_bytes(), b"final")
            self.assertEqual(obsolete.read_bytes(), b"old")

    def test_selected_protected_and_broad_targets_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            delivery, candidates, data, _, _ = self.fixture(folder)
            data["candidates"][0]["path"] = "/Game/PMX4UE/Character/final_v2/Materials/MI_Final"
            data["candidate_namespace"] = "/Game/PMX4UE/Character/final_v2"
            candidates.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Selected/protected"):
                make_plan(delivery, candidates)
            data["candidate_namespace"] = "/Game/PMX4UE"
            candidates.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "character/version-specific"):
                make_plan(delivery, candidates)

    def test_changed_selected_asset_blocks_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            delivery, candidates, _, selected, _ = self.fixture(folder)
            selected.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                make_plan(delivery, candidates)


if __name__ == "__main__":
    unittest.main()
