"""Isolated Spine-chain experiment, preserving v4 poses and original assets.

Run in MMD2UE with editor closed. PMX4UE_POSE_RELOAD=1 verifies persistence.
This does not evaluate animation and does not repair inherited root-motion settings.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_retarget_pose import inspect
from retarget_pose_math import verify

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
if not (project / "MMD2UE.uproject").is_file():
    raise RuntimeError("Use MMD2UE")
base = "/Game/Characters/TololoSchool1001/Rigs/"
original = base + "TPose_v4/RTG_UEFN_To_Tololo_TPose_v4"
destination = base + "TPose_v5/RTG_UEFN_To_Tololo_TPose_v5"
rig_destination = base + "TPose_v5/IK_Tololo_UpperOnly_Spine_v5"
folder = project / "Saved/PMX4UE/RetargetTPose_v5"
report_path = folder / "spine.json"
target_side = unreal.RetargetSourceOrTarget.TARGET


def fingerprint(path):
    file = project / "Content" / (path.split(".")[0].removeprefix("/Game/") + ".uasset")
    return hashlib.sha256(file.read_bytes()).hexdigest()


def configuration(asset):
    ctl = unreal.IKRetargeterController.get_controller(asset)
    sides = {}
    for side in ("source", "target"):
        enum = getattr(unreal.RetargetSourceOrTarget, side.upper())
        rig = ctl.get_ik_rig(enum)
        rc = unreal.IKRigController.get_controller(rig)
        sides[side] = dict(rig=rig.get_path_name(), pelvis=str(rc.get_retarget_root()),
            mesh=ctl.get_preview_mesh(enum).get_path_name(),
            pose=str(ctl.get_current_retarget_pose_name(enum)),
            chains={str(c.chain_name): [str(rc.get_retarget_chain_start_bone(c.chain_name)),
                str(rc.get_retarget_chain_end_bone(c.chain_name))] for c in rc.get_retarget_chains()})
    ops = []
    for i in range(ctl.get_num_retarget_ops()):
        name = ctl.get_op_name(i)
        rig = ctl.get_target_ik_rig_for_op(name)
        ops.append(dict(name=str(name), type=ctl.get_op_controller(i).get_class().get_name(),
            enabled=ctl.get_retarget_op_enabled(i), target_rig=rig.get_path_name() if rig else None))
    return dict(sides=sides, ops=ops,
        mappings={name: str(ctl.get_source_chain(name)) for name in sides["target"]["chains"]})


def snapshots(asset):
    return {side: inspect(asset, side) for side in ("source", "target")}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed_static_checks_needs_animation_review"
    result = unreal.load_asset(destination)
    assert configuration(result) == report["after_configuration"]
    errors = {side: verify(before, inspect(result, side)) for side, before in report["before_poses"].items()}
    assert all(fingerprint(p) == h for p, h in report["original_hashes"].items())
    assert all(fingerprint(p) == h for p, h in report["output_hashes"].items())
    write(folder / "reload.json", dict(passed=True, pose_errors=errors,
        original_assets_unchanged=True, configuration_persisted=True, animation_review="pending"))
else:
    if report_path.exists() or any(unreal.EditorAssetLibrary.does_asset_exist(p)
                                  for p in (destination, rig_destination)):
        raise RuntimeError("Do not overwrite existing v5 outputs")
    asset = unreal.load_asset(original)
    before = configuration(asset)
    poses = snapshots(asset)
    assert before["sides"]["target"]["chains"]["Spine"] == ["Groove", "UpperBody2"]
    assert before["sides"]["target"]["pelvis"] == "Center"
    inputs = [original]
    for side in before["sides"].values():
        inputs.extend([side["rig"], side["mesh"],
            unreal.load_asset(side["mesh"]).get_editor_property("skeleton").get_path_name()])
    report = dict(status="failed_do_not_use", before_configuration=before, before_poses=poses,
        original_hashes={p: fingerprint(p) for p in inputs}, animation_review="pending",
        known_issue="Inherited root-motion configuration intentionally unchanged")
    try:
        rig = unreal.EditorAssetLibrary.duplicate_asset(before["sides"]["target"]["rig"], rig_destination)
        assert rig
        rc = unreal.IKRigController.get_controller(rig)
        assert rc.set_retarget_chain_start_bone("Spine", "UpperBody")
        assert unreal.EditorAssetLibrary.save_loaded_asset(rig, False)
        result = unreal.EditorAssetLibrary.duplicate_asset(original, destination)
        assert result
        ctl = unreal.IKRetargeterController.get_controller(result)
        ctl.set_ik_rig(target_side, rig)
        ctl.assign_ik_rig_to_all_ops(target_side, rig)
        for target, source in before["mappings"].items():
            ctl.set_source_chain(source, target)
        after = configuration(result)
        expected = json.loads(json.dumps(before))
        expected["sides"]["target"]["rig"] = rig.get_path_name()
        expected["sides"]["target"]["chains"]["Spine"][0] = "UpperBody"
        for op in expected["ops"]:
            if op["target_rig"]:
                op["target_rig"] = rig.get_path_name()
        assert after == expected, (after, expected)
        report["pose_errors"] = {side: verify(pose, inspect(result, side)) for side, pose in poses.items()}
        assert unreal.EditorAssetLibrary.save_loaded_asset(result, False)
        assert all(fingerprint(p) == h for p, h in report["original_hashes"].items())
        report.update(after_configuration=after,
            output_hashes={p: fingerprint(p) for p in (destination, rig_destination)},
            status="passed_static_checks_needs_animation_review")
    finally:
        write(report_path, report)
    unreal.log("SPINE_V5_RETARGETER=" + destination)
