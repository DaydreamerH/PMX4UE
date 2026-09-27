"""Normalize actual UEFN -> Tololo retargeting in MMD2UE, on new assets only.

Run with UnrealEditor-Cmd MMD2UE.uproject -run=pythonscript -script=<this file>.
PMX4UE_POSE_RELOAD=1 verifies saved results in a fresh process instead of building.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_retarget_pose import build, inspect
from retarget_pose_math import plan, verify

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
if not (project / "MMD2UE.uproject").is_file():
    raise RuntimeError("Use the existing MMD2UE project")
namespace = "/Game/Characters/TololoSchool1001/Rigs/TPose_v1"
folder = project / "Saved/PMX4UE/RetargetTPose"
original_path = "/Game/Characters/TololoSchool1001/PhysicsSandbox/IK_Tololo_Mann"
dest = namespace + "/RTG_UEFN_To_Tololo_TPose_v1"
report_file = folder / "normalize.json"


def save(asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
        raise RuntimeError("Could not save " + asset.get_path_name())


def file_hash(asset_path):
    path = project / "Content" / (asset_path.split(".")[0].removeprefix("/Game/") + ".uasset")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def operations(ctl):
    return [(ctl.get_op_controller(i).get_class().get_name(), ctl.get_retarget_op_enabled(i))
            for i in range(ctl.get_num_retarget_ops())]


def mappings(ctl, rig):
    rc = unreal.IKRigController.get_controller(rig)
    return {str(c.chain_name): str(ctl.get_source_chain(c.chain_name)) for c in rc.get_retarget_chains()}


if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    report = json.loads(report_file.read_text(encoding="utf-8"))
    asset = unreal.load_asset(dest)
    ctl = unreal.IKRetargeterController.get_controller(asset)
    errors = {side: verify(snapshot, inspect(asset, side)) for side, snapshot in report["after"].items()}
    for side in ("source", "target"):
        assert str(ctl.get_current_retarget_pose_name(getattr(unreal.RetargetSourceOrTarget, side.upper()))) == report["profile"]["sides"][side]["pose_name"]
    for path, expected in report["original_hashes"].items():
        assert file_hash(path) == expected, path
    assert mappings(ctl, ctl.get_ik_rig(unreal.RetargetSourceOrTarget.TARGET)) == report["chain_mappings"]
    assert [list(x) for x in operations(ctl)] == report["operations"]
    for name, rig_path in report.get("op_rig_verification", {}).get("result", {}).get("op_rigs", {}).items():
        assert ctl.get_target_ik_rig_for_op(name).get_path_name() == rig_path
    (folder / "reload.json").write_text(json.dumps(dict(passed=True, asset=dest, errors=errors,
        source_and_target_selected=True, original_files_unchanged=True, mappings_reloaded=True), indent=2), encoding="utf-8")
else:
    paths = dict(source=namespace + "/IK_UEFN_TPose_v1", target=namespace + "/IK_Tololo_UpperOnly_TPose_v1",
                 basis=namespace + "/RTG_UEFN_To_Tololo_Basis_v1", result=dest)
    if report_file.exists() or any(unreal.EditorAssetLibrary.does_asset_exist(x) for x in paths.values()):
        raise RuntimeError("Output exists: do not overwrite normalized assets")
    original = unreal.load_asset(original_path)
    ctl = unreal.IKRetargeterController.get_controller(original)
    before = {side: inspect(original, side) for side in ("source", "target")}
    assert before["source"]["mesh"].split(".")[0] == "/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin"
    assert before["target"]["mesh"].split(".")[0] == "/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1"
    rigs = {side: ctl.get_ik_rig(getattr(unreal.RetargetSourceOrTarget, side.upper())) for side in before}
    original_mappings = mappings(ctl, rigs["target"])
    original_ops = operations(ctl)
    originals = [original_path, *[r.get_path_name() for r in rigs.values()], *[s["mesh"] for s in before.values()]]
    hashes = {path: file_hash(path) for path in originals}
    profile = dict(reviewed=True, retargeter=paths["basis"], output_retargeter=dest, sides={
        "source": dict(pose_name="TPose_Source_v1", auto_arms=True, up_axis=[0, 0, 1],
                       arms=dict(left=["upperarm_l", "lowerarm_l", "hand_l"], right=["upperarm_r", "lowerarm_r", "hand_r"])),
        "target": dict(pose_name="TPose_Target_v1", auto_arms=True, up_axis=[0, 0, 1],
                       arms=dict(left=["Arm_L", "Elbow_L", "Wrist_L"], right=["Arm_R", "Elbow_R", "Wrist_R"]))})
    # Validate the numerical plan and all chain endpoints before creating anything.
    for side in before:
        plan(before[side], profile["sides"][side])
    target_bones = {b["name"]: b for b in before["target"]["bones"]}
    additions = dict(LeftArm=["Arm_L", "Wrist_L"], RightArm=["Arm_R", "Wrist_R"],
                     LeftClavicle=["Shoulder_L", "Shoulder_L"], RightClavicle=["Shoulder_R", "Shoulder_R"],
                     Neck=["Neck", "Neck"], Head=["Head", "Head"])
    src_ctl = unreal.IKRigController.get_controller(rigs["source"])
    src_names = {str(c.chain_name) for c in src_ctl.get_retarget_chains()}
    for name, (start, end) in additions.items():
        if name not in src_names or start not in target_bones or end not in target_bones:
            raise RuntimeError("Review missing chain/bone: " + name)
        index = target_bones[end]["parent"]
        if start != end:
            while index >= 0 and before["target"]["bones"][index]["name"] != start:
                index = before["target"]["bones"][index]["parent"]
            if index < 0:
                raise RuntimeError("Chain endpoints do not form a parent-child path: " + name)
    copies = {side: unreal.EditorAssetLibrary.duplicate_asset(rigs[side].get_path_name(), paths[side]) for side in rigs}
    if not all(copies.values()):
        raise RuntimeError("Rig duplication failed")
    target_ctl = unreal.IKRigController.get_controller(copies["target"])
    existing = {str(c.chain_name) for c in target_ctl.get_retarget_chains()}
    for name, (start, end) in additions.items():
        if name not in existing:
            target_ctl.add_retarget_chain(name, start, end, "")
        if str(target_ctl.get_retarget_chain_start_bone(name)) != start or str(target_ctl.get_retarget_chain_end_bone(name)) != end:
            raise RuntimeError("Conflicting existing chain: " + name)
    for rig in copies.values():
        save(rig)
    basis = unreal.EditorAssetLibrary.duplicate_asset(original_path, paths["basis"])
    bc = unreal.IKRetargeterController.get_controller(basis)
    for side, rig in copies.items():
        bc.set_ik_rig(getattr(unreal.RetargetSourceOrTarget, side.upper()), rig)
        # UE intentionally does NOT propagate Target Rig changes to Op overrides.
        bc.assign_ik_rig_to_all_ops(getattr(unreal.RetargetSourceOrTarget, side.upper()), rig)
    for name in additions:
        bc.set_source_chain(name, name)
    for name, source in original_mappings.items():
        bc.set_source_chain(source, name)
    assert operations(bc) == original_ops
    save(basis)
    folder.mkdir(parents=True, exist_ok=True)
    report = build(profile, namespace, report_file)
    final = unreal.load_asset(dest)
    fc = unreal.IKRetargeterController.get_controller(final)
    report.update(original_hashes=hashes, chain_mappings=mappings(fc, copies["target"]),
                  operations=operations(fc), added_target_chains=list(additions), assets=paths)
    # Persist verification evidence even if a subsequent assertion fails.
    report["normalization_status"] = "pending_chain_verification"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(file_hash(path) == value for path, value in hashes.items())
    assert all(report["chain_mappings"][name] == name for name in additions)
    assert all(report["chain_mappings"][name] == value for name, value in original_mappings.items())
    assert operations(fc) == original_ops
    report["normalization_status"] = "passed_needs_animation_visual_review"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log("NORMALIZED_RETARGETER=" + dest)
