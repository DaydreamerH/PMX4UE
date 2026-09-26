"""Read-only armature/weight/UV audit for a prepared character .blend.

Usage: blender --background <character.blend> --python <this file> -- <report.json>
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import bpy


POSE_BONE_PATTERN = re.compile(r'pose\.bones\[(["\'])(.*?)\1\]')


def _path_bones(path: str) -> set[str]:
    return {match.group(2) for match in POSE_BONE_PATTERN.finditer(path or "")}


def collect_bone_references(armature) -> tuple[list[dict], list[str]]:
    """Collect known bone references; unscanned actions are conservative blockers."""
    references: list[dict] = []
    unscanned: list[str] = []
    for pose_bone in armature.pose.bones:
        for constraint in pose_bone.constraints:
            for property_name in ("subtarget", "pole_subtarget"):
                target = getattr(constraint, property_name, "")
                if target:
                    references.append({"kind": "constraint", "owner": pose_bone.name,
                                       "name": constraint.name, "target": target})
    for obj in bpy.data.objects:
        if obj.parent == armature and obj.parent_type == "BONE" and obj.parent_bone:
            references.append({"kind": "bone_parented_object", "owner": obj.name,
                               "target": obj.parent_bone})
    for datablock in [*bpy.data.objects, armature.data]:
        animation = getattr(datablock, "animation_data", None)
        if animation is None:
            continue
        for driver in animation.drivers:
            for name in _path_bones(driver.data_path):
                references.append({"kind": "driver_path", "owner": datablock.name,
                                   "path": driver.data_path, "target": name})
            for variable in driver.driver.variables:
                for target in variable.targets:
                    if getattr(target, "bone_target", ""):
                        references.append({"kind": "driver_target", "owner": datablock.name,
                                           "target": target.bone_target})
                    for name in _path_bones(getattr(target, "data_path", "")):
                        references.append({"kind": "driver_target_path", "owner": datablock.name,
                                           "target": name})
    for action in bpy.data.actions:
        try:
            curves = list(action.fcurves)
        except (AttributeError, RuntimeError):
            curves = []
        if not curves and len(getattr(action, "slots", [])) > 0:
            # Layered actions require slot/channelbag traversal. Refuse
            # automatic bone deletion rather than silently missing them.
            unscanned.append(action.name)
        for curve in curves:
            for name in _path_bones(curve.data_path):
                references.append({"kind": "action_curve", "owner": action.name,
                                   "path": curve.data_path, "target": name})
    return references, unscanned


def main() -> None:
    if "--" not in sys.argv:
        raise SystemExit("expected -- <report.json>")
    output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(armatures) != 1 or not meshes:
        raise RuntimeError(f"expected one armature and mesh, got {len(armatures)} / {len(meshes)}")

    armature = armatures[0]
    weight_stats = defaultdict(lambda: {"vertices": 0, "sum": 0.0, "max": 0.0})
    mesh_info = []
    for mesh in meshes:
        group_names = {group.index: group.name for group in mesh.vertex_groups}
        for vertex in mesh.data.vertices:
            for assignment in vertex.groups:
                if assignment.weight <= 0:
                    continue
                stats = weight_stats[group_names[assignment.group]]
                stats["vertices"] += 1
                stats["sum"] += assignment.weight
                stats["max"] = max(stats["max"], assignment.weight)
        mesh_info.append({
            "name": mesh.name,
            "vertices": len(mesh.data.vertices),
            "uv_layers": [layer.name for layer in mesh.data.uv_layers],
            "material_slots": [slot.material.name if slot.material else None for slot in mesh.material_slots],
        })

    bones = []
    for bone in armature.data.bones:
        stats = weight_stats.get(bone.name, {"vertices": 0, "sum": 0.0, "max": 0.0})
        bones.append({
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "children": [child.name for child in bone.children],
            "deform": bool(bone.use_deform),
            "length": float(bone.length),
            "head": list(bone.head_local),
            "tail": list(bone.tail_local),
            "weight": stats,
        })

    report = {
        "schema": "mmd2ue.skeleton-audit.v1",
        "blend": bpy.data.filepath,
        "source_file": {
            "size": Path(bpy.data.filepath).stat().st_size,
            "mtime_ns": Path(bpy.data.filepath).stat().st_mtime_ns,
        },
        "armature": armature.name,
        "bone_count": len(bones),
        "meshes": mesh_info,
        "bones": bones,
        "unmatched_weight_groups": sorted(set(weight_stats) - {bone.name for bone in armature.data.bones}),
    }
    references, unscanned = collect_bone_references(armature)
    report["bone_references"] = references
    report["unscanned_actions"] = unscanned
    report["bone_references_checked"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "bones": len(bones), "meshes": len(meshes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
