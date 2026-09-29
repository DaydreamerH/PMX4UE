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


def enable_mmd_metadata(armature):
    # A fresh background Blender does not necessarily register saved PropertyGroups.
    if any("mmd_bone" in bone for bone in armature.pose.bones) and not hasattr(bpy.types.PoseBone, "mmd_bone"):
        import addon_utils
        addon_utils.enable("mmd_tools")
        if not hasattr(bpy.types.PoseBone, "mmd_bone"):
            raise RuntimeError("Cannot read stored MMD bone metadata; enable compatible mmd_tools")


def _path_bones(path: str) -> set[str]:
    return {match.group(2) for match in POSE_BONE_PATTERN.finditer(path or "")}


def collect_bone_references(armature) -> tuple[list[dict], list[str]]:
    """Collect known bone references; unscanned actions are conservative blockers."""
    references: list[dict] = []
    unscanned: list[str] = []
    for pose_bone in armature.pose.bones:
        mmd = getattr(pose_bone, "mmd_bone", None)
        if mmd and (mmd.has_additional_rotation or mmd.has_additional_location):
            references.append(dict(kind="pmx_append", owner=pose_bone.name,
                                   target=mmd.additional_transform_bone))
        for constraint in pose_bone.constraints:
            for property_name in ("subtarget", "pole_subtarget"):
                target = getattr(constraint, property_name, "")
                if target:
                    references.append({"kind": "constraint", "owner": pose_bone.name,
                                       "name": constraint.name, "target": target})
    for obj in bpy.data.objects:
        root = getattr(obj, "mmd_root", None)
        if root and getattr(obj, "mmd_type", "") == "ROOT":
            for morph in root.bone_morphs:
                for entry in morph.data:
                    if entry.bone:
                        references.append(dict(kind="bone_morph", owner=morph.name, target=entry.bone))
        # Rigid-body bindings and object-level bone constraints are not pose constraints.
        for constraint in obj.constraints:
            for property_name in ("subtarget", "pole_subtarget"):
                target = getattr(constraint, property_name, "")
                if target:
                    references.append({"kind": "object_constraint", "owner": obj.name,
                                       "name": constraint.name, "target": target})
        for owner in [obj, *([*obj.pose.bones] if obj.type == "ARMATURE" else [])]:
            for constraint in owner.constraints:
                for entry in getattr(constraint, "targets", []):
                    if getattr(entry, "subtarget", ""):
                        references.append({"kind": "armature_constraint_target", "owner": owner.name,
                                           "name": constraint.name, "target": entry.subtarget})
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


def collect_control_facts(armature):
    facts = {}
    for bone in armature.pose.bones:
        mmd = getattr(bone, "mmd_bone", None)
        append = None
        if mmd and (mmd.has_additional_rotation or mmd.has_additional_location):
            append = dict(source=mmd.additional_transform_bone, rotation=bool(mmd.has_additional_rotation),
                          translation=bool(mmd.has_additional_location), factor=float(mmd.additional_transform_influence))
        matrix = bone.matrix_basis
        neutral = max(abs(matrix[r][c] - float(r == c)) for r in range(4) for c in range(4)) < 1e-6
        facts[bone.name] = dict(neutral=neutral, append=append,
                               source_name=getattr(mmd, "name_j", ""), source_name_e=getattr(mmd, "name_e", ""))
    return facts


def main() -> None:
    if "--" not in sys.argv:
        raise SystemExit("expected -- <report.json>")
    output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(armatures) != 1 or not meshes:
        raise RuntimeError(f"expected one armature and mesh, got {len(armatures)} / {len(meshes)}")

    armature = armatures[0]
    enable_mmd_metadata(armature)
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
    report["control_facts"] = collect_control_facts(armature)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "bones": len(bones), "meshes": len(meshes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
