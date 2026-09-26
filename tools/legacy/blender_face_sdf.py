"""Bake a reusable RGBA anime face-SDF control texture in Blender.

R stores the shadow-onset threshold, G/B store the animated highlight window,
and A stores the face-shadow application mask.  The source .blend is never
saved; all temporary geometry and materials exist only in the batch process.

Run:
  blender --background <file>.blend --python blender_face_sdf.py -- \
      --character-id MyCharacter --output-dir Artifacts/MyCharacter/SDF/final --model-faces +Y
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from pathlib import Path

import bmesh
import bpy
import numpy as np

MODEL_FACING_YAW = {"-Y": 0.0, "+Y": 180.0, "+X": 90.0, "-X": 270.0}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-name")
    parser.add_argument("--face-slot", default="Face")
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--frames", type=int, default=17)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--despeckle", type=int, default=2)
    parser.add_argument("--model-faces", choices=("-Y", "+Y", "+X", "-X"), default="-Y")
    return parser.parse_args(argv)


def majority_filter(mask: np.ndarray, passes: int) -> np.ndarray:
    for _ in range(passes):
        neighbors = np.zeros_like(mask, dtype=np.uint8)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbors += np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
        mask = neighbors >= 5
    return mask


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep the largest 4-connected UV island (the central face shell)."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    largest: list[tuple[int, int]] = []
    for start_y, start_x in zip(*np.nonzero(mask & ~visited)):
        if visited[start_y, start_x]:
            continue
        queue = deque([(int(start_y), int(start_x))])
        visited[start_y, start_x] = True
        component: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            component.append((y, x))
            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        if len(component) > len(largest):
            largest = component
    result = np.zeros_like(mask, dtype=bool)
    for y, x in largest:
        result[y, x] = True
    return result


def edt_1d(values: np.ndarray) -> np.ndarray:
    """Squared Euclidean distance transform (Felzenszwalb/Huttenlocher)."""
    count = values.shape[0]
    sites = np.zeros(count, dtype=np.int32)
    boundaries = np.empty(count + 1, dtype=np.float64)
    result = np.empty(count, dtype=np.float64)
    k = 0
    sites[0] = 0
    boundaries[0] = -np.inf
    boundaries[1] = np.inf
    for q in range(1, count):
        while True:
            p = sites[k]
            intersection = ((values[q] + q * q) - (values[p] + p * p)) / (2.0 * (q - p))
            if intersection > boundaries[k] or k == 0:
                break
            k -= 1
        if intersection <= boundaries[k]:
            intersection = -np.inf
        k += 1
        sites[k] = q
        boundaries[k] = intersection
        boundaries[k + 1] = np.inf
    k = 0
    for q in range(count):
        while boundaries[k + 1] < q:
            k += 1
        delta = q - sites[k]
        result[q] = delta * delta + values[sites[k]]
    return result


def distance_to(feature: np.ndarray) -> np.ndarray:
    height, width = feature.shape
    infinity = float(width * width + height * height + 1)
    work = np.where(feature, 0.0, infinity)
    vertical = np.empty_like(work)
    for x in range(width):
        vertical[:, x] = edt_1d(work[:, x])
    squared = np.empty_like(work)
    for y in range(height):
        squared[y, :] = edt_1d(vertical[y, :])
    return np.sqrt(squared)


def signed_distance(mask: np.ndarray) -> np.ndarray:
    return distance_to(~mask) - distance_to(mask)


def shadow_threshold_from_masks(masks: list[np.ndarray]) -> np.ndarray:
    stack = np.stack(masks).astype(bool)
    stack = np.logical_and.accumulate(stack, axis=0)
    frame_count, height, width = stack.shape
    threshold = np.where(stack[0], 1.0, 0.0).astype(np.float32)
    previous_sdf = signed_distance(stack[0])
    for index in range(frame_count - 1):
        current = stack[index]
        following = stack[index + 1]
        following_sdf = signed_distance(following)
        crossing = current & ~following
        denominator = previous_sdf - following_sdf
        fraction = np.divide(
            previous_sdf,
            denominator,
            out=np.full_like(previous_sdf, 0.5),
            where=np.abs(denominator) > 1.0e-6,
        )
        value = (index + np.clip(fraction, 0.0, 1.0)) / float(frame_count - 1)
        threshold[crossing] = value[crossing]
        previous_sdf = following_sdf
    threshold[stack[-1]] = 1.0
    return threshold


def ellipse(uv_x, uv_y, center_x, center_y, radius_x, radius_y):
    return ((uv_x - center_x) / radius_x) ** 2 + ((uv_y - center_y) / radius_y) ** 2 <= 1.0


def highlight_thresholds(resolution: int, face_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:resolution, 0:resolution]
    u = (x + 0.5) / resolution
    v = (y + 0.5) / resolution
    nose = ellipse(u, v, 0.5, 0.47, 0.045, 0.09)
    lips = ellipse(u, v, 0.5, 0.285, 0.075, 0.026)
    area = (nose | lips) & face_mask
    center = np.clip(0.5 + (u - 0.5) * 3.0, 0.08, 0.92)
    half_width = np.where(nose, 0.11, 0.075)
    green = np.where(area, np.clip(center + half_width, 0.0, 1.0), 0.0)
    blue = np.where(area, np.clip(1.0 - center + half_width, 0.0, 1.0), 0.0)
    return green.astype(np.float32), blue.astype(np.float32)


def find_face_source(face_slot: str) -> tuple[bpy.types.Object, int]:
    wanted = face_slot.casefold()
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for index, slot in enumerate(obj.material_slots):
            if slot.material and slot.material.name.casefold() == wanted:
                return obj, index
    raise RuntimeError(f"Material slot not found: {face_slot}")


def make_face_only_object(source: bpy.types.Object, material_index: int) -> bpy.types.Object:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
    face_obj = bpy.data.objects.new("SDF_FaceOnly", mesh)
    bpy.context.scene.collection.objects.link(face_obj)
    face_obj.matrix_world = source.matrix_world.copy()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    remove = [face for face in bm.faces if face.material_index != material_index]
    bmesh.ops.delete(bm, geom=remove, context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    if not mesh.polygons:
        raise RuntimeError("Face material slot contains no polygons")
    return face_obj


def make_bake_material(image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.new("SDF_BakeMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    diffuse.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    target = nodes.new("ShaderNodeTexImage")
    target.image = image
    nodes.active = target
    material.node_tree.links.new(diffuse.outputs[0], output.inputs["Surface"])
    return material


def make_coverage_material(image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.new("SDF_CoverageMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    target = nodes.new("ShaderNodeTexImage")
    target.image = image
    nodes.active = target
    material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return material


def save_rgba(path: Path, rgba: np.ndarray) -> None:
    height, width, _ = rgba.shape
    image = bpy.data.images.new("FaceSDF_RGBA", width, height, alpha=True, float_buffer=False)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(rgba.astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def main() -> None:
    args = parse_args()
    if args.frames < 3 or args.frames % 2 == 0:
        raise RuntimeError("--frames must be an odd number >= 3")
    output_dir = Path(args.output_dir).resolve()
    output_name = args.output_name or f"T_{args.character_id}_FaceSDF_RGBA.png"
    masks_dir = output_dir / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)
    for stale in masks_dir.glob("*.png"):
        stale.unlink()

    source, face_material_index = find_face_source(args.face_slot)
    source.hide_render = True
    face_obj = make_face_only_object(source, face_material_index)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.world = None
    for obj in scene.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True

    bake_image = bpy.data.images.new("SDF_BakeTarget", args.resolution, args.resolution, alpha=False, float_buffer=True)
    bake_image.colorspace_settings.name = "Non-Color"
    bake_material = make_bake_material(bake_image)
    face_obj.data.materials.clear()
    face_obj.data.materials.append(bake_material)
    for polygon in face_obj.data.polygons:
        polygon.material_index = 0

    sun_data = bpy.data.lights.new("SDF_Sun", "SUN")
    sun_data.energy = 1.0
    sun_data.angle = 0.0
    sun = bpy.data.objects.new("SDF_Sun", sun_data)
    scene.collection.objects.link(sun)
    bpy.ops.object.select_all(action="DESELECT")
    face_obj.select_set(True)
    bpy.context.view_layer.objects.active = face_obj

    base_yaw = MODEL_FACING_YAW[args.model_faces]
    pixel_buffer = np.empty(args.resolution * args.resolution * 4, dtype=np.float32)
    masks: list[np.ndarray] = []
    reference_max = None
    for index, angle in enumerate(np.linspace(0.0, 180.0, args.frames)):
        sun.rotation_euler = (math.radians(90.0), 0.0, math.radians(base_yaw + angle))
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT"}, margin=8, use_clear=True)
        bake_image.pixels.foreach_get(pixel_buffer)
        red = pixel_buffer.reshape(args.resolution, args.resolution, 4)[:, :, 0]
        if reference_max is None:
            reference_max = float(red.max())
            if reference_max <= 0.0:
                raise RuntimeError("Front-lit bake is black; check --model-faces")
        mask = red > args.threshold * reference_max
        mask = majority_filter(mask, args.despeckle)
        masks.append(mask)
        preview = np.ones((args.resolution, args.resolution, 4), dtype=np.float32)
        preview[:, :, :3] = mask[:, :, None]
        save_rgba(masks_dir / f"mask_{index:02d}_{int(round(angle)):03d}deg.png", preview)
        print(f"[SDF] baked {index + 1}/{args.frames}: {angle:.2f} degrees")

    red = shadow_threshold_from_masks(masks)
    coverage_material = make_coverage_material(bake_image)
    face_obj.data.materials[0] = coverage_material
    bpy.ops.object.bake(type="EMIT", margin=8, use_clear=True)
    bake_image.pixels.foreach_get(pixel_buffer)
    coverage = pixel_buffer.reshape(args.resolution, args.resolution, 4)[:, :, 0] > 0.5
    alpha = largest_component(coverage).astype(np.float32)
    green, blue = highlight_thresholds(args.resolution, alpha > 0.5)
    rgba = np.stack((red, green, blue, alpha), axis=2)
    output_path = output_dir / output_name
    save_rgba(output_path, rgba)
    opaque = np.ones_like(red, dtype=np.float32)
    for name, channel in (("R_ShadowThreshold", red), ("G_HighlightUpper", green),
                          ("B_HighlightLower", blue), ("A_FaceMask", alpha)):
        preview = np.stack((channel, channel, channel, opaque), axis=2)
        save_rgba(output_dir / f"debug_{name}.png", preview)

    report = {
        "schema": "mmd2ue.face-sdf.v1",
        "blender_version": bpy.app.version_string,
        "source_blend": bpy.data.filepath,
        "source_object": source.name,
        "character_id": args.character_id,
        "face_slot": args.face_slot,
        "face_polygons": len(face_obj.data.polygons),
        "resolution": args.resolution,
        "frames": args.frames,
        "samples": args.samples,
        "texture": str(output_path),
        "channels": {
            "R": "shadow onset threshold",
            "G": "nose/lip highlight upper threshold",
            "B": "one minus nose/lip highlight lower threshold",
            "A": "face shadow mask",
        },
    }
    (output_dir / "face_sdf_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
