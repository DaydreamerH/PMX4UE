"""Optional anisotropic stocking material.

Default-Lit PBR plus a grazing-angle thickness term and a GFL2-style
anisotropic Cook-Torrance macro lobe evaluated on a stable character-local
fibre tangent.  Reparents the stocking-profile instances to it.
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
    texture_parameter,
    vector,
)
from ue_material_instances import material_asset_name  # noqa: E402


def build(ctx: BuildContext) -> dict:
    entries = [entry for entry in ctx.slot_entries() if entry.get("profile") == "stocking"]
    if not entries:
        return {"status": "skipped", "reason": "no stocking-profile slots"}

    options = (ctx.material_map.get("specials", {}) or {}).get("stocking", {}) or {}
    special_scalars = options.get("scalars", {}) or {}
    special_vectors = options.get("vectors", {}) or {}

    def sc(name, default):
        return float(special_scalars.get(name, default))

    def vc(name, default):
        return tuple(special_vectors.get(name, default))

    anchor = entries[0]
    base = ctx.texture_for(anchor["textures"].get("base_color")) or ctx.default_texture("base_color")
    normal = ctx.texture_for(anchor["textures"].get("normal")) or ctx.default_texture("normal")
    rmo = ctx.texture_for(anchor["textures"].get("rmo")) or ctx.default_texture("rmo")

    root = ctx.names["material_root"]
    material = load_or_create_material(ctx.names["stocking_asset"], root, fresh=True)
    for name, value in (
        ("material_domain", unreal.MaterialDomain.MD_SURFACE),
        ("blend_mode", unreal.BlendMode.BLEND_MASKED),
        ("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT),
        ("two_sided", False),
        ("opacity_mask_clip_value", 0.12),
        ("used_with_skeletal_mesh", True),
        ("used_with_morph_targets", True),
        ("tangent_space_normal", True),
    ):
        safe_set(material, name, value)

    base_node = texture_parameter(material, "BaseColorTexture", base, -1500, -220)
    tint = vector(material, "Tint", vc("Tint", (0.06, 0.05, 0.08, 1.0)), -1500, -40)
    base_tinted = expression(material, unreal.MaterialExpressionMultiply, -1240, -160)
    connect(base_node, "RGB", base_tinted, "A")
    connect(tint, "", base_tinted, "B")
    macro_normal = expression(material, unreal.MaterialExpressionVertexNormalWS, -1500, 180)
    view = expression(material, unreal.MaterialExpressionCameraVectorWS, -1500, 300)
    nov = expression(material, unreal.MaterialExpressionDotProduct, -1240, 200)
    connect(macro_normal, "", nov, "A")
    connect(view, "", nov, "B")
    nov_sat = expression(material, unreal.MaterialExpressionSaturate, -1040, 200)
    connect(nov, "", nov_sat, "")
    grazing = expression(material, unreal.MaterialExpressionOneMinus, -850, 200)
    connect(nov_sat, "", grazing, "")
    edge_range = scalar(material, "StockingEdgeRange", sc("StockingEdgeRange", 2.2), -1040, 350)
    edge_curve = expression(material, unreal.MaterialExpressionPower, -650, 200)
    connect(grazing, "", edge_curve, "Base")
    connect(edge_range, "", edge_curve, "Exp")
    edge_intensity = scalar(material, "StockingEdgeIntensity", sc("StockingEdgeIntensity", 0.8), -850, 350)
    edge_raw = expression(material, unreal.MaterialExpressionMultiply, -440, 200)
    connect(edge_curve, "", edge_raw, "A")
    connect(edge_intensity, "", edge_raw, "B")
    edge_weight = expression(material, unreal.MaterialExpressionSaturate, -240, 200)
    connect(edge_raw, "", edge_weight, "")
    edge_tint = vector(material, "StockingEdgeTint", vc("StockingEdgeTint", (0.10, 0.06, 0.13, 1.0)), -440, 360)
    white = expression(material, unreal.MaterialExpressionConstant3Vector, -240, 360)
    safe_set(white, "constant", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    edge_color = expression(material, unreal.MaterialExpressionLinearInterpolate, 0, 220)
    connect(white, "", edge_color, "A")
    connect(edge_tint, "", edge_color, "B")
    connect(edge_weight, "", edge_color, "Alpha")
    physical_base = expression(material, unreal.MaterialExpressionMultiply, 220, -100)
    connect(base_tinted, "", physical_base, "A")
    connect(edge_color, "", physical_base, "B")
    connect_property(physical_base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    # Opaque knit: the arm sock has no skin mesh underneath, so translucency is
    # not usable.  The fabric reads through edge darkening + a soft macro sheen
    # instead of alpha.
    alpha_scale = scalar(material, "AlphaScale", sc("AlphaScale", 1.0), -1240, 20)
    opacity = expression(material, unreal.MaterialExpressionMultiply, -1040, 0)
    connect(base_node, "A", opacity, "A")
    connect(alpha_scale, "", opacity, "B")
    connect_property(opacity, "", unreal.MaterialProperty.MP_OPACITY_MASK)

    normal_node = texture_parameter(material, "NormalTexture", normal, -1500, 600, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    connect_property(normal_node, "RGB", unreal.MaterialProperty.MP_NORMAL)
    rmo_node = texture_parameter(material, "RMOTexture", rmo, -1500, 860, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    roughness_base = scalar(material, "StockingRoughnessBase", sc("StockingRoughnessBase", 0.32), -1240, 900)
    roughness_map_influence = scalar(material, "StockingRoughnessMapInfluence", sc("StockingRoughnessMapInfluence", 0.2), -1240, 1010)
    roughness_mapped = expression(material, unreal.MaterialExpressionLinearInterpolate, -980, 900)
    connect(roughness_base, "", roughness_mapped, "A")
    connect(rmo_node, "R", roughness_mapped, "B")
    connect(roughness_map_influence, "", roughness_mapped, "Alpha")
    roughness_min = scalar(material, "StockingRoughnessMin", sc("StockingRoughnessMin", 0.24), -760, 1000)
    roughness_floor = expression(material, unreal.MaterialExpressionMax, -540, 900)
    connect(roughness_mapped, "", roughness_floor, "A")
    connect(roughness_min, "", roughness_floor, "B")
    roughness_max = scalar(material, "StockingRoughnessMax", sc("StockingRoughnessMax", 0.46), -540, 1020)
    roughness_clamped = expression(material, unreal.MaterialExpressionMin, -320, 900)
    connect(roughness_floor, "", roughness_clamped, "A")
    connect(roughness_max, "", roughness_clamped, "B")
    connect_property(roughness_clamped, "", unreal.MaterialProperty.MP_ROUGHNESS)
    metallic = scalar(material, "StockingMetallic", sc("StockingMetallic", 0.0), -980, 1120)
    connect_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    specular = scalar(material, "Specular", sc("Specular", 0.56), -760, 1120)
    connect_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
    ao_one = expression(material, unreal.MaterialExpressionConstant, -980, 1260)
    safe_set(ao_one, "r", 1.0)
    ao_influence = scalar(material, "AOInfluence", sc("AOInfluence", 0.16), -980, 1370)
    ao = expression(material, unreal.MaterialExpressionLinearInterpolate, -760, 1260)
    connect(ao_one, "", ao, "A")
    connect(rmo_node, "B", ao, "B")
    connect(ao_influence, "", ao, "Alpha")
    connect_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

    light = expression(material, unreal.MaterialExpressionSkyAtmosphereLightDirection, -1500, 1540)
    safe_set(light, "light_index", 0)
    fibre_local = vector(material, "StockingFiberDirectionLocal", vc("StockingFiberDirectionLocal", (0.0, 0.0, 1.0, 0.0)), -1500, 1690)
    fibre_world = expression(material, unreal.MaterialExpressionTransform, -1240, 1690)
    safe_set(fibre_world, "transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL)
    safe_set(fibre_world, "transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    connect(fibre_local, "RGB", fibre_world, "")
    aniso_roughness = scalar(material, "StockingAnisoRoughness", sc("StockingAnisoRoughness", 0.42), -1240, 1840)
    anisotropy = scalar(material, "StockingAnisotropy", sc("StockingAnisotropy", 0.5), -1000, 1840)
    highlight_strength = scalar(material, "StockingHighlightStrength", sc("StockingHighlightStrength", 0.35), -760, 1840)
    highlight_tint = vector(material, "StockingHighlightTint", vc("StockingHighlightTint", (0.62, 0.66, 0.78, 1.0)), -520, 1840)
    custom = expression(material, unreal.MaterialExpressionCustom, -700, 1500)
    custom_inputs = []
    for input_name in ("N", "V", "L", "T", "Roughness", "Anisotropy", "Strength", "Tint"):
        custom_input = unreal.CustomInput()
        custom_input.set_editor_property("input_name", input_name)
        custom_inputs.append(custom_input)
    safe_set(custom, "inputs", custom_inputs)
    safe_set(custom, "output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    safe_set(
        custom,
        "code",
        """
float3 n = normalize(N);
float3 v = normalize(V);
float3 l = normalize(L);
float3 h = normalize(v + l);
float NoL = saturate(dot(n, l));
float NoV = saturate(dot(n, v));
float NoH = saturate(dot(n, h));
float VoH = saturate(dot(v, h));
float3 t = normalize(T - n * dot(T, n));
float3 b = normalize(cross(n, t));
float r = clamp(Roughness, 0.08, 0.9);
float a = clamp(Anisotropy, -0.8, 0.8);
float ax = max(r * (1.0 + a), 0.035);
float ay = max(r * (1.0 - a), 0.035);
float XoH = dot(t, h);
float YoH = dot(b, h);
float d = XoH * XoH / (ax * ax) + YoH * YoH / (ay * ay) + NoH * NoH;
float D = 1.0 / max(1e-4, 3.14159265 * ax * ay * d * d);
float k = (r + 1.0) * (r + 1.0) * 0.125;
float Gv = NoV / max(1e-4, NoV * (1.0 - k) + k);
float Gl = NoL / max(1e-4, NoL * (1.0 - k) + k);
float F = 0.04 + 0.96 * pow(1.0 - VoH, 5.0);
float spec = D * Gv * Gl * F * NoL / max(1e-4, 4.0 * NoV * NoL);
spec = spec / (1.0 + spec);
return Tint * spec * Strength;
""".strip(),
    )
    for source, output_name, input_name in (
        (macro_normal, "", "N"),
        (view, "", "V"),
        (light, "", "L"),
        (fibre_world, "", "T"),
        (aniso_roughness, "", "Roughness"),
        (anisotropy, "", "Anisotropy"),
        (highlight_strength, "", "Strength"),
        (highlight_tint, "RGB", "Tint"),
    ):
        connect(source, output_name, custom, input_name)
    connect_property(custom, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, False)

    reparented = []
    for entry in entries:
        name = f"{ctx.names['instance_prefix']}_{material_asset_name(entry['slot'])}"
        instance = unreal.EditorAssetLibrary.load_asset(f"{root}/{name}")
        if not isinstance(instance, unreal.MaterialInstanceConstant):
            continue
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
        for parameter, value in special_scalars.items():
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, parameter, float(value))
        for parameter, value in special_vectors.items():
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, parameter, unreal.LinearColor(*value))
        unreal.MaterialEditingLibrary.update_material_instance(instance)
        unreal.EditorAssetLibrary.save_loaded_asset(instance, False)
        reparented.append(instance.get_path_name())

    report = {
        "status": "success",
        "material": material.get_path_name(),
        "reparented": reparented,
        "shading": "Default Lit PBR plus anisotropic Cook-Torrance macro lobe",
        "fibre": "character-local direction projected onto the pixel normal",
    }
    ctx.report_path("stocking_build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    import argparse

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("MMD2UE_CHARACTER_CONFIG"))
    args, _ = parser.parse_known_args(argv)
    ctx = BuildContext(args.config)
    print("MMD2UE_STOCKING " + json.dumps(build(ctx), ensure_ascii=False))


if __name__ == "__main__":
    main()
