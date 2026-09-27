import copy
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.review_physics_benchmark import main, review


def fixture():
    row = dict(fps=100., observed_fps=100., mean_ms=10., p99_ms=12., frames=2000,
               measurement_valid=True, max_fps=200)
    return dict(mode="rendered_PIE", status="completed", quality_changes=False,
                input_assets_unchanged=True, background_cpu_throttle=False, vsync=0,
                previous_max_fps=0, restored_max_fps=0, viewport_size=[655, 325],
                seconds_per_case=20, warmup_seconds=8,
                input_hashes={"/Game/Control": "a", "/Game/Candidate": "b"},
                tests=[dict(row, case=n, blueprint="/Game/"+n)
                       for _ in range(3) for n in ("Control", "Candidate")])


class PhysicsBenchmarkReviewTests(unittest.TestCase):
    def check(self, report):
        return review(report, "Candidate", "Control", 0)

    def test_small_viewport_is_only_scoped_pass(self):
        r = self.check(fixture())
        self.assertEqual(r["status"], "measured_scope_pass")
        self.assertFalse(r["viewport_target_met"])
        self.assertFalse(r["production_accepted"])

    def test_large_viewport_is_not_production_pass(self):
        data = fixture()
        data["viewport_size"] = [1920, 1080]
        r = self.check(data)
        self.assertTrue(r["viewport_target_met"])
        self.assertFalse(r["production_accepted"])

    def test_p99_cannot_be_hidden_by_average(self):
        data = fixture()
        data["tests"][1]["p99_ms"] = 22
        self.assertEqual(self.check(data)["status"], "candidate_below_budget")

    def test_bad_control_not_solver_failure(self):
        data = fixture()
        data["tests"][0]["p99_ms"] = 30
        self.assertEqual(self.check(data)["status"], "control_below_budget")

    def test_invalid_and_missing_evidence(self):
        for key, value in (("status", "running"), ("vsync", 1), ("input_assets_unchanged", False),
                           ("background_cpu_throttle", True), ("viewport_size", None),
                           ("restored_max_fps", 60), ("seconds_per_case", 2),
                           ("warmup_seconds", None), ("input_hashes", {})):
            with self.subTest(key=key):
                data = fixture()
                data[key] = value
                self.assertEqual(self.check(data)["status"], "invalid_measurement")

    def test_corrupt_metrics(self):
        for key, value in (("fps", float("nan")), ("p99_ms", float("inf")),
                           ("frames", 2), ("observed_fps", 2), ("mean_ms", 1),
                           ("max_fps", 60), ("blueprint", None), ("measurement_valid", False)):
            with self.subTest(key=key):
                data = fixture()
                data["tests"][1][key] = value
                self.assertEqual(self.check(data)["status"], "invalid_measurement")

    def test_missing_repeat_and_crashed_process(self):
        data = fixture()
        data["tests"].pop()
        self.assertEqual(self.check(data)["status"], "invalid_measurement")
        self.assertEqual(review(fixture(), "Candidate", "Control", -1073741819)["status"], "invalid_measurement")

    def test_same_asset_is_not_a_control(self):
        data = fixture()
        for row in data["tests"]:
            row["blueprint"] = "/Game/Candidate"
        self.assertEqual(self.check(data)["status"], "invalid_measurement")

    def test_review_does_not_mutate_input(self):
        data = fixture()
        original = copy.deepcopy(data)
        self.check(data)
        self.assertEqual(data, original)

    def test_cli_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(StringIO()):
            source, output = Path(tmp)/"raw.json", Path(tmp)/"review.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            args = [str(source), "--candidate", "Candidate", "--control", "Control",
                    "--process-exit-code", "0", "--output", str(output)]
            self.assertEqual(main(args), 2)  # Small viewport is not requested 1080p.
            self.assertEqual(len(json.loads(output.read_text())["source_report_sha256"]), 64)
            with self.assertRaises(FileExistsError):
                main(args)
            self.assertEqual(main(args[:-2] + ["--target-width", "655", "--target-height", "325"]), 0)
