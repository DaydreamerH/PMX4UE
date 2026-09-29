"""Generic inverse-hull outline material for any character.

Distance-constrained vertex-normal extrusion with backface-only opacity, plus
optional UV-ellipse suppression of internal face lines (eyes/mouth).  Ellipse
regions and widths must be calibrated per character. No universal face UV mask.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import unreal

FRAMEWORK_DIR = Path(__file__).resolve().parent
if str(FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR))
if str(FRAMEWORK_DIR.parent) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR.parent))
from outline_contract import face_regions

from ue_context import (  # noqa: E402
    BuildContext,
    connect,
    connect_property,
    expression,
    load_or_create_material,
    safe_set,
    scalar,
    vector,
)

def ellipse_outside_mask(material, uv, name, center, radius, x, y):
    """Return 0 inside a soft UV ellipse and 1 outside it."""
    center_param = vector(material, f"{name}Center", (center[0], center[1], 0.0, 0.0), x, y + 160)
    radius_param = vector(material, f"{name}Radius", (radius[0], radius[1], 0.0, 0.0), x, y + 300)
    center_mask = expression(material, unreal.MaterialExpressionComponentMask, x + 220, y + 120)
    safe_set(center_mask, "r", True)
    safe_set(center_mask, "g", True)
    safe_set(center_mask, "b", False)
    safe_set(center_mask, "a", False)
    connect(center_param, "", center_mask, "")
    radius_mask = expression(material, unreal.MaterialExpressionComponentMask, x + 220, y + 260)
    safe_set(radius_mask, "r", True)
    safe_set(radius_mask, "g", True)
    safe_set(radius_mask, "b", False)
    safe_set(radius_mask, "a", False)
    connect(radius_param, "", radius_mask, "")
    delta = expression(material, unreal.MaterialExpressionSubtract, x + 440, y)
    connect(uv, "", delta, "A")
    connect(center_mask, "", delta, "B")
    normalized = expression(material, unreal.MaterialExpressionDivide, x + 660, y)
    connect(delta, "", normalized, "A")
    connect(radius_mask, "", normalized, "B")
    distance_squared = expression(material, unreal.MaterialExpressionDotProduct, x + 880, y)
    connect(normalized, "", distance_squared, "A")
    connect(normalized, "", distance_squared, "B")
    soft_start = expression(material, unreal.MaterialExpressionSubtract, x + 1100, y)
    connect(distance_squared, "", soft_start, "A")
    safe_set(soft_start, "const_b", 0.65)
    soft_scale = expression(material, unreal.MaterialExpressionMultiply, x + 1320, y)
    connect(soft_start, "", soft_scale, "A")
    safe_set(soft_scale, "const_b", 2.857142857)
    outside = expression(material, unreal.MaterialExpressionSaturate, x + 1540, y)
    connect(soft_scale, "", outside, "")
    return outside


def _build_instance(material, root, name, width, face_internal_mask=0.0):
    path = f"{root}/{name}"
    instance = unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if instance is None:
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, root, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
        )
    if not isinstance(instance, unreal.MaterialInstanceConstant):
        raise RuntimeError(f"failed to create {path}")
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, "OutlineWidthScale", width)
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, "FaceInternalOutlineMask", face_internal_mask)
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance, False)
    return instance


def build(ctx: BuildContext) -> dict:
    options = (ctx.config.get("features", {}) or {}).get("outline", {}) or {}
    regions = face_regions(options)  # Validate before creating any UE asset.
    root = ctx.names["material_root"]
    material = load_or_create_material(ctx.names["outline_asset"], root, fresh=True)
    for name, value in (
        ("material_domain", unreal.MaterialDomain.MD_SURFACE),
        ("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT),
        ("shading_model", unreal.MaterialShadingModel.MSM_UNLIT),
        ("two_sided", True),
        ("used_with_skeletal_mesh", True),
        ("used_with_morph_targets", True),
        ("tangent_space_normal", False),
    ):
        safe_set(material, name, value)

    vertex_normal = expression(material, unreal.MaterialExpressionVertexNormalWS, -1200, -120)
    camera_position = expression(material, unreal.MaterialExpressionCameraPositionWS, -1200, 100)
    object_position = expression(material, unreal.MaterialExpressionObjectPositionWS, -1200, 240)
    camera_distance = expression(material, unreal.MaterialExpressionDistance, -950, 160)
    connect(camera_position, "", camera_distance, "A")
    connect(object_position, "", camera_distance, "B")
    # Distance-constrained world-space extrusion.  UE material vertex shaders
    # cannot read the View uniform block (no clip-space access), so constant
    # screen width is approximated by clamping the camera distance; the MCP
    # overlay pass keeps the width consistent across slots.
    min_node = scalar(material, "OutlineMinDistance", options.get("min_distance", 140.0), -950, 320)
    distance_floor = expression(material, unreal.MaterialExpressionMax, -720, 160)
    connect(camera_distance, "", distance_floor, "A")
    connect(min_node, "", distance_floor, "B")
    max_node = scalar(material, "OutlineMaxDistance", options.get("max_distance", 520.0), -720, 320)
    distance_clamped = expression(material, unreal.MaterialExpressionMin, -490, 160)
    connect(distance_floor, "", distance_clamped, "A")
    connect(max_node, "", distance_clamped, "B")
    width_scale = scalar(material, "OutlineWidthScale", options.get("width", 0.00095), -490, 320)
    world_width = expression(material, unreal.MaterialExpressionMultiply, -260, 160)
    connect(distance_clamped, "", world_width, "A")
    connect(width_scale, "", world_width, "B")
    normal_offset = expression(material, unreal.MaterialExpressionMultiply, 0, 20)
    connect(vertex_normal, "", normal_offset, "A")
    connect(world_width, "", normal_offset, "B")
    connect_property(normal_offset, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)

    two_sided_sign = expression(material, unreal.MaterialExpressionTwoSidedSign, -720, 620)
    neg_half = expression(material, unreal.MaterialExpressionMultiply, -490, 620)
    connect(two_sided_sign, "", neg_half, "A")
    safe_set(neg_half, "const_b", -0.5)
    backface_mask = expression(material, unreal.MaterialExpressionAdd, -260, 620)
    connect(neg_half, "", backface_mask, "A")
    safe_set(backface_mask, "const_b", 0.5)
    outline_opacity = scalar(material, "OutlineOpacity", options.get("opacity", 0.92), -260, 760)
    opacity = expression(material, unreal.MaterialExpressionMultiply, 0, 620)
    connect(backface_mask, "", opacity, "A")
    connect(outline_opacity, "", opacity, "B")

    face_uv = expression(material, unreal.MaterialExpressionTextureCoordinate, -1480, 1040)
    safe_set(face_uv, "coordinate_index", options.get("face_uv_channel", 0))
    outside_nodes = []
    for index, region in enumerate(regions):
        outside_nodes.append(
            ellipse_outside_mask(
                material, face_uv, region.get("name", f"FaceOutlineRegion{index}"),
                region.get("center", [0.5, 0.5]), region.get("radius", [0.1, 0.1]),
                -1260, 1040 + index * 400,
            )
        )
    internal_outside = outside_nodes[0] if outside_nodes else expression(material, unreal.MaterialExpressionConstant, 520, 1040)
    if not outside_nodes:
        safe_set(internal_outside, "r", 1.0)
    for node in outside_nodes[1:]:
        combined = expression(material, unreal.MaterialExpressionMultiply, 520, 1120)
        connect(internal_outside, "", combined, "A")
        connect(node, "", combined, "B")
        internal_outside = combined
    mask_enable = scalar(material, "FaceInternalOutlineMask", 0.0, 520, 1320)
    one = expression(material, unreal.MaterialExpressionConstant, 520, 1440)
    safe_set(one, "r", 1.0)
    selected_internal_mask = expression(material, unreal.MaterialExpressionLinearInterpolate, 960, 1120)
    connect(one, "", selected_internal_mask, "A")
    connect(internal_outside, "", selected_internal_mask, "B")
    connect(mask_enable, "", selected_internal_mask, "Alpha")
    masked_opacity = expression(material, unreal.MaterialExpressionMultiply, 1180, 620)
    connect(opacity, "", masked_opacity, "A")
    connect(selected_internal_mask, "", masked_opacity, "B")
    connect_property(masked_opacity, "", unreal.MaterialProperty.MP_OPACITY)

    outline_color = vector(material, "OutlineColor", options.get("color", (0.018, 0.012, 0.026, 1.0)), 0, 820)
    connect_property(outline_color, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError("failed to save outline parent")

    prefix = ctx.names["instance_prefix"]
    general = _build_instance(material, root, f"{prefix}_Outline", options.get("width", 0.00095))
    face = _build_instance(material, root, f"{prefix}_Outline_Face", options.get("face_width", options.get("width", 0.00095)), float(bool(regions)))
    hair = _build_instance(material, root, f"{prefix}_Outline_Hair", options.get("hair_width", 0.00072))

    report = {
        "status": "success",
        "parent": material.get_path_name(),
        "instances": [general.get_path_name(), face.get_path_name(), hair.get_path_name()],
        "width": "VertexNormalWS * clamp(camera distance, min, max) * per-slot width",
        "culling": "TwoSidedSign backface only",
        "internal_line_control": "UV ellipse suppression + per-slot overlay exclusion",
        "face_internal_enabled": bool(regions),
        "face_uv_channel": options.get("face_uv_channel", 0),
        "face_internal_regions": regions,
        "face_internal_evidence": options.get("face_internal_evidence"),
        "visual_status": "pending: inspect mouth corners with outline off/on and calibrated face candidate",
        "duplicate_mesh_asset": False,
    }
    ctx.report_path("outline_build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    import argparse, os

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    args, _ = parser.parse_known_args(argv)
    ctx = BuildContext(args.config)
    print("MMD2UE_OUTLINE " + json.dumps(build(ctx), ensure_ascii=False))


if __name__ == "__main__":
    main()
