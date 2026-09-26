"""Inspect whether an imported MMD character is suitable for face-SDF baking."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--face-slot", default="Face")
    return parser.parse_args(argv)


def vec(values) -> list[float]:
    return [float(value) for value in values]


def main() -> None:
    args = parse_args()
    wanted = args.face_slot.casefold()
    matches = []

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        slot_indices = [
            index
            for index, slot in enumerate(obj.material_slots)
            if slot.material and slot.material.name.casefold() == wanted
        ]
        if not slot_indices:
            continue

        face_polygons = [poly for poly in obj.data.polygons if poly.material_index in slot_indices]
        vertex_indices = sorted({index for poly in face_polygons for index in poly.vertices})
        world_vertices = [obj.matrix_world @ obj.data.vertices[index].co for index in vertex_indices]
        bounds_min = [min(vertex[axis] for vertex in world_vertices) for axis in range(3)]
        bounds_max = [max(vertex[axis] for vertex in world_vertices) for axis in range(3)]

        uv_layers = []
        for layer in obj.data.uv_layers:
            uvs = [
                layer.data[loop_index].uv
                for poly in face_polygons
                for loop_index in poly.loop_indices
            ]
            uv_layers.append(
                {
                    "name": layer.name,
                    "active_render": bool(layer.active_render),
                    "min": [min(uv.x for uv in uvs), min(uv.y for uv in uvs)],
                    "max": [max(uv.x for uv in uvs), max(uv.y for uv in uvs)],
                }
            )

        normal = Vector((0.0, 0.0, 0.0))
        for poly in face_polygons:
            normal += (obj.matrix_world.to_3x3() @ poly.normal) * poly.area
        if normal.length_squared:
            normal.normalize()

        matches.append(
            {
                "object": obj.name,
                "mesh": obj.data.name,
                "material_slot_indices": slot_indices,
                "polygon_count": len(face_polygons),
                "vertex_count": len(vertex_indices),
                "bounds_min": bounds_min,
                "bounds_max": bounds_max,
                "weighted_average_normal_world": vec(normal),
                "uv_layers": uv_layers,
                "shape_key_count": len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0,
                "armature": obj.parent.name if obj.parent and obj.parent.type == "ARMATURE" else None,
            }
        )

    result = {
        "blender_version": bpy.app.version_string,
        "blend_file": bpy.data.filepath,
        "face_slot": args.face_slot,
        "match_count": len(matches),
        "matches": matches,
        "sdf_bake_ready": bool(matches)
        and all(match["polygon_count"] > 0 and match["uv_layers"] for match in matches),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
