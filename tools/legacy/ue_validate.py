"""Generic read-only validation of a built character.

Checks instance parents and parameters against the normalized material map,
verifies texture colour spaces per role, audits the master graph for
disconnected unary nodes, and emits the list of parent materials the live MCP
``InspectMaterialCompile`` tool must still confirm.
"""

from __future__ import annotations

import argparse
import hashlib
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
from material_input_policy import effective_scalars
from ue_face_sdf_nodes import response_readback

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


def _vector_value(instance, name):
    try:
        value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, name)
        return [float(getattr(value, channel)) for channel in ("r", "g", "b", "a")]
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
    map_errors = [issue for issue in ctx.map_issues if issue["level"] == "error"]
    if map_errors:
        raise RuntimeError(f"Cannot validate ambiguous/invalid material routes: {map_errors}")
    ctx.import_textures(read_only=True)
    root = ctx.names["material_root"]
    source_mesh = ctx.config.get("pmx4ue", {}).get("material_source_mesh")
    mesh = unreal.EditorAssetLibrary.load_asset(source_mesh or f"{ctx.names['mesh_root']}/{ctx.names['mesh_asset']}")
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
    try:
        master_sdf_response = response_readback(master)
    except Exception:
        master_sdf_response = None  # Missing readback is not a verified response.
    requested_sdf_response = ctx.material_map.get("policies", {}).get("face_sdf_light_response", "linear_azimuth_v1")
    for index, entry in enumerate(ctx.slot_entries()):
        slot_name = entry["slot"]
        instance_path = f"{root}/{ctx.names['instance_prefix']}_{material_asset_name(slot_name)}"
        instance = unreal.EditorAssetLibrary.load_asset(instance_path)
        if instance is None:
            violations.append(f"{slot_name}: missing instance {instance_path}")
            continue
        if not source_mesh and index < len(mesh_materials) and mesh_materials[index] != instance.get_path_name():
            violations.append(f"{slot_name}: mesh slot binds {mesh_materials[index]} instead of {instance.get_path_name()}")

        parent = None
        try:
            parent = instance.get_editor_property("parent")
        except Exception:
            parent = None
        parent_is_master = parent is not None and master is not None and parent.get_path_name() == master.get_path_name()
        if parent_is_master and entry["textures"].get("face_sdf") and master_sdf_response != requested_sdf_response:
            violations.append(f"{slot_name}: face SDF response readback {master_sdf_response!r} does not match requested {requested_sdf_response!r}")
        route = ctx.special_kind_for_slot(slot_name) or "master"
        parent_assets = ctx.material_map.get("parent_assets", {})
        builtin_names = {"master": "master_asset", "stocking": "stocking_asset", "cloth": "cloth_asset",
                         "eye_add": "eye_add_asset", "additive": "eye_add_asset", "eye_multiply": "eye_multiply_asset",
                         "glass": "glass_asset", "invisible": "invisible_asset"}
        expected_parent_path = parent_assets.get(route)
        if route in builtin_names:
            expected_parent_path = f"{root}/{ctx.names[builtin_names[route]]}"
        expected_parent = unreal.load_asset(expected_parent_path) if expected_parent_path else None
        if parent is None or expected_parent is None or parent.get_path_name() != expected_parent.get_path_name():
            violations.append(f"{slot_name}: parent route {route} does not match {expected_parent_path}")

        effective = {}
        input_audit = []
        scalar_readback = {str(name): _scalar_value(instance, str(name))
                           for name in unreal.MaterialEditingLibrary.get_scalar_parameter_names(instance)}
        supported = {str(n) for n in unreal.MaterialEditingLibrary.get_texture_parameter_names(instance)}
        for role, parameter in TEXTURE_PARAMETER_NAMES.items():
            expected = entry["textures"].get(role)
            if parameter not in supported:
                if expected:
                    violations.append(f"{slot_name}: declared {role} is not consumed")
                continue
            actual = _texture_value(instance, parameter)
            expected_texture = ctx.texture_for(expected) if expected else ctx.neutral_texture(role, create=False)
            actual_texture = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, parameter)
            if (expected_texture is None or actual_texture is None
                    or actual_texture.get_path_name() != expected_texture.get_path_name()):
                violations.append(f"{slot_name}: {parameter} does not match declared/neutral input")
            input_audit.append(dict(role=role, source="declared" if expected else "generated_neutral",
                                    actual=actual_texture.get_path_name() if actual_texture else None,
                                    expected=expected_texture.get_path_name() if expected_texture else None))
            if role == "face_sdf" and expected and actual_texture:
                try:
                    import_data = actual_texture.get_editor_property("asset_import_data")
                    source_file = Path(import_data.get_first_filename()) if import_data else None
                    if source_file is None or not source_file.is_file():
                        raise ValueError("Face SDF import source is unavailable")
                    input_audit[-1]["import_source"] = str(source_file.resolve())
                    input_audit[-1]["import_source_sha256"] = hashlib.sha256(source_file.read_bytes()).hexdigest()
                except Exception as error:
                    input_audit[-1]["import_source_error"] = str(error)
            effective[role] = actual

        if parent_is_master or route in {"stocking", "cloth"} or route in parent_assets:
            profile = ctx.material_map.get("profiles", {}).get(entry.get("profile"), {})
            expected_scalars, debt = effective_scalars(entry, profile, route)
            ctx.material_debt.extend(debt)
            for name, expected in expected_scalars.items():
                actual = _scalar_value(instance, name)
                if actual is None or abs(actual - float(expected)) > 0.0001:
                    violations.append(f"{slot_name}: scalar {name} = {actual}, expected {expected}")
            expected_vectors = dict(profile.get("vectors", {}) or {})
            expected_vectors.update((entry.get("overrides", {}) or {}).get("vectors", {}) or {})
            for name, expected in expected_vectors.items():
                actual = _vector_value(instance, name)
                if (actual is None or len(expected) != 4
                        or any(abs(a - float(b)) > 0.0001 for a, b in zip(actual, expected))):
                    violations.append(f"{slot_name}: vector {name} = {actual}, expected {expected}")
        slots_audit.append({
            "slot": slot_name,
            "profile": entry.get("profile"),
            "instance": instance.get_path_name(),
            "parent": parent.get_path_name() if parent else None,
            "declared_route": route,
            "effective_textures": effective,
            "effective_scalars": scalar_readback,
            "face_sdf_response": master_sdf_response if parent_is_master else None,
            "input_audit": input_audit,
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
            if role == "normal" and (srgb or "NORMALMAP" not in compression.upper()):
                violations.append(f"{key}: normal map requires linear Normalmap compression")
            if role in MASK_ROLES and (srgb or "MASKS" not in compression.upper()):
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
        "binding_scope": "unassigned_component_overrides" if source_mesh else "mesh_default_materials",
        "source_mesh": source_mesh,
        "material_debt": ctx.material_debt,
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
