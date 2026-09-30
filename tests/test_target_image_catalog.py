import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.target_image_catalog import discover, lookup


class TargetImageCatalogTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder) / "source"
        targets = root / "targets"
        targets.mkdir(parents=True)
        pmx = root / "model.pmx"
        pmx.write_bytes(b"pmx-fixture")
        image = targets / "reference.png"
        image.write_bytes(b"reference-fixture")
        return root, pmx, image

    def annotate(self, catalog):
        # Synthetic review data tests retrieval only; no real image is reviewed.
        image = catalog["images"][0]
        image.update(kind="target", review={"images_opened": True, "reviewer": "fixture-review",
                                           "selection_reason": "synthetic task goal"})
        image["regions"] = [{"id": "stocking_edge", "tags": ["stocking"], "features": ["edge_thickness"],
                             "observation": "fixture edge observation", "priority": "high",
                             "material_slots": [], "bbox_normalized": [0.1, 0.2, 0.6, 0.9]}]
        return catalog

    def test_discovery_is_not_semantic_review_and_reports_texture_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root, pmx, image = self.fixture(folder)
            texture = root / "cloth.png"
            texture.write_bytes(b"texture-fixture")
            manifest = Path(folder) / "manifest.json"
            manifest.write_text(json.dumps({"textures": ["cloth.png"]}))
            catalog = discover(pmx, manifest=manifest)
            self.assertEqual(len(catalog["images"]), 2)
            self.assertEqual(catalog["images"][0]["locations"][0]["path"], str(image.resolve()))
            self.assertTrue(all(row["kind"] == "candidate" and not row["review"]["images_opened"]
                                for row in catalog["images"]))
            texture_row = next(row for row in catalog["images"] if row["locations"][0]["path"] == str(texture.resolve()))
            self.assertIn("referenced_texture_in_manifest", texture_row["locations"][0]["discovery_hints"])
            self.assertEqual(lookup(catalog, ["stocking"])["matches"], [])

    def test_same_content_aliases_and_tag_region_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            root, pmx, image = self.fixture(folder)
            alias = root / "copy.png"
            alias.write_bytes(image.read_bytes())
            catalog = self.annotate(discover(pmx))
            self.assertEqual(len(catalog["images"]), 1)
            image.unlink()
            result = lookup(catalog, ["stocking"], "edge_thickness")
            self.assertEqual(len(result["matches"]), 1)
            self.assertEqual(result["matches"][0]["path"], str(alias.resolve()))
            self.assertEqual(result["matches"][0]["region"]["id"], "stocking_edge")
            self.assertEqual(lookup(catalog, ["face"])["matches"], [])
            alias.write_bytes(b"changed-content")
            self.assertEqual(lookup(catalog)["matches"], [])
            self.assertEqual(lookup(catalog)["unavailable_target_image_ids"], [catalog["images"][0]["id"]])

    def test_refresh_preserves_regions_only_for_same_image_and_model_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root, pmx, image = self.fixture(folder)
            old = self.annotate(discover(pmx))
            old_path = Path(folder) / "catalog.json"
            old_path.write_text(json.dumps(old))
            renamed = image.with_name("renamed.png")
            image.rename(renamed)
            current = discover(pmx, previous=old_path)
            self.assertEqual(current["images"][0]["id"], old["images"][0]["id"])
            self.assertEqual(current["images"][0]["regions"], old["images"][0]["regions"])
            renamed.write_bytes(b"new-reference")
            current = discover(pmx, previous=old_path)
            self.assertEqual(current["images"][0]["kind"], "candidate")
            self.assertEqual(current["removed_or_changed_image_ids"], [old["images"][0]["id"]])
            pmx.write_bytes(b"different-model")
            with self.assertRaisesRegex(ValueError, "different PMX"):
                discover(pmx, previous=old_path)
            with self.assertRaisesRegex(ValueError, "PMX missing/changed"):
                lookup(old)

    def test_no_images_is_valid_and_unreviewed_target_cannot_be_retrieved(self):
        with tempfile.TemporaryDirectory() as folder:
            root, pmx, image = self.fixture(folder)
            image.unlink()
            catalog = discover(pmx)
            self.assertEqual(catalog["status"], "no_candidates")
            self.assertEqual(lookup(catalog)["matches"], [])
            image.write_bytes(b"fixture")
            catalog = discover(pmx)
            catalog["images"][0]["kind"] = "target"
            with self.assertRaisesRegex(ValueError, "actual image review"):
                lookup(catalog)

    def test_invalid_crop_cannot_be_used_as_a_region(self):
        with tempfile.TemporaryDirectory() as folder:
            _, pmx, _ = self.fixture(folder)
            catalog = self.annotate(discover(pmx))
            for bbox in ([0.6, 0.2, 0.1, 0.9], [0, 0, 2, 1], [0, 0, float("nan"), 1]):
                catalog["images"][0]["regions"][0]["bbox_normalized"] = bbox
                with self.assertRaisesRegex(ValueError, "Invalid normalized"):
                    lookup(catalog)

    def test_cli_writes_only_new_artifact_and_query_reads_reviewed_catalog(self):
        script = Path(__file__).resolve().parents[1] / "tools/target_image_catalog.py"
        with tempfile.TemporaryDirectory() as folder:
            root, pmx, _ = self.fixture(folder)
            output = Path(folder) / "artifacts/catalog.json"
            command = [sys.executable, str(script), "discover", "--pmx", str(pmx), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            bad = command[:-1] + [str(root / "catalog.json")]
            self.assertEqual(subprocess.run(bad, capture_output=True).returncode, 2)
            self.assertFalse((root / "catalog.json").exists())
            output.write_text(json.dumps(self.annotate(json.loads(output.read_text()))))
            result = subprocess.run([sys.executable, str(script), "query", "--catalog", str(output),
                                     "--tag", "stocking"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)["matches"]), 1)


if __name__ == "__main__":
    unittest.main()
