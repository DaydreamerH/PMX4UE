"""Generic character build orchestrator (runs inside Unreal Python).

Stages:
  import   - import FBX mesh and textures
  material - rebuild master, optional eye/glass/invisible/fringe passes,
             create per-slot instances and bind them to the mesh
  build    - import + material only (default; leave the current level untouched)
  preview/full - retired: use the isolated material-preview runner stage

Usage:
  UnrealEditor-Cmd MMD2UE.uproject -run=pythonscript -script=.../ue_build_character.py -- --config <path> [--mode build]
or set MMD2UE_CHARACTER_CONFIG and run without arguments.
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

from ue_context import BuildContext, BuildError  # noqa: E402
from ue_master_material import (  # noqa: E402
    create_bang_passes,
    create_eye_blend,
    create_glass,
    create_invisible,
    create_master,
)
from ue_material_instances import assign_materials, create_instance  # noqa: E402
from ue_preview import setup_preview  # noqa: E402


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    parser.add_argument("--mode", default=os.environ.get("MMD2UE_BUILD_MODE", "build"))
    parser.add_argument("--variant", default=os.environ.get("MMD2UE_ASSET_VARIANT", ""))
    parser.add_argument("--allow-unapproved", action="store_true")
    parser.add_argument("--no-save-level", action="store_true")
    args, _ = parser.parse_known_args(argv)
    return args


def build_special_masters(ctx, kinds):
    table = {}
    # Explicit dispatch, not name-based guessing. Dedicated graphs are built
    # before instances; later builds retain the declared parent route.
    for kind, module_name in (("stocking", "ue_feature_stocking"), ("cloth", "ue_feature_cloth")):
        if kind in kinds:
            import importlib
            slots = [e["slot"] for e in ctx.slot_entries() if ctx.special_kind_for_slot(e["slot"]) == kind]
            result = importlib.import_module(module_name).build(ctx, reparent=False, slots=slots)
            if result.get("status") != "success":
                raise BuildError(f"Required {kind} graph was not built: {result}; no fallback to Master")
            table[kind] = unreal.load_asset(result["material"])
    for alias, path in ctx.material_map.get("parent_assets", {}).items():
        if alias not in kinds:
            continue
        parent = unreal.load_asset(path)
        if not isinstance(parent, unreal.MaterialInterface):
            raise BuildError(f"Required parent {alias} is not a saved material: {path}")
        table[alias] = parent
    additive_kinds = [kind for kind in ("eye_add", "additive") if kind in kinds]
    if additive_kinds:
        additive = create_eye_blend(ctx, ctx.names["eye_add_asset"], unreal.BlendMode.BLEND_ADDITIVE)
        for kind in additive_kinds:
            table[kind] = additive
    if "eye_multiply" in kinds:
        table["eye_multiply"] = create_eye_blend(ctx, ctx.names["eye_multiply_asset"], unreal.BlendMode.BLEND_MODULATE)
    if "glass" in kinds:
        table["glass"] = create_glass(ctx)
    if "invisible" in kinds or any(entry.get("profile") == "hidden" for entry in ctx.slot_entries()):
        table["invisible"] = create_invisible(ctx)
    return table


def build_bang(ctx, specials):
    bang = (specials or {}).get("bang") or {}
    slot = bang.get("slot")
    if not slot:
        return None
    hair_base = ctx.texture_for(bang.get("hair_base")) or ctx.default_texture("base_color")
    hair_spec = ctx.texture_for(bang.get("hair_spec")) or ctx.default_texture("spec_mask")
    return {
        "slot": slot,
        "passes": create_bang_passes(
            ctx,
            hair_base,
            hair_spec,
            bang_opacity=float(bang.get("opacity", 0.82)),
            eye_opacity=float(bang.get("eye_opacity", 0.22)),
        ),
    }


def main() -> None:
    args = parse_args()
    if not args.config:
        raise BuildError("--config or MMD2UE_CHARACTER_CONFIG is required")
    mode = args.mode.strip().lower()
    if mode in {"preview", "full"}:
        raise BuildError("Legacy current-level preview is disabled. Use build, then pmx4ue.py material-preview with a reviewed profile")
    if mode not in {"import", "material", "build", "preview", "full"}:
        raise BuildError(f"unsupported build mode: {mode}")
    ctx = BuildContext(args.config, variant=args.variant, strict=not args.allow_unapproved, require_map=mode != "import")
    ctx.check_coverage()
    source_mesh = ctx.config.get("pmx4ue", {}).get("material_source_mesh")
    if source_mesh and mode != "material":
        raise BuildError("material_source_mesh requires material-build; never reimport the source mesh")
    if source_mesh:
        retained = unreal.load_asset(source_mesh)
        if not isinstance(retained, unreal.SkeletalMesh):
            raise BuildError("Retained mesh not found")
        source_slots = list(retained.get_editor_property("materials"))
        ordered = ctx.manifest_slot_names()
        if len(source_slots) != len(ordered):
            raise BuildError("Retained mesh/manifest slot count mismatch")
        for slot, name in zip(source_slots, ordered):
            names = {str(slot.get_editor_property(key)) for key in ("material_slot_name", "imported_material_slot_name")}
            if name not in names:
                raise BuildError(f"Retained slot order differs: {name} not in {names}; inspect the correct source manifest")

    report = {
        "status": "success",
        "mode": mode,
        "engine": unreal.SystemLibrary.get_engine_version(),
        "character_id": ctx.names["character_id"],
        "config": str(ctx.config_path),
        "material_map": ctx.names["material_map"],
        "variant": ctx.variant or "default",
    }

    ctx.import_textures()
    report["textures"] = len(ctx.texture_map)

    mesh = ctx.import_skeletal_mesh() if mode in ("import", "build", "full") else unreal.EditorAssetLibrary.load_asset(
        source_mesh or f"{ctx.names['mesh_root']}/{ctx.names['mesh_asset']}"
    )
    if mode in ("material", "build", "full") and not isinstance(mesh, unreal.SkeletalMesh):
        mesh = unreal.EditorAssetLibrary.load_asset(f"{ctx.names['mesh_root']}/{ctx.names['mesh_asset']}")
    if mode in ("material", "build", "full", "preview") and not isinstance(mesh, unreal.SkeletalMesh):
        raise BuildError("skeletal mesh is not available; run import mode first")
    if isinstance(mesh, unreal.SkeletalMesh):
        report["skeletal_mesh"] = mesh.get_path_name()

    if mode in ("material", "build", "full"):
        master = create_master(ctx, ctx.texture_map)
        report["master_material"] = master.get_path_name()

        kinds = {ctx.special_kind_for_slot(entry["slot"]) for entry in ctx.slot_entries()}
        special_masters = build_special_masters(ctx, kinds)
        special_masters["master"] = master
        report["special_masters"] = {kind: mat.get_path_name() for kind, mat in special_masters.items() if mat}

        bang = build_bang(ctx, ctx.material_map.get("specials"))
        if bang:
            report["bang"] = {"slot": bang["slot"], "invisible": bang["passes"][0].get_path_name()}

        instances = {}
        for entry in ctx.slot_entries():
            instances[entry["slot"]] = create_instance(ctx, master, entry, special_masters)
        report["material_instances"] = len(instances)
        if source_mesh:
            ordered = ctx.manifest_slot_names()
            if len(mesh.get_editor_property("materials")) != len(ordered):
                raise BuildError("Source mesh and manifest slot counts differ")
            report["component_overrides"] = [{"index": i, "slot": slot, "material": instances[slot].get_path_name()}
                                             for i, slot in enumerate(ordered)]
            report["assigned_slots"] = 0
            report["binding_scope"] = "unassigned_component_overrides"
        else:
            report["assigned_slots"] = assign_materials(ctx, mesh, instances)
        report["material_routes"] = [{"slot": e["slot"], "profile": e["profile"],
                                      "route": ctx.special_kind_for_slot(e["slot"]) or "master",
                                      "parent": instances[e["slot"]].get_editor_property("parent").get_path_name()}
                                     for e in ctx.slot_entries()]
        report["material_quality"] = "built_visual_pending"
        report["input_audit"] = ctx.input_audit
        report["material_debt"] = ctx.material_debt

    if mode in ("preview", "full"):
        report["preview"] = setup_preview(ctx, mesh)
        if not args.no_save_level:
            try:
                unreal.EditorLevelLibrary.save_current_level()
            except Exception as exc:  # a default Untitled level may refuse to save
                report["preview_save"] = f"skipped: {exc}"

    Path(ctx.names["ue_build_report"]).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("MMD2UE_BUILD " + json.dumps(report, ensure_ascii=False))


try:
    main()
except Exception:
    traceback.print_exc()
    raise
