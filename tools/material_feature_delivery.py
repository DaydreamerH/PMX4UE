"""Explicit lookdev decisions and game-use evidence, not automatic art approval."""
import hashlib
import math
from pathlib import Path

FEATURES = {
    "eye_layers": ("geometry_layers", "highlight_shadow", "side_view"),
    "hair_clumps": ("uv_direction", "clump_shape", "view_light_response"),
    "stocking_edge": ("surface_layers", "edge_color", "highlight_response"),
}
GAME_CHECKS = ("occlusion", "distance_lod", "motion", "lighting", "multi_instance", "performance")


def has_refs(row, reports):
    refs = row.get("evidence", [])
    return bool(refs) and all(r in reports for r in refs)


def review_material_features(profile, slots, reports, captures, issue):
    if profile.get("material_review_contract") not in {1, 2}:
        issue("Material review contract 1 or 2 required: migrate feature decisions and acceptance scope")
    if profile.get("material_acceptance") not in {"static_lookdev", "game_ready"}:
        issue("Choose material_acceptance=static_lookdev or game_ready; static screenshots are not game validation")
    features = profile.get("material_features", {})
    effects = {e.get("id"): e for e in profile.get("effects", [])}
    for name, observations in FEATURES.items():
        row = features.get(name, {})
        target = row.get("slots", [])
        if not row.get("reason") or not has_refs(row, reports):
            issue(f"Material feature {name}: model-specific decision and source/design evidence required")
        if row.get("status") == "not_applicable":
            if target:
                issue(f"Material feature {name}: existing target slots need implementation or explicit scope limitation")
            continue
        if not target or len(set(target)) != len(target) or not set(target) <= set(slots):
            issue(f"Material feature {name}: identify actual, unique target slots")
        if row.get("status") == "accepted_limitation":
            if not row.get("scope_approval"):
                issue(f"Material feature {name}: scope limitation requires user approval, not optional-tool status")
            continue
        if row.get("status") != "reviewed":
            issue(f"Material feature unfinished: {name}; next={row.get('next_action')}")
            continue
        effect = effects.get(row.get("effect"), {})
        if (effect.get("status") != "reviewed" or not set(target) <= set(effect.get("slots", [])) or
                effect.get("comparison_required", True) is not True):
            issue(f"Material feature {name}: requires its reviewed slot-specific A/B effect")
        notes = row.get("observations", {})
        if any(not isinstance(notes.get(k), str) or not notes[k].strip() for k in observations):
            issue(f"Material feature {name}: missing regional/algorithm observations {observations}")
        # Two candidate Lit views in one report/case. Shared effects remain legal
        # for real shared graphs, but cannot omit this family's observations.
        views = {}
        for h in effect.get("image_sha256", []):
            for report, case, camera, light, mode in captures.get(h, set()):
                if mode == "Lit" and case != "Baseline":
                    views.setdefault((report, case), set()).add(camera)
        if not any(len(v) >= 2 for v in views.values()):
            issue(f"Material feature {name}: needs >=2 candidate Lit views (close front/oblique), not only a full-body baseline")


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def review_scene_gameplay(profile, reports, issue):
    """Static delivery may explicitly defer gameplay; game-ready cannot."""
    for name in ("outline", "rim"):
        row = profile.get("scene_effects", {}).get(name, {})
        if row.get("status") == "not_selected":
            continue
        game = row.get("game_validation", {})
        if game.get("status") in {"pending", "blocked"}:
            if not game.get("next_action") or not game.get("reason"):
                issue(f"Scene gameplay {name}: pending needs reason and next_action")
            if profile.get("material_acceptance") == "game_ready":
                issue(f"Scene gameplay {name}: unfinished; cannot claim game_ready")
            continue
        if game.get("status") != "reviewed":
            issue(f"Scene gameplay {name}: declare pending/blocked/reviewed separately from screenshots")
            continue
        for check in GAME_CHECKS:
            ident = game.get("checks", {}).get(check)
            kind, report = reports.get(ident, (None, None))
            if (kind != "material_game_test" or not isinstance(report, dict) or
                    report.get("schema") != "pmx4ue.material-game-test.v1" or report.get("check") != check or
                    name not in report.get("effects", []) or report.get("passed") is not True or
                    not report.get("observation") or not report.get("reviewer") or
                    not has_refs(report, reports) or ident in report.get("evidence", [])):
                issue(f"Scene gameplay {name}/{check}: needs matching test report and raw evidence, not a success checkbox")
                continue
            if Path(report.get("project", "")).resolve() != Path(profile.get("project", "")).resolve():
                issue(f"Scene gameplay {name}/{check}: wrong project")
            recorded = report.get("asset_sha256", {})
            selected = {a.get("path"): a.get("sha256") for a in profile.get("assets", [])}
            if not selected or any(recorded.get(p) != h for p, h in selected.items()):
                issue(f"Scene gameplay {name}/{check}: report does not cover selected asset combination")
            # Include parent graphs, runtime BP and other dependencies as well.
            for package, expected in recorded.items():
                if not isinstance(package, str) or not package.startswith("/Game/") or ".." in package:
                    issue(f"Scene gameplay {name}/{check}: invalid package fingerprint")
                    continue
                path = Path(profile.get("project", "")).parent / "Content" / (package[6:].split('.')[0] + ".uasset")
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    issue(f"Scene gameplay {name}/{check}: changed/missing asset {package}")
            if check == "performance":
                review_cost(report, name, issue)


def review_cost(report, name, issue):
    pairs = report.get("measurements", {})
    off, on = pairs.get("off", {}), pairs.get("on", {})
    if (off.get("active_effects") != [] or not report.get("effects") or
            set(on.get("active_effects", [])) != set(report["effects"])):
        issue(f"Scene gameplay {name}/performance: record the actual off/on effect switches")
    conditions = ("hardware", "resolution", "quality", "camera_path", "animation", "actor_count", "physics", "exposure_policy", "engine", "execution_mode")
    for key in conditions:
        if off.get(key) is None or off.get(key) == "" or off.get(key) != on.get(key):
            issue(f"Scene gameplay {name}/performance: unmatched/missing {key}")
    for label, sample in (("off", off), ("on", on)):
        if (sample.get("max_fps") != 200 or sample.get("vsync") is not False or
                not positive(sample.get("duration_seconds")) or type(sample.get("frames")) is not int or sample.get("frames", 0) < 2 or
                not positive(sample.get("warmup_seconds"))):
            issue(f"Scene gameplay {name}/performance: {label} needs measured samples, warmup, t.MaxFPS=200 and VSync off")
        if type(sample.get("actor_count")) is not int or sample.get("actor_count", 0) < 1:
            issue(f"Scene gameplay {name}/performance: invalid actor count")
        for metric in ("frame_p95_ms", "frame_p99_ms", "gpu_p95_ms", "game_p95_ms"):
            if not positive(sample.get(metric)):
                issue(f"Scene gameplay {name}/performance: missing/invalid {label}.{metric}")
        if (positive(sample.get("frame_p99_ms")) and positive(sample.get("frame_p95_ms")) and
                sample["frame_p99_ms"] < sample["frame_p95_ms"]):
            issue(f"Scene gameplay {name}/performance: invalid frame percentiles")
    budget = report.get("budget", {})
    for key in ("frame_p99_ms", "added_gpu_p95_ms"):
        if not positive(budget.get(key)):
            issue(f"Scene gameplay {name}/performance: explicit positive {key} budget required")
    if positive(on.get("frame_p99_ms")) and positive(budget.get("frame_p99_ms")) and on["frame_p99_ms"] > budget["frame_p99_ms"]:
        issue(f"Scene gameplay {name}/performance: frame-time budget exceeded")
    if all(positive(x) for x in (on.get("gpu_p95_ms"), off.get("gpu_p95_ms"), budget.get("added_gpu_p95_ms"))):
        if on["gpu_p95_ms"] - off["gpu_p95_ms"] > budget["added_gpu_p95_ms"]:
            issue(f"Scene gameplay {name}/performance: added GPU budget exceeded")
