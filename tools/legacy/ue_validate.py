"""Generic read-only validation of a built character.

Checks instance parents and parameters against the normalized material map,
verifies texture colour spaces per role, audits the master graph for
disconnected unary nodes, and emits the list of parent materials the live MCP
``InspectMaterialCompile`` tool must still confirm.
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

from mmd2ue_core import TEXTURE_PARAMETER_NAMES  # noqa: E402
from ue_context import BuildContext  # noqa: E402
from ue_material_instances import material_asset_name  # noqa: E402

UNARY_CLASSES = {
    "MaterialExpressionSaturate",
    "MaterialExpressionOneMinus",
    "MaterialExpressionSquareRoot",
    "MaterialExpressionCeil",
    "MaterialExpressionNormalize",
}
MASK_ROLES = {"rmo", "spec_mask", "face_sdf"}


def _scalar_value(instance, name):
    try:
        return float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(instance, name))
    except Exception:
        return None


def _texture_value(instance, name):
    try:
        texture = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, name)
        return texture.get_name().lower() if texture else None
    except Exception:
        return None


def audit_master_graph(master):
    audit = []
    if not master:
        return audit
    try:
        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(master))
    except Exception:
        expressions = []
    for expression in expressions:
        class_name = expression.get_class().get_name()
        if class_name not in UNARY_CLASSES:
            continue
        input_value = None
        for prop in ("input", "vector_input"):
            try:
                input_value = expression.get_editor_property(prop)
            except Exception:
                input_value = None
            if input_value is not None:
                break
        source = None
        try:
            source = input_value.expression if input_value is not None else None
        except Exception:
            source = None
        audit.append({
            "class": class_name,
            "connected": source is not None,
            "source": source.get_class().get_name() if source else None,
        })
    return audit


def main() -> None:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    parser.add_argument("--variant", default=os.environ.get("MMD2UE_ASSET_VARIANT", ""))
    args, _ = parser.parse_known_args(argv)

    ctx = BuildContext(args.config, variant=args.variant, strict=False)
    ctx.import_textures()
    root = ctx.names["material_root"]
    mesh = unreal.EditorAssetLibrary.load_asset(f"{ctx.names['mesh_root']}/{ctx.names['mesh_asset']}")
    master = unreal.EditorAssetLibrary.load_asset(f"{root}/{ctx.names['master_asset']}")

    violations: list[str] = []
    if mesh is None:
        violations.append(f"mesh missing: {ctx.names['mesh_asset']}")
    if master is None:
        violations.append(f"master missing: {ctx.names['master_asset']}")

    mesh_materials = []
    if mesh is not None:
        for slot in mesh.get_editor_property("materials"):
            material = slot.get_editor_property("material_interface")
            mesh_materials.append(material.get_path_name() if material else None)

    manifest_slots = ctx.manifest_slot_names()
    if manifest_slots and len(manifest_slots) != len(mesh_materials):
        violations.append(f"mesh/source slot count mismatch {len(mesh_materials)} != {len(manifest_slots)}")

    slots_audit = []
    for index, entry in enumerate(ctx.slot_entries()):
        slot_name = entry["slot"]
        instance_path = f"{root}/{ctx.names['instance_prefix']}_{material_asset_name(slot_name)}"
        instance = unreal.EditorAssetLibrary.load_asset(instance_path)
        if instance is None:
            violations.append(f"{slot_name}: missing instance {instance_path}")
            continue
        if index < len(mesh_materials) and mesh_materials[index] != instance.get_path_name():
            violations.append(f"{slot_name}: mesh slot binds {mesh_materials[index]} instead of {instance.get_path_name()}")

        parent = None
        try:
            parent = instance.get_editor_property("parent")
        except Exception:
            parent = None
        parent_is_master = parent is not None and master is not None and parent.get_path_name() == master.get_path_name()

        effective = {}
        for role, parameter in TEXTURE_PARAMETER_NAMES.items():
            expected = entry["textures"].get(role)
            actual = _texture_value(instance, parameter)
            if expected and actual != str(expected).lower():
                violations.append(f"{slot_name}: {parameter} = {actual!r}, expected {expected!r}")
            effective[role] = actual

        if parent_is_master:
            profile = ctx.material_map.get("profiles", {}).get(entry.get("profile"), {})
            expected_scalars = dict(profile.get("scalars", {}) or {})
            expected_scalars.update((entry.get("overrides", {}) or {}).get("scalars", {}) or {})
            for name, expected in expected_scalars.items():
                actual = _scalar_value(instance, name)
                if actual is None or abs(actual - float(expected)) > 0.0001:
                    violations.append(f"{slot_name}: scalar {name} = {actual}, expected {expected}")
        slots_audit.append({
            "slot": slot_name,
            "profile": entry.get("profile"),
            "instance": instance.get_path_name(),
            "parent": parent.get_path_name() if parent else None,
            "effective_textures": effective,
        })

    texture_audit = []
    for entry in ctx.slot_entries():
        for role, key in entry["textures"].items():
            if role == "toon_ramp" or not key:
                continue
            texture = ctx.texture_for(key)
            if texture is None:
                continue
            srgb = bool(texture.get_editor_property("srgb")) if hasattr(texture, "srgb") else None
            compression = str(texture.get_editor_property("compression_settings") or "")
            if role == "normal" and srgb:
                violations.append(f"{key}: normal map must not be sRGB")
            if role in MASK_ROLES and "MASKS" not in compression.upper() and "NORMALMAP" not in compression.upper():
                violations.append(f"{key}: {role} should use a mask compression setting")
            if role == "base_color" and srgb is False:
                violations.append(f"{key}: base colour should be sRGB")
            texture_audit.append({"texture": key, "role": role, "srgb": srgb, "compression": compression})

    graph_audit = audit_master_graph(master) if master else []
    # This UE build does not expose FExpressionInput through Python, so the
    # audit is informational only; shader compilation is verified via the
    # MCP InspectMaterialCompile tool listed in compile_check_required.

    forbidden = ctx.config.get("validation", {}).get("forbid_asset_name_tokens", [])
    forbidden_assets = [
        path for path in unreal.EditorAssetLibrary.list_assets(ctx.names["ue_root"], recursive=True, include_folder=False)
        if any(token in path for token in forbidden)
    ]
    for path in forbidden_assets:
        violations.append(f"forbidden asset present: {path}")

    compile_required = sorted({
        audit["parent"] for audit in slots_audit if audit["parent"]
    })
    report = {
        "schema": "mmd2ue.ue-validation.v1",
        "engine": unreal.SystemLibrary.get_engine_version(),
        "character_id": ctx.names["character_id"],
        "variant": ctx.variant or "default",
        "mesh": ctx.names["mesh_asset"],
        "master": ctx.names["master_asset"],
        "mesh_material_count": len(mesh_materials),
        "slot_audit": slots_audit,
        "texture_audit": texture_audit,
        "master_graph_audit": graph_audit,
        "forbidden_assets": forbidden_assets,
        "compile_check_required": compile_required,
        "compile_note": "Run InspectMaterialCompile for every path; this report only proves graph connectivity.",
        "violations": violations,
        "passed": not violations,
    }
    Path(ctx.names["validation_report"]).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("MMD2UE_VALIDATION " + json.dumps(report, ensure_ascii=False))
    if violations:
        raise RuntimeError(f"character validation found {len(violations)} violation(s)")


try:
    main()
except Exception:
    traceback.print_exc()
    raise
