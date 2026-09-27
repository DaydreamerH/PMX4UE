"""Validated pipeline runtime settings and honest performance acceptance gates."""
import math


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value, lo, hi, label):
    require(type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi,
            "Invalid " + label)
    return value


def resolve_settings(profile):
    solver = dict(position_iterations=16, fixed_time_step=1/120,
                  max_depenetration_velocity=0., use_linear_joint_solver=False)
    supplied = profile.get("solver", {})
    require(isinstance(supplied, dict) and not set(supplied)-set(solver), "Unknown solver setting")
    solver.update(supplied)
    require(type(solver["position_iterations"]) is int, "Position iterations must be integer")
    number(solver["position_iterations"], 1, 64, "position iterations")
    number(solver["fixed_time_step"], 1/240, 1/15, "fixed physics time step")
    number(solver["max_depenetration_velocity"], 0, 10000, "depenetration velocity")
    require(type(solver["use_linear_joint_solver"]) is bool, "Linear solver flag must be boolean")
    simulation = dict(timing="synchronous", accept_one_frame_latency=False,
                      space="component", base_bone="", world_alpha=1., damping_alpha=0.,
                      max_linear_velocity=1e10, max_linear_acceleration=1e10,
                      max_angular_velocity=1e10, max_angular_acceleration=1e10)
    supplied = profile.get("simulation", {})
    require(isinstance(supplied, dict) and not set(supplied)-set(simulation), "Unknown simulation setting")
    simulation.update(supplied)
    require(simulation["timing"] in ("synchronous", "deferred"), "Unknown simulation timing")
    require(type(simulation["accept_one_frame_latency"]) is bool, "Latency acceptance must be boolean")
    require(simulation["timing"] != "deferred" or simulation["accept_one_frame_latency"],
            "Deferred simulation requires explicit one-frame latency acceptance")
    require(simulation["space"] in ("component", "base_bone", "world"), "Unknown simulation space")
    require(isinstance(simulation["base_bone"], str), "Base bone must be a name")
    require(bool(simulation["base_bone"]) == (simulation["space"] == "base_bone"), "Base bone required only in base_bone space")
    for key in ("world_alpha", "damping_alpha"):
        number(simulation[key], 0, 1, key)
    for key in ("max_linear_velocity", "max_linear_acceleration", "max_angular_velocity", "max_angular_acceleration"):
        number(simulation[key], 0, 1e10, key)
    perf = dict(enabled=False, max_fps=200, seconds=60, repeats=3,
                viewport_width=1920, viewport_height=1080,
                minimum_average_fps=70., maximum_p99_ms=1000/60)
    supplied = profile.get("performance_test", {})
    require(isinstance(supplied, dict) and not set(supplied)-set(perf), "Unknown performance setting")
    perf.update(supplied)
    require(type(perf["enabled"]) is bool, "Performance enabled flag must be boolean")
    require(perf["max_fps"] == 200, "Performance tests require t.MaxFPS 200")
    number(perf["seconds"], 10, 600, "performance duration")
    require(type(perf["repeats"]) is int, "Performance repeats must be integer")
    number(perf["repeats"], 1, 10, "performance repeats")
    for key in ("viewport_width", "viewport_height"):
        require(type(perf[key]) is int, "Viewport dimensions must be integers")
        number(perf[key], 64, 4320 if key == "viewport_height" else 7680, key)
    if perf["enabled"]:
        require(perf["repeats"] >= 3 and perf["seconds"] >= 20, "Enabled acceptance requires three repeats and 20 measured seconds")
    number(perf["minimum_average_fps"], 60, 199, "average FPS target")
    number(perf["maximum_p99_ms"], 5, 1000/60, "P99 target")
    return dict(solver=solver, simulation=simulation, performance_test=perf)


def performance_verdict(tests, policy):
    rows = [r for r in tests if r["case"] == "Candidate"]
    complete = (len(rows) == policy["repeats"] and len(tests) == policy["repeats"]+2
                and sum(r["case"] == "SynchronousControl" for r in tests) == 1
                and sum(r["case"] == "NoPhysics" for r in tests) == 1
                and all(r.get("frames", 0) > 0 for r in tests))
    cap_ok = complete and all(r.get("max_fps") == 200 for r in tests)
    average = cap_ok and all(r["fps"] >= policy["minimum_average_fps"]
                            and r["observed_frames_per_second"] >= policy["minimum_average_fps"] for r in rows)
    tail = cap_ok and all(r["p99_ms"] <= policy["maximum_p99_ms"] for r in rows)
    return dict(status="passed" if average and tail else "not_met", complete=complete,
                cap_verified=cap_ok, average_fps_passed=average, p99_passed=tail,
                scope="PIE only; visual approval and packaged-game validation remain separate")
