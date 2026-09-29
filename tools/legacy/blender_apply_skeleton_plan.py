"""Safely derive a skeletal variant from an explicit skeleton_plan.py plan.

Usage: blender --background SOURCE.blend --python this_file --
       --plan plan.json --out-blend NEW.blend --out-fbx NEW.fbx --report report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from blender_skeleton_audit import collect_bone_references, collect_control_facts, enable_mmd_metadata
from skeleton_plan import verify_postconditions
from blender_fbx_units import prepare_cm_native_scene, audit_fbx_units, assert_cm_native_contract
sys.path.insert(0,str(SCRIPT_DIR.parent))
from blender_fbx_bind import normalize as normalize_fbx_bind


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out-blend", required=True, type=Path)
    parser.add_argument("--out-fbx", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--cm-native", action="store_true",
                        help="Bake mesh, morphs and rest bones to centimeters; FBX root scale stays 1")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def _evaluated_positions(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    result = {}
    for mesh in meshes:
        evaluated = mesh.evaluated_get(depsgraph)
        evaluated_mesh = evaluated.to_mesh()
        result[mesh.name] = [tuple(evaluated.matrix_world @ vertex.co) for vertex in evaluated_mesh.vertices]
        evaluated.to_mesh_clear()
    return result


def _pose_samples(armature, meshes, roles):
    names = {side: roles[side] for side in ("left", "right")}
    poses = {"rest": {}}
    for side, sign in (("left", 1), ("right", -1)):
        joint = names[side]
        has_shoulder = joint["shoulder"] in armature.pose.bones
        if has_shoulder:
            poses[f"shoulder_{side}"] = {joint["shoulder"]: (0, 0, 30 * sign)}
        poses[f"elbow_{side}"] = {joint["elbow"]: (0, 0, 60 * sign)}
        poses[f"wrist_{side}"] = {joint["wrist"]: (35 * sign, 0, 0)}
        combined = {
            joint["elbow"]: (0, 0, 60 * sign),
            joint["wrist"]: (35 * sign, 0, 0),
        }
        if has_shoulder:
            combined[joint["shoulder"]] = (0, 0, 20 * sign)
        poses[f"combined_{side}"] = combined
    original = {bone.name: (bone.rotation_mode, bone.matrix_basis.copy()) for bone in armature.pose.bones}
    result = {}
    try:
        for label, rotations in poses.items():
            for bone in armature.pose.bones:
                bone.rotation_mode = "XYZ"
                bone.rotation_euler = (0, 0, 0)
                bone.location = (0, 0, 0)
                bone.scale = (1, 1, 1)
            for name, angles in rotations.items():
                armature.pose.bones[name].rotation_euler = tuple(math.radians(value) for value in angles)
            bpy.context.view_layer.update()
            result[label] = _evaluated_positions(meshes)
    finally:
        for bone in armature.pose.bones:
            bone.rotation_mode = original[bone.name][0]
            bone.matrix_basis = original[bone.name][1]
        bpy.context.view_layer.update()
    return result


def _max_position_delta(before, after):
    maximum = 0.0
    for label, old_meshes in before.items():
        if label not in after or old_meshes.keys() != after[label].keys():
            raise RuntimeError(f"pose/mesh set changed: {label}")
        for mesh, old_vertices in old_meshes.items():
            new_vertices = after[label][mesh]
            if len(old_vertices) != len(new_vertices):
                raise RuntimeError(f"vertex count changed: {label}/{mesh}")
            for old, new in zip(old_vertices, new_vertices):
                maximum = max(maximum, math.dist(old, new))
    return maximum


def _validate_plan(plan, armature, meshes):
    if plan.get("schema") != "mmd2ue.skeleton-edit-plan.v1" or plan.get("status") != "ready":
        raise RuntimeError("only a ready, reviewed skeleton-edit-plan.v1 can be applied")
    if not plan.get("operations"):
        raise RuntimeError("plan contains no operations")
    if os.path.normcase(os.path.abspath(plan.get("source_blend") or "")) != os.path.normcase(os.path.abspath(bpy.data.filepath)):
        raise RuntimeError("loaded blend differs from plan source_blend")
    source_file = Path(bpy.data.filepath).stat()
    identity = plan.get("source_file") or {}
    if identity.get("size") != source_file.st_size or identity.get("mtime_ns") != source_file.st_mtime_ns:
        raise RuntimeError("source blend changed since skeleton audit; regenerate the plan")
    if len(armature.data.bones) != plan["source_bone_count"]:
        raise RuntimeError("bone count changed since audit; regenerate the plan")
    deleted = {op["bone"] for op in plan["operations"] if op["op"] == "delete_unweighted_leaf"}
    reparented = {op["bone"] for op in plan["operations"] if op["op"] == "reparent"}
    references, unscanned = collect_bone_references(armature)
    controls = set(plan.get("compatibility", {}).get("neutral_controls", []))
    facts = collect_control_facts(armature)
    if any(not facts.get(name, {}).get("neutral") for name in controls):
        raise RuntimeError("UE-FK shoulder controls must remain neutral; regenerate the plan")
    if any(ref.get("target") in controls and ref.get("kind") in
           {"bone_morph", "action_curve", "driver_path", "driver_target", "driver_target_path"} for ref in references):
        raise RuntimeError("UE-FK shoulder controls have animation/morph/driver dependencies")
    if unscanned or any(ref["target"] in deleted or
                        (ref["kind"] == "action_curve" and ref["target"] in reparented)
                        for ref in references):
        raise RuntimeError("bone reference/action changed since audit; regenerate the plan")
    for mesh in meshes:
        groups = {group.index: group.name for group in mesh.vertex_groups}
        for vertex in mesh.data.vertices:
            for assignment in vertex.groups:
                if groups.get(assignment.group) in deleted and assignment.weight > 1e-8:
                    raise RuntimeError("a bone to delete carries vertex weight")
    original_parents = {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}
    simulated = dict(original_parents)
    seen_reparents = set()
    for op in plan["operations"]:
        name = op["bone"]
        if name not in simulated:
            raise RuntimeError(f"missing or already deleted bone: {name}")
        if simulated[name] != op["expected_parent"]:
            raise RuntimeError(f"stale plan at {name}: {simulated[name]} != {op['expected_parent']}")
        if op["op"] == "reparent":
            parent = op["new_parent"]
            if name in seen_reparents or parent not in simulated:
                raise RuntimeError(f"invalid reparent: {name} -> {parent}")
            seen_reparents.add(name)
            current = parent
            while current is not None:
                if current == name:
                    raise RuntimeError(f"reparent creates a cycle: {name} -> {parent}")
                current = simulated.get(current)
            simulated[name] = parent
        elif op["op"] == "delete_unweighted_leaf":
            if name not in deleted or name in simulated.values():
                raise RuntimeError(f"cannot delete non-leaf bone: {name}")
            del simulated[name]
        else:
            raise RuntimeError(f"unknown operation: {op['op']}")


def main():
    args = _args()
    outputs = [path.resolve() for path in (args.out_blend, args.out_fbx, args.report)]
    if len(set(outputs)) != 3 or any(path.exists() for path in outputs):
        raise RuntimeError("derived outputs must be distinct and must not already exist")
    if any(path == Path(bpy.data.filepath).resolve() or path == args.plan.resolve() for path in outputs):
        raise RuntimeError("output path overlaps source blend or plan")
    if len({path.parent for path in outputs}) != 1:
        raise RuntimeError("derived blend, FBX and report must share one output directory")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(armatures) != 1 or not meshes:
        raise RuntimeError("expected exactly one armature and at least one mesh")
    armature = armatures[0]
    enable_mmd_metadata(armature)
    _validate_plan(plan, armature, meshes)
    before_poses = _pose_samples(armature, meshes, plan["roles"])
    before_bones = {bone.name: bone.matrix_local.copy() for bone in armature.data.bones}
    before_groups = {mesh.name: [(group.name, group.index) for group in mesh.vertex_groups] for mesh in meshes}

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for op in plan["operations"]:
            bone = armature.data.edit_bones.get(op["bone"])
            if bone is None or (bone.parent.name if bone.parent else None) != op["expected_parent"]:
                raise RuntimeError(f"edit-mode hierarchy changed at {op['bone']}")
            if op["op"] == "reparent":
                matrix, length = bone.matrix.copy(), bone.length
                bone.use_connect = False
                bone.parent = armature.data.edit_bones[op["new_parent"]]
                bone.matrix = matrix
                bone.length = length
            else:
                if bone.children:
                    raise RuntimeError(f"cannot delete non-leaf edit bone {bone.name}")
                armature.data.edit_bones.remove(bone)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()

    for mesh in meshes:
        if before_groups[mesh.name] != [(group.name, group.index) for group in mesh.vertex_groups]:
            raise RuntimeError(f"vertex groups changed: {mesh.name}")
    remaining = armature.data.bones
    final_parents = {bone.name: bone.parent.name if bone.parent else None for bone in remaining}
    postconditions = verify_postconditions(plan, final_parents)
    if len(remaining) != len(before_bones) - sum(op["op"] == "delete_unweighted_leaf" for op in plan["operations"]):
        raise RuntimeError("unexpected bone count after edit")
    max_bone_delta = max(
        abs(old - new)
        for bone in remaining
        for old_row, new_row in zip(before_bones[bone.name], bone.matrix_local)
        for old, new in zip(old_row, new_row)
    )
    after_poses = _pose_samples(armature, meshes, plan["roles"])
    rest_delta = _max_position_delta({"rest": before_poses["rest"]}, {"rest": after_poses["rest"]})
    pose_deltas = {label: _max_position_delta({label: old}, {label: after_poses[label]})
                   for label, old in before_poses.items() if label != "rest"}
    if max_bone_delta > plan["max_allowed_bone_matrix_delta"] or rest_delta > plan["max_allowed_vertex_delta"] \
            or max(pose_deltas.values(), default=0) > plan["max_allowed_pose_delta"]:
        raise RuntimeError(f"deformation tolerance exceeded: bone={max_bone_delta}, rest={rest_delta}, poses={pose_deltas}")

    if args.cm_native:
        prepare_cm_native_scene(armature, meshes)
        armature.data.pose_position = "POSE"
        centimeter_poses = _pose_samples(armature, meshes, plan["roles"])
        normalized = {label: {name: [tuple(value / 100.0 for value in vertex)
                                     for vertex in vertices] for name, vertices in data.items()}
                      for label, data in centimeter_poses.items()}
        cm_delta = _max_position_delta(after_poses, normalized)
        if cm_delta > plan["max_allowed_pose_delta"]:
            raise RuntimeError(f"centimeter bake changed deformation: {cm_delta}")
    else:
        cm_delta = None

    report = {
        "schema": "mmd2ue.skeleton-apply.v1", "status": "validated_variant_exported",
        "source_blend": plan["source_blend"], "derived_blend": str(outputs[0]),
        "derived_fbx": str(outputs[1]), "operations": plan["operations"],
        "source_bone_count": len(before_bones), "derived_bone_count": len(remaining),
        "weight_groups_unchanged": True, "max_rest_vertex_delta": rest_delta,
        "max_rest_bone_matrix_delta": max_bone_delta, "pose_max_deltas": pose_deltas,
        "animation_validation": "pending",
        "postconditions": postconditions, "final_bone_parents": final_parents,
        "compatibility": plan.get("compatibility"),
        "fbx_units": "centimeter_native_root_scale_1" if args.cm_native else "legacy",
        "max_cm_bake_pose_delta_m": cm_delta,
    }
    output_dir = outputs[0].parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mmd2ue-skeleton-", dir=output_dir) as temporary:
        stage = Path(temporary)
        staged_blend, staged_fbx, staged_report = (stage / path.name for path in outputs)
        bpy.ops.wm.save_as_mainfile(filepath=str(staged_blend))
        bpy.ops.object.select_all(action="DESELECT")
        for mesh in meshes:
            mesh.select_set(True)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        raw_fbx = stage / 'raw_bind.fbx' if args.cm_native else staged_fbx
        bpy.ops.export_scene.fbx(
            filepath=str(raw_fbx), use_selection=True, object_types={"ARMATURE", "MESH"},
            use_mesh_modifiers=False, use_armature_deform_only=False, add_leaf_bones=False,
            bake_anim=False, apply_unit_scale=True, global_scale=1.0,
            apply_scale_options="FBX_SCALE_UNITS" if args.cm_native else "FBX_SCALE_NONE",
            axis_forward="-Z", axis_up="Y", mesh_smooth_type="FACE",
            use_tspace=True, use_custom_props=True, path_mode="COPY", embed_textures=False,
        )
        if args.cm_native:
            report['bind_precision'] = normalize_fbx_bind(raw_fbx, staged_fbx)
            unit_bones = {bone.name for bone in armature.data.bones if bone.parent is None}
            unit_bones.update(name for spec in plan.get("leg_cleanup", {}).values()
                              for name in spec.get("deform_chain", []))
            unit_facts = audit_fbx_units(
                staged_fbx, armature.name, [mesh.name for mesh in meshes],
                bone_scale_names=sorted(unit_bones),
            )
            assert_cm_native_contract(unit_facts)
            report["fbx_unit_audit"] = unit_facts
        staged_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if any(path.exists() for path in outputs):
            raise RuntimeError("output appeared during export; refusing to overwrite")
        for staged, destination in zip((staged_blend, staged_fbx, staged_report), outputs):
            staged.rename(destination)
    print("MMD2UE_SKELETON_APPLY " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
