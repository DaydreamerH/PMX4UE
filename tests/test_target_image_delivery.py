import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.target_image_delivery import review_target_images


class TargetImageDeliveryTests(unittest.TestCase):
    def test_absent_target_is_allowed(self):
        issues = []
        review_target_images({}, {}, issues.append, {})
        self.assertEqual(issues, [])

    def test_supplied_target_requires_traceable_lit_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.png"
            path.write_bytes(b"reference pixels")
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            result_hash = "capture-hash"
            profile = {"target_image_review": {
                "status": "reviewed", "images_opened": True, "reviewer": "agent",
                "sources": [{"path": str(path), "sha256": source_hash}],
                "comparisons": [{"source_sha256": source_hash,
                                 "result_image_sha256": result_hash,
                                 "region": "hair", "feature": "clump highlight",
                                 "conditions": "similar front view, oblique daylight",
                                 "observation": "highlight width matches",
                                 "disposition": "matched"}]}}
            captures = {result_hash: {("report", "Baseline", "Front", "Oblique", "Lit")}}
            issues, hashes = [], {}
            review_target_images(profile, captures, issues.append, hashes)
            self.assertEqual(issues, [])
            self.assertEqual(hashes[str(path.resolve())], source_hash)
            captures[result_hash] = {("report", "Baseline", "Front", "Oblique", "Unlit")}
            review_target_images(profile, captures, issues.append, {})
            self.assertTrue(any("Lit" in issue for issue in issues))
            issues.clear()
            captures[result_hash] = {("report", "Baseline", "Front", "Oblique", "Lit")}
            profile["target_image_review"]["comparisons"][0]["disposition"] = "iterate"
            profile["target_image_review"]["comparisons"][0]["next_action"] = "narrow highlight"
            review_target_images(profile, captures, issues.append, {})
            self.assertTrue(any("iteration" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
