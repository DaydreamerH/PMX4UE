"""Create per-slot material instances from a normalized material map and bind
them to the skeletal mesh.  Character independent."""

from __future__ import annotations

import re
from pathlib import Path

import unreal

from ue_context import BuildError, asset_exists, load
from mmd2ue_core import TEXTURE_PARAMETER_NAMES

TOON_SPHERE_STEMS = {
    "toon01", "toon02", "toon03", "toon04", "toon05", "toon06", "toon07", "toon08",
    "toon09", "toon10", "stoon01", "stoon03", "skin", "hair-a", "socks2", "ssshine1",
    "ssshine2", "spa",
}


def material_asset_name(slot_name: str) -> str:
    """Keep semantic punctuation that would otherwise collide (Eyes vs Eyes+)."""
    semantic = str(slot_name).replace("+", "_Plus").replace("(", "_").replace(")", "")
    return re.sub(r"[^A-Za-z0-9_]+", "_", semantic).strip("_") or "Material"


def find_base_name(images: list[str]) -> str | None:
    for image in images:
        low = image.lower()
        if low.startswith("toon") or low in TOON_SPHERE_STEMS:
            continue
        if "_rmo" in low or low.endswith("_n.png") or low.endswith("_n"):
            continue
        return image
    return images[0] if images else None


def manifest_records(ctx) -> dict:
    manifest = ctx.require_manifest()
    return {record.get("name"): record for record in manifest.get("materials", [])}


def source_base_key(ctx, slot_name: str) -> str | None:
    record = manifest_records(ctx).get(slot_name)
    if not record:
        return None
    for image in record.get("images", []):
        if image.get("node") == "mmd_base_tex":
            return Path(image.get("path") or image.get("image") or "").stem.lower()
    images = [Path(image.get("path") or image.get("image") or "").name for image in record.get("images", [])]
    base = find_base_name(images)
    return Path(base).stem.lower() if base else None


def special_masters_for(ctx, master, eye_add=None, eye_multiply=None, invisible=None, glass=None):
    table = {
        "master": master,
        "eye_add": eye_add,
        "eye_multiply": eye_multiply,
        "invisible": invisible,
        "glass": glass,
    }
    return {kind: value for kind, value in table.items() if value is not None}


def create_instance(ctx, master, entry: dict, special_masters: dict | None = None):
    slot_name = entry["slot"]
    name = material_asset_name(slot_name)
    asset_name = f"{ctx.names['instance_prefix']}_{name}"
    asset_path = f"{ctx.names['material_root']}/{asset_name}"

    instance = load(asset_path) if asset_exists(asset_path) else None
    if instance is None:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name, ctx.names["material_root"], unreal.MaterialInstanceConstant, factory
        )
    if instance is None:
        raise BuildError(f"failed to create material instance {asset_path}")
    if not isinstance(instance, unreal.MaterialInstanceConstant):
        raise BuildError(f"{asset_path} exists but is not a MaterialInstanceConstant")

    kind = ctx.special_kind_for_slot(slot_name)
    parent = (special_masters or {}).get(kind, master)
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
    try:
        unreal.MaterialEditingLibrary.clear_all_material_instance_parameters(instance)
    except Exception:
        pass

    profile_name = entry.get("profile")
    profile = ctx.material_map.get("profiles", {}).get(profile_name)
    if profile is None:
        raise BuildError(f"unknown profile {profile_name!r} for slot {slot_name!r}")

    mapped_base = entry["textures"].get("base_color")
    actual_base = source_base_key(ctx, slot_name)
    if mapped_base and actual_base and mapped_base.lower() != actual_base:
        raise BuildError(
            f"source/map mismatch for {slot_name}: manifest={actual_base!r} map={mapped_base!r}"
        )

    for role, parameter in TEXTURE_PARAMETER_NAMES.items():
        key = entry["textures"].get(role)
        if not key:
            continue
        texture = ctx.texture_for(key)
        if texture is None:
            raise BuildError(f"mapped texture {key!r} for slot {slot_name!r} was not imported")
        unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(instance, parameter, texture)

    # Materials with no base texture use a white default so the profile/override
    # Tint alone drives the colour (solid-colour PMX materials, effect shells).
    if not entry["textures"].get("base_color"):
        white = ctx.engine_default_texture()
        if white is not None:
            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(instance, "BaseColorTexture", white)

    for parameter, value in profile.get("scalars", {}).items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, parameter, float(value))
    for parameter, value in profile.get("vectors", {}).items():
        if len(value) != 4:
            raise BuildError(f"vector parameter {parameter!r} in profile {profile_name!r} needs four components")
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
            instance, parameter, unreal.LinearColor(*value)
        )

    overrides = entry.get("overrides") or {}
    for parameter, value in (overrides.get("scalars") or {}).items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, parameter, float(value))
    for parameter, value in (overrides.get("vectors") or {}).items():
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
            instance, parameter, unreal.LinearColor(*value)
        )

    unreal.EditorAssetLibrary.save_loaded_asset(instance)
    return instance


def assign_materials(ctx, mesh, instances: dict):
    manifest = ctx.require_manifest()
    ordered_slots = [name for record in manifest.get("meshes", []) for name in record.get("materials", [])]
    created = [instances.get(slot) for slot in ordered_slots]
    if any(instance is None for instance in created):
        missing = [slot for slot, instance in zip(ordered_slots, created) if instance is None]
        raise BuildError(f"no material instance for slots: {missing}")

    current = list(mesh.get_editor_property("materials"))
    if len(current) != len(created):
        raise BuildError(f"material slot count mismatch: mesh={len(current)} generated={len(created)}")
    for slot, instance in zip(current, created):
        slot.set_editor_property("material_interface", instance)
    mesh.modify()
    mesh.set_editor_property("materials", current)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)

    written = list(mesh.get_editor_property("materials"))
    resolved = [slot.get_editor_property("material_interface") for slot in written]
    if any(material is None or material.get_path_name().endswith("WorldGridMaterial") for material in resolved):
        raise BuildError("skeletal mesh material assignment did not persist")
    return len(resolved)
