"""Optional stylized-PBR cloth material.

The main master already provides physical cloth PBR.  This builder adds the
GFL2-style two-row ramp (diffuse remap + normalized GGX D) and reparents the
requested cloth-family instances to it.  It is skipped unless a ramp texture is
available.

Ramp resolution order:
  1. material_map.specials.cloth.ramp (a texture key already imported)
  2. <source_assets_dir>/T_<CharacterId>_ClothRamp.png
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
    import_one,
    load_or_create_material,
    safe_set,
    scalar,
    texture_parameter,
    vector,
)
from ue_material_instances import material_asset_name  # noqa: E402

CLOTH_FAMILIES = {"cloth", "white_cloth", "dark_cloth", "soft_fabric", "heavy_fabric"}


def _resolve_ramp(ctx: BuildContext):
    special = (ctx.material_map.get("specials", {}) or {}).get("cloth", {}) or {}
    if special.get("ramp"):
        texture = ctx.texture_for(special["ramp"])
        if texture is not None:
            return texture
    source_root = ctx.config.get("paths", {}).get("source_assets_dir", f"SourceAssets/{ctx.names['character_id']}")
    source = ctx.root / source_root / f"T_{ctx.names['character_id']}_ClothRamp.png"
    if not source.is_file():
        return None
    asset_path = f"{ctx.names['texture_root']}/T_{ctx.names['character_id']}_ClothRamp"
    texture = unreal.EditorAssetLibrary.load_asset(asset_path)
    if texture is None:
        imported = import_one(source, ctx.names["texture_root"], destination_name=f"T_{ctx.names['character_id']}_ClothRamp")
        texture = imported[0] if imported else unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(texture, unreal.Texture2D):
        safe_set(texture, "srgb", True)
        safe_set(texture, "address_x", unreal.TextureAddress.TA_CLAMP)
        safe_set(texture, "address_y", unreal.TextureAddress.TA_CLAMP)
        safe_set(texture, "filter", unreal.TextureFilter.TF_BILINEAR)
        unreal.EditorAssetLibrary.save_loaded_asset(texture, False)
        return texture
    return None


def build(ctx: BuildContext) -> dict:
    ramp_texture = _resolve_ramp(ctx)
    if ramp_texture is None:
        return {"status": "skipped", "reason": "no cloth ramp texture available"}

    options = (ctx.material_map.get("specials", {}) or {}).get("cloth", {}) or {}
    special_scalars = options.get("scalars", {}) or {}
    special_vectors = options.get("vectors", {}) or {}

    def sc(name, default):
        return float(special_scalars.get(name, default))

    def vc(name, default):
        return tuple(special_vectors.get(name, default))

    families = set(options.get("families", CLOTH_FAMILIES))
    entries = [entry for entry in ctx.slot_entries() if entry.get("profile") in families]
    if not entries:
        return {"status": "skipped", "reason": "no cloth-family slots"}

    anchor = entries[0]
    base = ctx.texture_for(anchor["textures"].get("base_color")) or ctx.default_texture("base_color")
    normal = ctx.texture_for(anchor["textures"].get("normal")) or ctx.default_texture("normal")
    rmo = ctx.texture_for(anchor["textures"].get("rmo")) or ctx.default_texture("rmo")

    root = ctx.names["material_root"]
    material = load_or_create_material(ctx.names["cloth_asset"], root, fresh=True)
    for name, value in (
        ("material_domain", unreal.MaterialDomain.MD_SURFACE),
        ("blend_mode", unreal.BlendMode.BLEND_MASKED),
        ("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT),
        ("two_sided", True),
        ("opacity_mask_clip_value", 0.12),
        ("used_with_skeletal_mesh", True),
        ("used_with_morph_targets", True),
        ("tangent_space_normal", True),
    ):
        safe_set(material, name, value)

    base_node = texture_parameter(material, "BaseColorTexture", base, -1700, -300)
    tint = vector(material, "Tint", (1.0, 1.0, 1.0, 1.0), -1700, -100)
    base_tinted = expression(material, unreal.MaterialExpressionMultiply, -1450, -220)
    connect(base_node, "RGB", base_tinted, "A")
    connect(tint, "", base_tinted, "B")
    normal_node = texture_parameter(material, "NormalTexture", normal, -1700, 420, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    connect_property(normal_node, "RGB", unreal.MaterialProperty.MP_NORMAL)
    rmo_node = texture_parameter(material, "RMOTexture", rmo, -1700, 680, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    roughness_scale = scalar(material, "ClothRoughnessScale", sc("ClothRoughnessScale", 1.0), -1430, 720)
    roughness_scaled = expression(material, unreal.MaterialExpressionMultiply, -1200, 700)
    connect(rmo_node, "R", roughness_scaled, "A")
    connect(roughness_scale, "", roughness_scaled, "B")
    roughness_min = scalar(material, "ClothRoughnessMin", sc("ClothRoughnessMin", 0.34), -1200, 840)
    roughness_floor = expression(material, unreal.MaterialExpressionMax, -970, 700)
    connect(roughness_scaled, "", roughness_floor, "A")
    connect(roughness_min, "", roughness_floor, "B")
    roughness_max = scalar(material, "ClothRoughnessMax", sc("ClothRoughnessMax", 0.78), -970, 840)
    roughness = expression(material, unreal.MaterialExpressionMin, -740, 700)
    connect(roughness_floor, "", roughness, "A")
    connect(roughness_max, "", roughness, "B")
    connect_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
    metallic_scale = scalar(material, "ClothMetallicScale", 1.0, -1200, 980)
    metallic = expression(material, unreal.MaterialExpressionMultiply, -970, 960)
    connect(rmo_node, "G", metallic, "A")
    connect(metallic_scale, "", metallic, "B")
    connect_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    specular = scalar(material, "Specular", sc("Specular", 0.26), -740, 960)
    connect_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
    one = expression(material, unreal.MaterialExpressionConstant, -1200, 1120)
    safe_set(one, "r", 1.0)
    ao_influence = scalar(material, "AOInfluence", 0.30, -1200, 1240)
    ao = expression(material, unreal.MaterialExpressionLinearInterpolate, -970, 1120)
    connect(one, "", ao, "A")
    connect(rmo_node, "B", ao, "B")
    connect(ao_influence, "", ao, "Alpha")
    connect_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    alpha_scale = scalar(material, "AlphaScale", 1.0, -1430, 20)
    opacity = expression(material, unreal.MaterialExpressionMultiply, -1200, 0)
    connect(base_node, "A", opacity, "A")
    connect(alpha_scale, "", opacity, "B")
    connect_property(opacity, "", unreal.MaterialProperty.MP_OPACITY_MASK)

    pixel_normal = expression(material, unreal.MaterialExpressionPixelNormalWS, -1700, 1500)
    view = expression(material, unreal.MaterialExpressionCameraVectorWS, -1700, 1640)
    light = expression(material, unreal.MaterialExpressionSkyAtmosphereLightDirection, -1700, 1780)
    safe_set(light, "light_index", 0)
    nol = expression(material, unreal.MaterialExpressionDotProduct, -1430, 1500)
    connect(pixel_normal, "", nol, "A")
    connect(light, "", nol, "B")
    nol_sat = expression(material, unreal.MaterialExpressionSaturate, -1210, 1500)
    connect(nol, "", nol_sat, "")
    diffuse_row = expression(material, unreal.MaterialExpressionConstant, -1210, 1620)
    safe_set(diffuse_row, "r", 0.125)
    diffuse_uv = expression(material, unreal.MaterialExpressionAppendVector, -980, 1500)
    connect(nol_sat, "", diffuse_uv, "A")
    connect(diffuse_row, "", diffuse_uv, "B")
    ramp_diffuse = texture_parameter(material, "ToonRampTexture", ramp_texture, -740, 1440)
    connect(diffuse_uv, "", ramp_diffuse, "UVs")
    white = expression(material, unreal.MaterialExpressionConstant3Vector, -740, 1600)
    safe_set(white, "constant", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    diffuse_strength = scalar(material, "ClothDiffuseRampStrength", sc("ClothDiffuseRampStrength", 0.34), -740, 1740)
    diffuse_ramp_mix = expression(material, unreal.MaterialExpressionLinearInterpolate, -500, 1500)
    connect(white, "", diffuse_ramp_mix, "A")
    connect(ramp_diffuse, "RGB", diffuse_ramp_mix, "B")
    connect(diffuse_strength, "", diffuse_ramp_mix, "Alpha")
    stylized_base = expression(material, unreal.MaterialExpressionMultiply, -260, 200)
    connect(base_tinted, "", stylized_base, "A")
    connect(diffuse_ramp_mix, "", stylized_base, "B")
    connect_property(stylized_base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    ggx = expression(material, unreal.MaterialExpressionCustom, -980, 1940)
    ggx_inputs = []
    for input_name in ("N", "V", "L", "Roughness"):
        custom_input = unreal.CustomInput()
        custom_input.set_editor_property("input_name", input_name)
        ggx_inputs.append(custom_input)
    safe_set(ggx, "inputs", ggx_inputs)
    safe_set(ggx, "output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    safe_set(
        ggx,
        "code",
        """
float3 n = normalize(N);
float3 v = normalize(V);
float3 l = normalize(L);
float3 h = normalize(v + l);
float NoH = saturate(dot(n, h));
float r = clamp(Roughness, 0.08, 1.0);
float roughness2 = r * r;
float d = NoH * NoH * (roughness2 - 1.0) + 1.00001;
return saturate((roughness2 * roughness2) / (d * d));
""".strip(),
    )
    for source, output_name, input_name in (
        (pixel_normal, "", "N"),
        (view, "", "V"),
        (light, "", "L"),
        (roughness, "", "Roughness"),
    ):
        connect(source, output_name, ggx, input_name)
    spec_row = expression(material, unreal.MaterialExpressionConstant, -740, 2020)
    safe_set(spec_row, "r", 0.375)
    spec_uv = expression(material, unreal.MaterialExpressionAppendVector, -500, 1940)
    connect(ggx, "", spec_uv, "A")
    connect(spec_row, "", spec_uv, "B")
    ramp_spec = texture_parameter(material, "SpecularRampTexture", ramp_texture, -260, 1880)
    connect(spec_uv, "", ramp_spec, "UVs")
    spec_tint = vector(material, "ClothSpecRampTint", vc("ClothSpecRampTint", (1.0, 0.92, 0.88, 1.0)), -260, 2040)
    spec_strength = scalar(material, "ClothSpecRampStrength", sc("ClothSpecRampStrength", 0.05), -260, 2180)
    spec_color = expression(material, unreal.MaterialExpressionMultiply, 0, 1900)
    connect(ramp_spec, "RGB", spec_color, "A")
    connect(spec_tint, "", spec_color, "B")
    spec_scaled = expression(material, unreal.MaterialExpressionMultiply, 220, 1900)
    connect(spec_color, "", spec_scaled, "A")
    connect(spec_strength, "", spec_scaled, "B")
    spec_lit = expression(material, unreal.MaterialExpressionMultiply, 440, 1900)
    connect(spec_scaled, "", spec_lit, "A")
    connect(nol_sat, "", spec_lit, "B")
    connect_property(spec_lit, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, False)

    reparented = []
    for entry in entries:
        name = f"{ctx.names['instance_prefix']}_{material_asset_name(entry['slot'])}"
        instance = unreal.EditorAssetLibrary.load_asset(f"{root}/{name}")
        if not isinstance(instance, unreal.MaterialInstanceConstant):
            continue
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
        unreal.MaterialEditingLibrary.update_material_instance(instance)
        unreal.EditorAssetLibrary.save_loaded_asset(instance, False)
        reparented.append(instance.get_path_name())

    report = {
        "status": "success",
        "material": material.get_path_name(),
        "ramp": ramp_texture.get_path_name(),
        "reparented": reparented,
        "diffuse": "N.L -> ramp row V=0.125",
        "specular": "normalized GGX D -> ramp row V=0.375",
    }
    ctx.report_path("cloth_build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    print("MMD2UE_CLOTH " + json.dumps(build(ctx), ensure_ascii=False))


if __name__ == "__main__":
    main()
