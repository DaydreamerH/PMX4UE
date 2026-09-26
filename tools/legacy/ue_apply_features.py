"""Apply optional feature materials for a character, in a fixed order.

Order matters: base PBR must already compile/render before outline, rim,
cloth and stocking are layered on.  Each step is independent and skips when
its preconditions are absent, so a character without stockings or a cloth
ramp still produces a valid build.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

import unreal

FRAMEWORK_DIR = Path(__file__).resolve().parent
if str(FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR))

from ue_context import BuildContext  # noqa: E402
from ue_feature_cloth import build as build_cloth  # noqa: E402
from ue_feature_depth_rim import build as build_depth_rim  # noqa: E402
from ue_feature_outline import build as build_outline  # noqa: E402
from ue_feature_stocking import build as build_stocking  # noqa: E402

DISABLED = {"off", "disabled", "none", "false", "skip"}


def _enabled(ctx, key: str) -> bool:
    feature = (ctx.config.get("features", {}) or {}).get(key, {})
    if isinstance(feature, str):
        return feature.casefold() not in DISABLED
    return str(feature.get("mode", "")).casefold() not in DISABLED


def main() -> None:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    parser.add_argument("--variant", default=os.environ.get("MMD2UE_ASSET_VARIANT", ""))
    parser.add_argument("--apply-rim-in-level", action="store_true")
    args, _ = parser.parse_known_args(argv)

    ctx = BuildContext(args.config, variant=args.variant)
    ctx.import_textures()
    results: dict[str, dict] = {}
    errors: list[str] = []

    steps = [
        ("outline", "outline", lambda: build_outline(ctx)),
        ("cloth_stylized_pbr", "cloth", lambda: build_cloth(ctx)),
        ("stocking_pbr", "stocking", lambda: build_stocking(ctx)),
        ("depth_rim", "depth_rim", lambda: build_depth_rim(ctx, apply_in_level=args.apply_rim_in_level)),
    ]
    for label, feature_key, runner in steps:
        if not _enabled(ctx, feature_key):
            results[label] = {"status": "skipped", "reason": "feature disabled"}
            continue
        try:
            results[label] = runner()
        except Exception as exc:  # keep going so a partial build is still useful
            errors.append(f"{label}: {exc}")
            results[label] = {"status": "failed", "error": str(exc)}
            traceback.print_exc()

    report = {
        "status": "success" if not errors else "partial",
        "character_id": ctx.names["character_id"],
        "engine": unreal.SystemLibrary.get_engine_version(),
        "variant": ctx.variant or "default",
        "results": results,
        "errors": errors,
    }
    ctx.report_path("ue_features_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("MMD2UE_FEATURES " + json.dumps(report, ensure_ascii=False))
    if errors:
        raise RuntimeError("character feature build failed: " + "; ".join(errors))


try:
    main()
except Exception:
    traceback.print_exc()
    raise
