"""Prepare one PMX character for the MMD2UE pipeline.

This script is intentionally deterministic and headless-friendly.  It keeps the
original source untouched, imports through the installed mmd_tools extension,
exports a skeletal FBX, and writes a sidecar manifest for the UE stage.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import bpy
import addon_utils
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from framework.blender_fbx_units import (
    assert_cm_native_contract, audit_fbx_units, prepare_cm_native_scene,
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--scale", type=float, default=0.08)
    parser.add_argument("--fbx-units", choices=("legacy", "cm-native"), default="legacy",
                        help="cm-native is an isolated centimeter-baked FBX; legacy preserves old output")
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.armatures,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def image_path(image: bpy.types.Image) -> str | None:
    try:
        path = bpy.path.abspath(image.filepath)
    except Exception:
        return None
    return os.path.normpath(path) if path else None


def collect_material(material: bpy.types.Material) -> dict:
    images = []
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.image:
                path = image_path(node.image)
                images.append(
                    {
                        "node": node.name,
                        "image": node.image.name,
                        "path": path,
                        "colorspace": getattr(node.image.colorspace_settings, "name", None),
                    }
                )
    return {
        "name": material.name,
        "diffuse_color": list(material.diffuse_color),
        "blend_method": getattr(material, "surface_render_method", None)
        or getattr(material, "blend_method", None),
        "use_nodes": material.use_nodes,
        "images": images,
    }


def copy_source_textures(source_root: Path, texture_out: Path) -> list[str]:
    texture_out.mkdir(parents=True, exist_ok=True)
    extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".dds", ".exr"}
    copied = []
    for src in sorted(source_root.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in extensions:
            continue
        rel = src.relative_to(source_root)
        dst = texture_out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(str(rel).replace("\\", "/"))
    return copied


def object_bounds(objects: list[bpy.types.Object]) -> dict:
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        points.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
    if not points:
        return {"min": [0, 0, 0], "max": [0, 0, 0], "height": 0}
    mins = [min(p[i] for p in points) for i in range(3)]
    maxs = [max(p[i] for p in points) for i in range(3)]
    return {"min": mins, "max": maxs, "height": maxs[2] - mins[2]}


def main() -> None:
    args = parse_args()
    pmx_path = Path(args.pmx).resolve()
    source_root = Path(args.source_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    texture_dir = out_dir / "textures"
    fbx_path = out_dir / f"{args.character_id}.fbx"
    blend_path = out_dir / f"{args.character_id}.blend"
    manifest_path = out_dir / "blender_manifest.json"
    log_path = out_dir / "blender_prepare.log"
    if args.fbx_units == "cm-native":
        existing = [str(path) for path in (fbx_path, blend_path, manifest_path)
                    if path.exists()]
        if existing:
            raise FileExistsError(f"experimental centimeter export refuses to overwrite: {existing}")

    reset_scene()
    addon_utils.enable("mmd_tools")
    print(f"[MMD2UE] importing {pmx_path}")
    import_options = {
        "filepath": str(pmx_path), "types": {"MESH", "ARMATURE", "MORPHS"},
        "scale": args.scale, "clean_model": True, "remove_doubles": False,
        "rename_bones": True, "use_underscore": True, "dictionary": "INTERNAL",
        "use_mipmap": True, "sph_blend_factor": 1.0, "spa_blend_factor": 1.0,
    }
    available = bpy.ops.mmd_tools.import_model.get_rna_type().properties.keys()
    if "fix_bone_order" in available:
        import_options["fix_bone_order"] = True
    else:
        print("[MMD2UE] mmd_tools has no fix_bone_order option; bone order must be audited")
    if "fix_ik_links" in available:
        import_options["fix_ik_links"] = False
    elif "fix_IK_links" in available:
        import_options["fix_IK_links"] = False
    else:
        raise RuntimeError("mmd_tools has no recognized IK-link import option")
    result = bpy.ops.mmd_tools.import_model(**import_options)
    if result != {"FINISHED"}:
        raise RuntimeError(f"mmd_tools import failed: {result}")

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not meshes or not armatures:
        raise RuntimeError(f"expected mesh and armature, got meshes={len(meshes)} armatures={len(armatures)}")

    armature = armatures[0]
    armature.name = f"SK_{args.character_id}_Skeleton"
    for index, mesh in enumerate(meshes, start=1):
        mesh.name = f"SK_{args.character_id}_Mesh_{index:02d}"

    # Keep the editable Blender source in meters. The centimeter conversion is
    # applied only to the in-memory export copy after the .blend is saved.
    bounds = object_bounds(meshes)
    if args.fbx_units == "cm-native":
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        prepare_cm_native_scene(armature, meshes)

    # Export only the render mesh and armature.  MMD physics/display helpers are
    # intentionally excluded from this first visual pass and remain in the PMX.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes + [armature]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature

    print(f"[MMD2UE] exporting {fbx_path}")
    bpy.ops.export_scene.fbx(
        filepath=str(fbx_path),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        use_mesh_modifiers=False,
        use_armature_deform_only=False,
        add_leaf_bones=False,
        bake_anim=False,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS" if args.fbx_units == "cm-native" else "FBX_SCALE_NONE",
        global_scale=1.0,
        axis_forward="-Z",
        axis_up="Y",
        mesh_smooth_type="FACE",
        use_tspace=True,
        use_custom_props=True,
        path_mode="COPY",
        embed_textures=False,
    )
    bone_samples = {}
    if args.fbx_units == "cm-native":
        for bone in armature.data.bones:
            if bone.parent:
                length = (bone.head_local - bone.parent.head_local).length
                if length > 25.0:
                    bone_samples[bone.name] = length
                    break
        if not bone_samples:
            raise RuntimeError("no suitable centimeter bone offset to verify FBX export")
    fbx_units = audit_fbx_units(fbx_path, armature.name,
                                [mesh.name for mesh in meshes], bone_samples)
    if args.fbx_units == "cm-native":
        assert_cm_native_contract(fbx_units)

    copied_textures = copy_source_textures(source_root, texture_dir)
    manifest = {
        "schema": "mmd2ue.blender-manifest.v1",
        "character_id": args.character_id,
        "source": {"pmx": str(pmx_path), "root": str(source_root)},
        "outputs": {"fbx": str(fbx_path), "blend": str(blend_path), "textures": str(texture_dir)},
        "scale": args.scale,
        "fbx_units_mode": args.fbx_units,
        "fbx_units": fbx_units,
        "bounds": bounds,
        "armature": {
            "name": armature.name,
            "bones": [bone.name for bone in armature.data.bones],
            "bone_count": len(armature.data.bones),
        },
        "meshes": [
            {
                "name": mesh.name,
                "vertices": len(mesh.data.vertices),
                "polygons": len(mesh.data.polygons),
                "materials": [slot.material.name if slot.material else None for slot in mesh.material_slots],
                "shape_keys": [key.name for key in mesh.data.shape_keys.key_blocks] if mesh.data.shape_keys else [],
            }
            for mesh in meshes
        ],
        "materials": [collect_material(material) for material in bpy.data.materials],
        "textures": copied_textures,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.fbx_units == "legacy":
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    log_path.write_text("MMD2UE Blender preparation completed.\n", encoding="utf-8")
    print(json.dumps({"fbx": str(fbx_path), "height": bounds["height"], "meshes": len(meshes), "bones": len(armature.data.bones)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
