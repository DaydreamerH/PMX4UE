"""Offline review of rendered PIE reports; never launches UE or approves visuals.

Accepts the tests[] format emitted by ue_mmd2ue_motion_performance_pie.py.
Other collectors need an explicit adapter, not guessed field aliases.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def require_scoped_budget(review_result):
    """Reject an invalid, over-budget or undersized run without claiming game approval."""
    if review_result.get("status") != "measured_scope_pass":
        raise ValueError("Physics benchmark did not meet budget: " + str(review_result.get("status")))
    if review_result.get("viewport_target_met") is not True:
        raise ValueError("Physics benchmark viewport is below the requested target size")


def review(report, candidate, control, exit_code, repeats=3, target_size=(1920, 1080),
           minimum_average_fps=70., maximum_p99_ms=1000/60, additional_controls=()):
    if candidate == control or repeats < 3 or any(not positive(v) for v in target_size):
        raise ValueError("Use distinct candidate/control, >=3 repeats and positive target dimensions")
    if len({candidate, control, *additional_controls}) != 2 + len(additional_controls):
        raise ValueError("All benchmark cases must be distinct")
    if not positive(minimum_average_fps) or not positive(maximum_p99_ms):
        raise ValueError("Performance budgets must be finite and positive")
    errors = []
    if exit_code != 0:
        errors.append("process_exit_not_zero")
    if report.get("mode") != "rendered_PIE" or report.get("status") != "completed":
        errors.append("report_not_completed_rendered_PIE")
    if report.get("quality_changes") is not False:
        errors.append("quality_changes_or_unknown")
    if report.get("input_assets_unchanged") is not True:
        errors.append("input_assets_changed_or_unknown")
    if report.get("background_cpu_throttle") is not False or report.get("vsync") != 0:
        errors.append("throttle_or_vsync_not_confirmed_disabled")
    previous = report.get("previous_max_fps")
    if previous is None or previous != report.get("restored_max_fps"):
        errors.append("frame_cap_not_restored")
    viewport = report.get("viewport_size")
    viewport_valid = (isinstance(viewport, list) and len(viewport) == 2
                      and all(positive(v) for v in viewport))
    if not viewport_valid:
        errors.append("viewport_unknown")
    duration = report.get("seconds_per_case")
    if not positive(duration) or duration < 20:
        errors.append("measurement_duration_below_20s_or_unknown")
    warmup = report.get("warmup_seconds")
    if not positive(warmup) or warmup < 8:
        errors.append("warmup_below_8s_or_unknown")
    rows = report.get("tests", [])
    if not isinstance(rows, list):
        rows = []
        errors.append("tests_not_list")
    hashes = report.get("input_hashes", {})
    if not isinstance(hashes, dict):
        hashes = {}
    selected = {}
    for name in (control, candidate, *additional_controls):
        cases = [r for r in rows if isinstance(r, dict) and r.get("case") == name]
        selected[name] = cases
        if len(cases) < repeats:
            errors.append(name + ":insufficient_repeats")
        identities = {r.get("blueprint") for r in cases if isinstance(r.get("blueprint"), str)}
        if len(identities) != 1 or any(not hashes.get(p) for p in identities):
            errors.append(name + ":missing_or_mixed_asset_identity")
        for i, row in enumerate(cases):
            prefix = f"{name}[{i}]:"
            if row.get("measurement_valid") is not True or row.get("max_fps") != 200:
                errors.append(prefix + "invalid_measurement_or_cap")
            values = [row.get(k) for k in ("fps", "observed_fps", "mean_ms", "p99_ms", "frames")]
            if not all(positive(v) for v in values):
                errors.append(prefix + "missing_nonpositive_or_nonfinite_metrics")
                continue
            fps, observed, mean, _, frames = values
            if (abs(fps-observed)/fps >= .10 or abs(fps-1000/mean)/fps >= .01
                    or (positive(duration) and abs(observed-frames/duration)/observed >= .01)):
                errors.append(prefix + "frame_time_count_disagree")
            if row.get("blueprint") not in identities:
                errors.append(prefix + "asset_identity_missing")
    if all(selected.values()):
        if len({cases[0].get("blueprint") for cases in selected.values()}) != len(selected):
            errors.append("benchmark_cases_share_asset")
        if len({len(cases) for cases in selected.values()}) != 1:
            errors.append("unbalanced_benchmark_repeats")

    status = "invalid_measurement"
    summaries = {}
    if not errors:
        for name, cases in selected.items():
            summaries[name] = dict(
                repeats=len(cases), fps_min=min(r["fps"] for r in cases),
                fps_max=max(r["fps"] for r in cases), p99_ms_max=max(r["p99_ms"] for r in cases),
                all_runs_in_budget=all(r["fps"] >= minimum_average_fps and r["p99_ms"] <= maximum_p99_ms for r in cases))
        status = ("control_below_budget" if not summaries[control]["all_runs_in_budget"] else
                  "candidate_below_budget" if not summaries[candidate]["all_runs_in_budget"] else
                  "measured_scope_pass")
    return dict(
        schema="pmx4ue.physics_benchmark_review.v1", status=status, errors=errors,
        simulation_scope=report.get("simulation_scope", "unknown"),
        candidate=candidate, control=control, summary=summaries,
        budget=dict(minimum_average_fps=minimum_average_fps, maximum_p99_ms=maximum_p99_ms),
        viewport_size=viewport, requested_viewport_size=list(target_size),
        viewport_target_met=bool(viewport_valid and all(a >= b for a, b in zip(viewport, target_size))),
        rendering_mode=report.get("rendering_mode", "unknown"),
        screen_percentage_setting=report.get("screen_percentage"),
        scope="Only recorded PIE viewport/quality/cases; not packaged-game acceptance",
        production_accepted=False,
        pending=["Verify full mesh/skeleton/PA/animation/config dependency fingerprints",
                 "Verify actual render resolution/dynamic resolution, hardware and quality",
                 "Agent visual/contact review and movement/low-FPS numerical evidence",
                 "Target-resolution gameplay, endurance, LOD and multi-character tests"],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--control", default="NoPhysics")
    parser.add_argument("--process-exit-code", type=int, required=True,
                        help="Actual exit code from the owned UE launch, not report status")
    parser.add_argument("--target-width", type=int, default=1920)
    parser.add_argument("--target-height", type=int, default=1080)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    raw = args.report.read_bytes()
    result = review(json.loads(raw), args.candidate, args.control, args.process_exit_code,
                    target_size=(args.target_width, args.target_height))
    result.update(source_report=str(args.report.resolve()), source_report_sha256=hashlib.sha256(raw).hexdigest())
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 0 if result["status"] == "measured_scope_pass" and result["viewport_target_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
