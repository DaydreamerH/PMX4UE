"""Reviewed IK Rig + optional retargeter; no fixed character/source content paths."""
import json
import os
from pathlib import Path
import unreal
from ue_bridge import resolve


def bone_names(mesh):
    report = json.loads(resolve("physics").inspect_physics_mesh(mesh.get_path_name()))
    if report.get("status") != "inspected":
        raise RuntimeError(report)
    return {row["name"] for row in report["bones"]}


def chain_path(mesh, start, end):
    names = bone_names(mesh)
    if start not in names or end not in names:
        raise RuntimeError(f"Missing chain endpoint: {start}, {end}")
    path, current = [], end
    while current not in path:
        path.append(current)
        if current == start:
            return list(reversed(path))
        current = str(mesh.get_bone_parent(current))
        if current not in names:
            break
    raise RuntimeError(f"Invalid chain: {start} is not ancestor of {end}")


def new_asset(path, cls, factory):
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError(f"Asset exists; choose new rig variant: {path}")
    folder, name = path.rsplit("/", 1)
    result = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if not result:
        raise RuntimeError("Creation failed: " + path)
    return result


def validate_rig(spec):
    mesh = unreal.load_asset(spec["mesh"])
    if not isinstance(mesh, unreal.SkeletalMesh):
        raise RuntimeError("Missing skeletal mesh: " + spec["mesh"])
    names = bone_names(mesh)
    if spec["pelvis"] not in names or not spec["chains"]:
        raise RuntimeError("Review pelvis and chains using imported UE hierarchy")
    for start, end in spec["chains"].values():
        chain_path(mesh, start, end)
    return mesh


def build_rig(spec, mesh):
    rig = new_asset(spec["asset"], unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    controller.set_skeletal_mesh(mesh)
    controller.set_retarget_root(spec["pelvis"])
    if str(controller.get_retarget_root()) != spec["pelvis"]:
        raise RuntimeError("Pelvis assignment failed")
    for name, (start, end) in spec["chains"].items():
        controller.add_retarget_chain(name, start, end, "")
        if str(controller.get_retarget_chain_start_bone(name)) != start or str(controller.get_retarget_chain_end_bone(name)) != end:
            raise RuntimeError("Chain assignment failed: " + name)
    if not unreal.EditorAssetLibrary.save_loaded_asset(rig, False):
        raise RuntimeError("Rig save failed")
    return rig


def main():
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8"))
    profile = json.loads(Path(os.environ["PMX4UE_RIG_PROFILE"]).read_text(encoding="utf-8"))
    if profile.get("reviewed") is not True:
        raise RuntimeError("Rig profile requires hierarchy/root/chain review")
    target, source = profile["target"], profile.get("source")
    specs = [target] + ([source] if source else [])
    paths = [s["asset"] for s in specs] + ([profile["retargeter"]] if source else [])
    namespace = config["paths"]["ue_root"] + "/"
    if len(paths) != len(set(paths)) or any(not x.startswith(namespace) for x in paths):
        raise RuntimeError("New rigs/retargeter must use this variant namespace")
    if any(unreal.EditorAssetLibrary.does_asset_exist(x) for x in paths):
        raise RuntimeError("Destination exists; no partial overwrite")
    meshes = [validate_rig(s) for s in specs]
    if source and set(target["chains"]) - set(source["chains"]):
        raise RuntimeError("Explicitly align semantic chain names on both rigs")
    rigs = [build_rig(s, m) for s, m in zip(specs, meshes)]
    if source:
        retarget = new_asset(profile["retargeter"], unreal.IKRetargeter, unreal.IKRetargetFactory())
        controller = unreal.IKRetargeterController.get_controller(retarget)
        controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, rigs[1])
        controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, rigs[0])
        controller.add_default_ops()
        controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
        for name in target["chains"]:
            controller.set_source_chain(name, name)
            if str(controller.get_source_chain(name)) != name:
                raise RuntimeError("Retarget chain mapping failed: " + name)
        if not unreal.EditorAssetLibrary.save_loaded_asset(retarget, False):
            raise RuntimeError("Retargeter save failed")
    Path(os.environ["PMX4UE_OUTPUT"]).write_text(json.dumps({
        "status": "configured_needs_pose_and_animation_review", "assets": paths,
        "animation_exported": False, "profile": profile}, ensure_ascii=False, indent=2), encoding="utf-8")


main()
