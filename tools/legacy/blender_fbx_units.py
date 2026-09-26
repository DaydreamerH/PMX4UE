"""Explicit FBX unit contracts for Blender-side character exports."""

from __future__ import annotations

from io_scene_fbx import parse_fbx
from mathutils import Matrix
from math import sqrt


def prepare_cm_native_scene(armature, meshes):
    """Bake meter coordinates into centimeter-valued data, without object scale."""
    if any(abs(component - 1.0) > 1e-5 for component in armature.scale):
        raise RuntimeError("armature object scale is not identity")
    for mesh in meshes:
        if any(abs(component - 1.0) > 1e-5 for component in mesh.scale):
            raise RuntimeError(f"{mesh.name}: mesh object scale is not identity")
        if any(abs(component - 1.0) > 1e-5 for component in mesh.matrix_parent_inverse.to_scale()):
            raise RuntimeError(f"{mesh.name}: mesh parent inverse scale is not identity")
    for mesh in meshes:
        mesh.data.transform(Matrix.Scale(100.0, 4), shape_keys=True)
    armature.data.transform(Matrix.Scale(100.0, 4))
    # MMD constraints can leave evaluated pose matrices at the *old* meter
    # coordinates after the rest data changes. FBX uses the evaluated pose for
    # bind data, so force the in-memory export to the new rest pose.
    armature.data.pose_position = "REST"
    import bpy
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.01
    bpy.context.view_layer.update()
    for bone in armature.data.bones:
        pose = armature.pose.bones.get(bone.name)
        if pose is None or (pose.matrix.translation - bone.matrix_local.translation).length > 0.001:
            raise RuntimeError(f"evaluated/rest bone mismatch after centimeter bake: {bone.name}")


def audit_fbx_units(path, armature_name, mesh_names, expected_bone_lengths=None, bone_scale_names=()):
    root, _ = parse_fbx.parse(str(path))
    global_settings = next(elem for elem in root.elems if elem.id == b"GlobalSettings")
    settings = next(elem for elem in global_settings.elems if elem.id == b"Properties70")
    unit = next(prop.props[-1] for prop in settings.elems
                if prop.props[0] == b"UnitScaleFactor")
    objects = next(elem for elem in root.elems if elem.id == b"Objects")
    scales = {}
    for name in (armature_name, *mesh_names, *bone_scale_names):
        model = next(elem for elem in objects.elems if elem.id == b"Model"
                     and elem.props[1].split(bytes([0]))[0].decode("utf-8") == name)
        values = [prop.props[4:] for group in model.elems if group.id == b"Properties70"
                  for prop in group.elems if prop.props[0] == b"Lcl Scaling"]
        scales[name] = values[0] if values else [1.0, 1.0, 1.0]
    bone_lengths = {}
    for name in (expected_bone_lengths or {}):
        model = next(elem for elem in objects.elems if elem.id == b"Model"
                     and elem.props[1].split(bytes([0]))[0].decode("utf-8") == name)
        values = [prop.props[4:] for group in model.elems if group.id == b"Properties70"
                  for prop in group.elems if prop.props[0] == b"Lcl Translation"]
        if not values:
            raise RuntimeError(f"FBX bone has no local translation: {name}")
        bone_lengths[name] = sqrt(sum(float(component) ** 2 for component in values[0]))
    return {"fbx_unit_scale_factor": unit, "fbx_object_scales": scales,
            "expected_bone_lengths_cm": expected_bone_lengths or {},
            "fbx_bone_lengths_cm": bone_lengths}


def assert_cm_native_contract(facts):
    if abs(facts["fbx_unit_scale_factor"] - 1.0) > 1e-5 or any(
        abs(component - 1.0) > 1e-5 for values in facts["fbx_object_scales"].values()
        for component in values
    ):
        raise RuntimeError(f"centimeter-native FBX contract failed: {facts}")
    for name, expected in facts["expected_bone_lengths_cm"].items():
        actual = facts["fbx_bone_lengths_cm"][name]
        if abs(actual - expected) > max(0.05, 0.01 * expected):
            raise RuntimeError(f"FBX bone length has stale unit scale: {name}: "
                               f"expected {expected:.4f} cm, got {actual:.4f} cm")
