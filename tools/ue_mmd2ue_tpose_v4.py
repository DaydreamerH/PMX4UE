"""Match UEFN and Tololo standing leg directions on independent v4 poses.

Use MMD2UE with editor closed; PMX4UE_POSE_RELOAD=1 verifies saved results.
Reviewed basis: target v3 neutral legs, component +X left and +Z up on both.
Preserves actual proportions, upper body and component-space foot orientation.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_retarget_pose import build, inspect
from retarget_pose_math import verify, unit, sub, dot

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
if not (project / "MMD2UE.uproject").is_file():
    raise RuntimeError("Use MMD2UE")
base = "/Game/Characters/TololoSchool1001/Rigs/"
original = base + "TPose_v3/RTG_UEFN_To_Tololo_TPose_v3"
namespace = base + "TPose_v4"
destination = namespace + "/RTG_UEFN_To_Tololo_TPose_v4"
folder = project / "Saved/PMX4UE/RetargetTPose_v4"
report_path = folder / "normalize.json"
legs = dict(source=dict(left=["thigh_l", "calf_l", "foot_l"], right=["thigh_r", "calf_r", "foot_r"]),
    target=dict(left=["LegD_L", "KneeD_L", "AnkleD_L"], right=["LegD_R", "KneeD_R", "AnkleD_R"]))


def fingerprint(path):
    file = project / "Content" / (path.split(".")[0].removeprefix("/Game/") + ".uasset")
    return hashlib.sha256(file.read_bytes()).hexdigest()


def configuration(asset):
    ctl = unreal.IKRetargeterController.get_controller(asset)
    rigs = {s: ctl.get_ik_rig(getattr(unreal.RetargetSourceOrTarget, s.upper())) for s in legs}
    chains = unreal.IKRigController.get_controller(rigs["target"]).get_retarget_chains()
    return dict(rigs={s: r.get_path_name() for s, r in rigs.items()},
        mappings={str(c.chain_name): str(ctl.get_source_chain(c.chain_name)) for c in chains},
        ops=[dict(type=ctl.get_op_controller(i).get_class().get_name(), enabled=ctl.get_retarget_op_enabled(i))
             for i in range(ctl.get_num_retarget_ops())])


def selected(asset):
    return {s: inspect(asset, s)["pose"] for s in legs}


if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    report = json.loads(report_path.read_text(encoding="utf-8"))
    asset = unreal.load_asset(destination)
    errors = {s: verify(snapshot, inspect(asset, s)) for s, snapshot in report["after"].items()}
    assert configuration(asset) == report["configuration"]
    assert selected(asset) == {s: v["pose_name"] for s, v in report["profile"]["sides"].items()}
    assert all(fingerprint(p) == h for p, h in report["original_hashes"].items())
    assert fingerprint(destination) == report["output_hash"]
    (folder / "reload.json").write_text(json.dumps(dict(passed=True, errors=errors,
        original_assets_unchanged=True, configuration_unchanged=True,
        visual_review="pending", animation_review="pending"), indent=2), encoding="utf-8")
else:
    if report_path.exists() or unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise RuntimeError("Do not overwrite v4")
    asset = unreal.load_asset(original)
    before = {s: inspect(asset, s) for s in legs}
    expected_meshes = dict(source="/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin",
        target="/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1")
    assert all(before[s]["mesh"].split(".")[0] == p for s, p in expected_meshes.items())
    settings = configuration(asset)
    inputs = [original, *settings["rigs"].values()]
    for snapshot in before.values():
        inputs.extend([snapshot["mesh"], unreal.load_asset(snapshot["mesh"]).get_editor_property("skeleton").get_path_name()])
    hashes = {p: fingerprint(p) for p in inputs}
    target = {b["name"]: b for b in before["target"]["bones"]}
    goals = {s: [unit(sub(target[b]["global_position"], target[a]["global_position"])) for a, b in zip(c, c[1:])]
             for s, c in legs["target"].items()}
    checks = dict(source=[dict(start="pelvis", end="neck_01", up_axis=[0, 0, 1], max_tilt_degrees=5)],
                  target=[dict(start="Waist", end="Neck", up_axis=[0, 0, 1], max_tilt_degrees=2)])
    profile = dict(reviewed=True, retargeter=original, output_retargeter=destination, sides={s: dict(
        pose_name="TPose_"+s.title()+"_v4", leg_alignment=dict(legs=chains, directions=goals,
            left_axis=[1, 0, 0], up_axis=[0, 0, 1], max_foot_height_change_cm=1),
        posture_checks=checks[s]+[dict(start=c[0], end=c[2], up_axis=[0, 0, -1], max_tilt_degrees=5) for c in chains.values()]
        ) for s, chains in legs.items()})
    report = build(profile, namespace, report_path)
    try:
        result = unreal.load_asset(destination)
        assert configuration(result) == settings
        assert selected(result) == {s: v["pose_name"] for s, v in profile["sides"].items()}
        assert all(fingerprint(p) == h for p, h in hashes.items())
        upper_errors, foot_errors, matches = {}, {}, {}
        for s, chains in legs.items():
            affected = set()
            for i, b in enumerate(before[s]["bones"]):
                if b["name"] in [c[0] for c in chains.values()] or b["parent"] in affected:
                    affected.add(i)
            keep = lambda snapshot: {"bones": [b for i, b in enumerate(snapshot["bones"]) if i not in affected]}
            upper_errors[s] = verify(keep(before[s]), keep(report["after"][s]))
            old = {b["name"]: b for b in before[s]["bones"]}
            new = {b["name"]: b for b in report["after"][s]["bones"]}
            foot_errors[s] = {side: math.degrees(2*math.acos(min(1, abs(dot(unit(old[c[2]]["global_rotation"]),
                unit(new[c[2]]["global_rotation"])))))) for side, c in chains.items()}
            assert max(foot_errors[s].values()) < .05
            matches[s] = [segment["native_final_degrees"] for segment in report["plans"][s]["segments"]]
            assert max(matches[s]) < .05
        report.update(configuration=settings, original_hashes=hashes, output_hash=fingerprint(destination),
            upper_body_verification=upper_errors, foot_orientation_error_degrees=foot_errors,
            leg_direction_errors_degrees=matches, basis="target v3 component-space leg segment directions",
            normalization_status="passed_native_checks_needs_visual_and_animation_review", animation_review="pending")
    except Exception:
        report["normalization_status"] = "failed_do_not_use"
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log("NORMALIZED_RETARGETER=" + destination)
