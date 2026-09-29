import unittest

from tools.light_direction_delivery import review_light_direction
from tools.delivery_contract import review_delivery


class LightDirectionReviewTests(unittest.TestCase):
    def fixture(self):
        hashes = ["default", "side"]
        profile = {"material_review_contract": 2,
            "effects": [{"id": "hair", "status": "reviewed", "image_sha256": hashes}],
            "light_direction_review": {"status": "reviewed", "effect": "hair",
                "reason": "Hair highlights move with the sun", "images_opened": True,
                "reviewer": "agent", "image_sha256": hashes,
                "observations": {"shadow_transition": "smooth", "highlight_response": "moves to edge",
                                 "failure_or_limitation": "none seen in this static view"}}}
        capture = {"profile": {"lights": [{"name": "Daylight"}, {"name": "Side", "yaw_offset": 45}]},
                   "captures": [
                       {"image": {"sha256": "default"}, "case": "Candidate", "camera": {"name": "Close"},
                        "light": {"name": "Daylight"}, "mode": "Lit", "actual_sun": {"pitch": 30, "yaw": 10}},
                       {"image": {"sha256": "side"}, "case": "Candidate", "camera": {"name": "Close"},
                        "light": {"name": "Side"}, "mode": "Lit", "actual_sun": {"pitch": 30, "yaw": 55}}]}
        return profile, {"capture": ("capture", capture)}

    def issues(self, profile, reports):
        issues = []
        review_light_direction(profile, reports, issues.append)
        return issues

    def test_changed_sun_passes_and_old_contract_is_not_retroactively_broken(self):
        profile, reports = self.fixture()
        self.assertEqual(self.issues(profile, reports), [])
        profile["material_review_contract"] = 1
        profile.pop("light_direction_review")
        self.assertEqual(self.issues(profile, reports), [])

    def test_named_side_light_without_actual_rotation_fails(self):
        profile, reports = self.fixture()
        reports["capture"][1]["captures"][1]["actual_sun"]["yaw"] = 10
        self.assertTrue(any("actual sun change" in x for x in self.issues(profile, reports)))

    def test_different_case_or_camera_cannot_fake_matched_turn_light(self):
        profile, reports = self.fixture()
        reports["capture"][1]["captures"][1]["camera"]["name"] = "Other"
        self.assertTrue(self.issues(profile, reports))

    def test_missing_default_or_unopened_images_fail(self):
        profile, reports = self.fixture()
        profile["light_direction_review"]["images_opened"] = False
        self.assertTrue(any("opened Lit" in x for x in self.issues(profile, reports)))
        profile["light_direction_review"]["images_opened"] = True
        reports["capture"][1]["captures"][0]["light"]["name"] = "Other"
        self.assertTrue(self.issues(profile, reports))

    def test_delivery_contract_two_cannot_skip_light_review(self):
        result = review_delivery({"schema": "pmx4ue.delivery.v2", "project": "sample.uproject",
                                  "scope": ["materials"], "material_review_contract": 2}, "sample.uproject")
        self.assertTrue(any("Light-direction review is missing" in x for x in result["unresolved"]))


if __name__ == "__main__":
    unittest.main()
