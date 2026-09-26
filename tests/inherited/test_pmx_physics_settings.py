import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmx_physics_settings import resolve_settings, performance_verdict
from test_pmx_physics_plan import fixture
from pmx_physics_plan import make_plan


class PhysicsSettingsTests(unittest.TestCase):
    def test_legacy_defaults_stay_synchronous(self):
        result = resolve_settings({})
        self.assertEqual(result["simulation"]["timing"], "synchronous")
        self.assertEqual(result["solver"]["position_iterations"], 16)
        self.assertFalse(result["performance_test"]["enabled"])

    def test_optimized_settings_reach_plan_and_all_partitions(self):
        inv, profile, mesh = fixture()
        profile.update(solver=dict(position_iterations=8, fixed_time_step=1/60),
                       simulation=dict(timing="deferred", accept_one_frame_latency=True),
                       performance_test=dict(enabled=True))
        plan = make_plan(inv, profile, mesh)
        self.assertEqual(plan["simulation"]["timing"], "deferred")
        self.assertEqual(len(plan["performance_controls"]), 2)
        self.assertTrue(all(p["solver"]["position_iterations"] == 8 and p["solver"]["fixed_time_step"] == 1/60 for p in plan["partitions"]))

    def test_invalid_settings_rejected(self):
        for profile in [dict(simulation=dict(timing="deferred")), dict(simulation=dict(timing="magic")),
                        dict(solver=dict(position_iterations=True)), dict(solver=dict(position_iterations=0)),
                        dict(solver=dict(fixed_time_step=float("nan"))), dict(solver=dict(fixed_time_step=1)),
                        dict(solver=dict(use_linear_joint_solver="false")), dict(solver=dict(unknown=5)),
                        dict(performance_test=dict(max_fps=60)), dict(performance_test=dict(repeats=0))]:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                resolve_settings(profile)

    def records(self, p99=15):
        return [dict(case=c, fps=90, observed_frames_per_second=90, p99_ms=p99, max_fps=200, frames=5400)
                for c in ["SynchronousControl", "Candidate", "Candidate", "Candidate", "NoPhysics"]]

    def test_average_pass_is_not_full_performance_pass(self):
        policy = resolve_settings({})["performance_test"]
        verdict = performance_verdict(self.records(21), policy)
        self.assertTrue(verdict["average_fps_passed"])
        self.assertFalse(verdict["p99_passed"])
        self.assertEqual(verdict["status"], "not_met")

    def test_complete_pass_and_missing_control(self):
        policy = resolve_settings({})["performance_test"]
        self.assertEqual(performance_verdict(self.records(), policy)["status"], "passed")
        self.assertFalse(performance_verdict(self.records()[:-1], policy)["complete"])

    def test_observed_fps_and_cap_must_both_pass(self):
        policy = resolve_settings({})["performance_test"]
        rows = self.records()
        rows[1]["observed_frames_per_second"] = 40
        self.assertFalse(performance_verdict(rows, policy)["average_fps_passed"])
        rows = self.records()
        rows[1]["max_fps"] = 60
        self.assertFalse(performance_verdict(rows, policy)["cap_verified"])


if __name__ == "__main__":
    unittest.main()
