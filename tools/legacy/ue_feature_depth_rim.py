"""Generic custom-depth rim post-process material and optional in-level binding.

Four-neighbour custom-depth comparison in viewport pixels, gated by a custom
stencil value.  Built on demand; can apply itself to the current default level.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import unreal

FRAMEWORK_DIR = Path(__file__).resolve().parent
if str(FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR))

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


def _scene_texture(material, texture_id, uv, x, y, uv_output=""):
    node = expression(material, unreal.MaterialExpressionSceneTexture, x, y)
    safe_set(node, "scene_texture_id", texture_id)
    if uv is not None:
        connect(uv, uv_output, node, "UVs")
    return node


def _mask(material, source, component, x, y):
    node = expression(material, unreal.MaterialExpressionComponentMask, x, y)
    for channel in "rgba":
        safe_set(node, channel, channel == component)
    connect(source, "", node, "")
    return node


def _binary(material, cls, a, b, x, y):
    node = expression(material, cls, x, y)
    connect(a, "", node, "A")
    connect(b, "", node, "B")
    return node


def build(ctx: BuildContext, apply_in_level: bool = False) -> dict:
    options = (ctx.config.get("features", {}) or {}).get("depth_rim", {}) or {}
    root = ctx.names["material_root"]
    material = load_or_create_material(ctx.names["rim_asset"], root, fresh=True)
    safe_set(material, "material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    safe_set(material, "blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    safe_set(material, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)

    screen_uv = expression(material, unreal.MaterialExpressionScreenPosition, -2200, -500)
    scene_color = _scene_texture(material, unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0, screen_uv, -2200, -760, "ViewportUV")
    scene_rgb = expression(material, unreal.MaterialExpressionComponentMask, -1960, -760)
    safe_set(scene_rgb, "r", True)
    safe_set(scene_rgb, "g", True)
    safe_set(scene_rgb, "b", True)
    safe_set(scene_rgb, "a", False)
    connect(scene_color, "Color", scene_rgb, "")
    center_depth = _scene_texture(material, unreal.SceneTextureId.PPI_CUSTOM_DEPTH, screen_uv, -2200, -240, "ViewportUV")
    center_stencil = _scene_texture(material, unreal.SceneTextureId.PPI_CUSTOM_STENCIL, screen_uv, -2200, 20, "ViewportUV")

    width = scalar(material, "RimWidthPixels", options.get("width_pixels", 2.25), -1960, 300)
    pixel_step = expression(material, unreal.MaterialExpressionMultiply, -1740, 300)
    connect(center_depth, "InvSize", pixel_step, "A")
    connect(width, "", pixel_step, "B")
    step_x = _mask(material, pixel_step, "r", -1520, 220)
    step_y = _mask(material, pixel_step, "g", -1520, 380)
    zero = expression(material, unreal.MaterialExpressionConstant, -1520, 540)
    safe_set(zero, "r", 0.0)
    x_offset = expression(material, unreal.MaterialExpressionAppendVector, -1300, 220)
    connect(step_x, "", x_offset, "A")
    connect(zero, "", x_offset, "B")
    y_offset = expression(material, unreal.MaterialExpressionAppendVector, -1300, 400)
    connect(zero, "", y_offset, "A")
    connect(step_y, "", y_offset, "B")
    uv_right = _binary(material, unreal.MaterialExpressionAdd, screen_uv, x_offset, -1080, 120)
    uv_left = _binary(material, unreal.MaterialExpressionSubtract, screen_uv, x_offset, -1080, 260)
    uv_up = _binary(material, unreal.MaterialExpressionAdd, screen_uv, y_offset, -1080, 400)
    uv_down = _binary(material, unreal.MaterialExpressionSubtract, screen_uv, y_offset, -1080, 540)
    diffs = []
    for index, uv in enumerate((uv_right, uv_left, uv_up, uv_down)):
        y = -180 + index * 170
        depth = _scene_texture(material, unreal.SceneTextureId.PPI_CUSTOM_DEPTH, uv, -820, y)
        delta = _binary(material, unreal.MaterialExpressionSubtract, center_depth, depth, -580, y)
        absolute = expression(material, unreal.MaterialExpressionAbs, -360, y)
        connect(delta, "", absolute, "")
        diffs.append(absolute)
    max_a = _binary(material, unreal.MaterialExpressionMax, diffs[0], diffs[1], -120, -80)
    max_b = _binary(material, unreal.MaterialExpressionMax, diffs[2], diffs[3], -120, 260)
    max_diff = _binary(material, unreal.MaterialExpressionMax, max_a, max_b, 100, 80)
    threshold_min_node = scalar(material, "RimDepthThresholdMin", options.get("threshold_min", 0.00001), -120, 500)
    threshold_max_node = scalar(material, "RimDepthThresholdMax", options.get("threshold_max", 0.00020), -120, 650)
    minus_min = _binary(material, unreal.MaterialExpressionSubtract, max_diff, threshold_min_node, 320, 80)
    range_node = _binary(material, unreal.MaterialExpressionSubtract, threshold_max_node, threshold_min_node, 100, 600)
    normalized = _binary(material, unreal.MaterialExpressionDivide, minus_min, range_node, 540, 80)
    depth_mask = expression(material, unreal.MaterialExpressionSaturate, 760, 80)
    connect(normalized, "", depth_mask, "")
    depth_mask_scalar = _mask(material, depth_mask, "r", 980, 40)

    stencil_value = float(options.get("stencil_value", 1.0))
    stencil_r = _mask(material, center_stencil, "r", 100, 800)
    stencil_delta = expression(material, unreal.MaterialExpressionSubtract, 320, 800)
    connect(stencil_r, "", stencil_delta, "A")
    safe_set(stencil_delta, "const_b", stencil_value)
    stencil_abs = expression(material, unreal.MaterialExpressionAbs, 540, 800)
    connect(stencil_delta, "", stencil_abs, "")
    stencil_sat = expression(material, unreal.MaterialExpressionSaturate, 760, 800)
    connect(stencil_abs, "", stencil_sat, "")
    stencil_equal = expression(material, unreal.MaterialExpressionOneMinus, 980, 800)
    connect(stencil_sat, "", stencil_equal, "")
    rim_mask = _binary(material, unreal.MaterialExpressionMultiply, depth_mask_scalar, stencil_equal, 1200, 160)
    rim_color = vector(material, "RimColor", options.get("color", (0.28, 0.34, 0.48, 1.0)), 1000, 360)
    rim_intensity = scalar(material, "RimIntensity", options.get("intensity", 0.18), 1000, 520)
    rim_colored = _binary(material, unreal.MaterialExpressionMultiply, rim_color, rim_intensity, 1240, 420)
    rim_term = _binary(material, unreal.MaterialExpressionMultiply, rim_colored, rim_mask, 1480, 260)
    final_color = _binary(material, unreal.MaterialExpressionAdd, scene_rgb, rim_term, 1720, -40)
    connect_property(final_color, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError("failed to save depth-rim parent")

    instance_name = f"{ctx.names['instance_prefix']}_DepthRim"
    instance_path = f"{root}/{instance_name}"
    instance = unreal.EditorAssetLibrary.load_asset(instance_path) if unreal.EditorAssetLibrary.does_asset_exist(instance_path) else None
    if instance is None:
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            instance_name, root, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()
        )
    if not isinstance(instance, unreal.MaterialInstanceConstant):
        raise RuntimeError(f"failed to create {instance_path}")
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance, False)

    applied = None
    if apply_in_level:
        applied = _apply_in_level(ctx, instance, stencil_value)

    report = {
        "status": "success",
        "parent": material.get_path_name(),
        "instance": instance.get_path_name(),
        "method": "four-neighbour custom-depth comparison in viewport pixels",
        "applied_in_level": applied,
    }
    ctx.report_path("depth_rim_build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _apply_in_level(ctx: BuildContext, rim_material, stencil_value: float):
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        return "no editor world"
    label = f"{ctx.names['character_id']}_Preview"
    target = None
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == label:
            components = actor.get_components_by_class(unreal.SkeletalMeshComponent)
            if components:
                target = components[0]
                break
    if target is None:
        return f"character actor {label!r} not found"

    target.set_render_custom_depth(True)
    target.set_custom_depth_stencil_value(int(stencil_value))
    target.mark_render_state_dirty()

    volume = None
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.PostProcessVolume) and actor.get_actor_label().endswith("_DepthRim"):
            volume = actor
            break
    if volume is None:
        volume = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator())
        volume.set_actor_label(f"{ctx.names['character_id']}_DepthRim")
    safe_set(volume, "unbound", True)
    safe_set(volume, "blend_weight", 1.0)
    settings = volume.get_editor_property("settings")
    settings.set_editor_property("weighted_blendables", unreal.WeightedBlendables([unreal.WeightedBlendable(1.0, rim_material)]))
    safe_set(volume, "settings", settings)
    return volume.get_path_name()


def main() -> None:
    import argparse

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    parser.add_argument("--apply-in-level", action="store_true")
    args, _ = parser.parse_known_args(argv)
    ctx = BuildContext(args.config)
    print("MMD2UE_DEPTH_RIM " + json.dumps(build(ctx, apply_in_level=args.apply_in_level), ensure_ascii=False))


if __name__ == "__main__":
    main()
