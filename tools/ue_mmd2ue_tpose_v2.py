"""MMD2UE: restore reviewed torso offsets before solving T arms on a v2 copy.

Run only with the project editor closed. PMX4UE_POSE_RELOAD=1 verifies in a
fresh process. Existing mesh, skeleton, rigs, v1 retargeter and animations are
read-only. No root-motion/chain configuration changes belong to this experiment.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_retarget_pose import build, inspect
from retarget_pose_math import verify

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
if not (project / "MMD2UE.uproject").is_file():
    raise RuntimeError("Use the existing MMD2UE project")
namespace = "/Game/Characters/TololoSchool1001/Rigs/TPose_v2"
original = "/Game/Characters/TololoSchool1001/Rigs/TPose_v1/RTG_UEFN_To_Tololo_TPose_v1"
destination = namespace + "/RTG_UEFN_To_Tololo_TPose_v2"
folder = project / "Saved/PMX4UE/RetargetTPose_v2"
report_path = folder / "normalize.json"


def file_hash(asset_path):
    path = project / "Content" / (asset_path.split(".")[0].removeprefix("/Game/") + ".uasset")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_snapshot(asset):
    ctl = unreal.IKRetargeterController.get_controller(asset)
    rigs = {s: ctl.get_ik_rig(getattr(unreal.RetargetSourceOrTarget, s.upper())) for s in ("source", "target")}
    chains = unreal.IKRigController.get_controller(rigs["target"]).get_retarget_chains()
    return dict(rigs={s: r.get_path_name() for s, r in rigs.items()},
                chain_mappings={str(c.chain_name): str(ctl.get_source_chain(c.chain_name)) for c in chains},
                operations=[dict(type=ctl.get_op_controller(i).get_class().get_name(),
                                 enabled=ctl.get_retarget_op_enabled(i)) for i in range(ctl.get_num_retarget_ops())])


def assert_selected(asset, report):
    ctl = unreal.IKRetargeterController.get_controller(asset)
    for side, spec in report["profile"]["sides"].items():
        assert str(ctl.get_current_retarget_pose_name(getattr(unreal.RetargetSourceOrTarget, side.upper()))) == spec["pose_name"]


if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    report = json.loads(report_path.read_text(encoding="utf-8"))
    asset = unreal.load_asset(destination)
    assert_selected(asset, report)
    errors = {s: verify(expected, inspect(asset, s)) for s, expected in report["after"].items()}
    assert config_snapshot(asset) == report["configuration"]
    assert all(file_hash(p) == h for p, h in report["original_hashes"].items())
    assert file_hash(destination) == report["output_hash"]
    (folder / "reload.json").write_text(json.dumps(dict(passed=True, errors=errors,
        original_assets_unchanged=True, configuration_unchanged=True, poses_selected=True,
        visual_review="pending", animation_review="pending"), indent=2), encoding="utf-8")
else:
    if report_path.exists() or unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise RuntimeError("Output exists: never overwrite v2")
    asset = unreal.load_asset(original)
    before = {s: inspect(asset, s) for s in ("source", "target")}
    expected_meshes = dict(source="/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin",
        target="/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1")
    assert all(before[s]["mesh"].split(".")[0] == p for s, p in expected_meshes.items())
    configuration = config_snapshot(asset)
    paths = [original, *configuration["rigs"].values(), *expected_meshes.values()]
    for mesh_path in expected_meshes.values():
        paths.append(unreal.load_asset(mesh_path).get_editor_property("skeleton").get_path_name())
    hashes = {p: file_hash(p) for p in paths}
    profile = dict(reviewed=True, retargeter=original, output_retargeter=destination, sides={
        "source": dict(pose_name="TPose_Source_v2", auto_arms=True, up_axis=[0, 0, 1],
            arms=dict(left=["upperarm_l", "lowerarm_l", "hand_l"], right=["upperarm_r", "lowerarm_r", "hand_r"]),
            posture_checks=[dict(start="pelvis", end="neck_01", up_axis=[0, 0, 1], max_tilt_degrees=5)]),
        "target": dict(pose_name="TPose_Target_v2", auto_arms=True, up_axis=[0, 0, 1],
            restore_reference_rotations=["Center", "Groove", "Waist", "UpperBody"],
            arms=dict(left=["Arm_L", "Elbow_L", "Wrist_L"], right=["Arm_R", "Elbow_R", "Wrist_R"]),
            posture_checks=[dict(start="Waist", end="Neck", up_axis=[0, 0, 1], max_tilt_degrees=2)])})
    report = build(profile, namespace, report_path)
    result = unreal.load_asset(destination)
    try:
        assert_selected(result, report)
        assert config_snapshot(result) == configuration
        assert all(file_hash(p) == h for p, h in hashes.items())
        for planned in report["plans"].values():
            assert all(s["native_final_degrees"] < 0.05 for s in planned["segments"])
        # Source pose was already accepted numerically; v2 must not change it.
        report["source_unchanged_verification"] = verify(before["source"], report["after"]["source"])
        report.update(original_hashes=hashes, configuration=configuration, output_hash=file_hash(destination),
            normalization_status="passed_native_checks_needs_visual_and_animation_review",
            animation_review="pending", torso_policy="restore_explicit_reference_offsets_before_arm_solve")
    except Exception:
        report["normalization_status"] = "failed_do_not_use"
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log("NORMALIZED_RETARGETER=" + destination)
