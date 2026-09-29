"""Build only explicitly selected scene-effect assets; never mutate a level."""
import json
import os
from pathlib import Path
import unreal
from ue_context import BuildContext
from ue_feature_outline import build as build_outline
from ue_feature_depth_rim import build as build_depth_rim


def main():
    output = Path(os.environ["PMX4UE_OUTPUT"])
    if output.exists():
        raise RuntimeError("Scene-effect report exists; select a new variant")
    ctx = BuildContext(os.environ["PMX4UE_CONFIG"])
    results, steps = {}, []
    for name, build in (("outline", build_outline), ("depth_rim", build_depth_rim)):
        if (ctx.config.get("features", {}).get(name) or {}).get("mode") != "enabled":
            continue
        root, prefix = ctx.names["material_root"], ctx.names["instance_prefix"]
        key = "outline_asset" if name == "outline" else "rim_asset"
        suffixes = ("Outline", "Outline_Face", "Outline_Hair") if name == "outline" else ("DepthRim",)
        paths = [root + "/" + ctx.names[key]] + [root + "/" + prefix + "_" + s for s in suffixes]
        if any(unreal.EditorAssetLibrary.does_asset_exist(path) for path in paths):
            raise RuntimeError("Scene-effect asset exists; choose a new variant: " + name)
        if ctx.report_path(name + "_build_report.json").exists():
            raise RuntimeError("Scene-effect build report exists; choose a new variant: " + name)
        steps.append((name, build))
    for name, build in steps:
        results[name] = build(ctx)
    if not results:
        raise RuntimeError("No explicitly enabled scene effects")
    output.write_text(json.dumps(dict(status="built_visual_pending", results=results,
        applied_to_scene=False, next="Add separate outline/depth_rim cases to material-preview; no current-level writes"),
        ensure_ascii=False, indent=2), encoding="utf-8")


main()
