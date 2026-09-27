"""Repair inherited D-leg pose offsets on a new MMD2UE v3 retargeter.

Run with the editor closed. PMX4UE_POSE_RELOAD=1 performs read-only reload QA.
No arm recomputation, no skeleton edits, no chain/root-motion changes.
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
    raise RuntimeError("Use MMD2UE")
base = "/Game/Characters/TololoSchool1001/Rigs/"
original = base + "TPose_v2/RTG_UEFN_To_Tololo_TPose_v2"
namespace = base + "TPose_v3"
destination = namespace + "/RTG_UEFN_To_Tololo_TPose_v3"
folder = project / "Saved/PMX4UE/RetargetTPose_v3"
report_path = folder / "normalize.json"


def fingerprint(path):
    file = project / "Content" / (path.split(".")[0].removeprefix("/Game/") + ".uasset")
    return hashlib.sha256(file.read_bytes()).hexdigest()


def config(asset):
    ctl = unreal.IKRetargeterController.get_controller(asset)
    rigs = {s: ctl.get_ik_rig(getattr(unreal.RetargetSourceOrTarget, s.upper())) for s in ("source", "target")}
    chains = unreal.IKRigController.get_controller(rigs["target"]).get_retarget_chains()
    return dict(rigs={s: r.get_path_name() for s, r in rigs.items()},
        mappings={str(c.chain_name): str(ctl.get_source_chain(c.chain_name)) for c in chains},
        ops=[dict(type=ctl.get_op_controller(i).get_class().get_name(), enabled=ctl.get_retarget_op_enabled(i))
             for i in range(ctl.get_num_retarget_ops())])


if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    report = json.loads(report_path.read_text(encoding="utf-8"))
    asset = unreal.load_asset(destination)
    errors = {s: verify(snapshot, inspect(asset, s)) for s, snapshot in report["after"].items()}
    assert config(asset) == report["configuration"]
    assert all(fingerprint(p) == h for p, h in report["original_hashes"].items())
    assert fingerprint(destination) == report["output_hash"]
    assert inspect(asset, "target")["pose"] == "TPose_Target_v3"
    assert inspect(asset, "source")["pose"] == report["before"]["source"]["pose"]
    (folder / "reload.json").write_text(json.dumps(dict(passed=True, errors=errors,
        original_assets_unchanged=True, configuration_unchanged=True,
        visual_review="pending", animation_review="pending"), indent=2), encoding="utf-8")
else:
    if report_path.exists() or unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise RuntimeError("Do not overwrite v3")
    asset = unreal.load_asset(original)
    before = {s: inspect(asset, s) for s in ("source", "target")}
    assert before["target"]["mesh"].split(".")[0] == "/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1"
    settings = config(asset)
    inputs = [original, *settings["rigs"].values()]
    for snapshot in before.values():
        inputs.extend([snapshot["mesh"], unreal.load_asset(snapshot["mesh"]).get_editor_property("skeleton").get_path_name()])
    hashes = {p: fingerprint(p) for p in inputs}
    restore = ["LegD_L", "KneeD_L", "LegD_R", "KneeD_R"]
    profile = dict(reviewed=True, retargeter=original, output_retargeter=destination, sides={
        "target": dict(pose_name="TPose_Target_v3", restore_reference_rotations=restore,
            posture_checks=[dict(start="Waist", end="Neck", up_axis=[0, 0, 1], max_tilt_degrees=2),
                *[dict(start="LegD_"+s, end="AnkleD_"+s, up_axis=[0, 0, -1], max_tilt_degrees=5) for s in ("L", "R")]])})
    report = build(profile, namespace, report_path)
    try:
        result = unreal.load_asset(destination)
        assert config(result) == settings
        assert all(fingerprint(p) == h for p, h in hashes.items())
        # No legitimate target changes outside the two D-leg subtrees.
        affected = set()
        for i, b in enumerate(before["target"]["bones"]):
            if b["name"] in restore or b["parent"] in affected:
                affected.add(i)
        keep = lambda snapshot: {"bones": [b for i, b in enumerate(snapshot["bones"]) if i not in affected]}
        report["unaffected_target_verification"] = verify(keep(before["target"]), keep(report["after"]["target"]))
        report["source_unchanged_verification"] = verify(before["source"], report["after"]["source"])
        assert inspect(result, "target")["pose"] == "TPose_Target_v3"
        report.update(configuration=settings, original_hashes=hashes, output_hash=fingerprint(destination),
            normalization_status="passed_native_checks_needs_visual_and_animation_review", animation_review="pending")
    except Exception:
        report["normalization_status"] = "failed_do_not_use"
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log("NORMALIZED_RETARGETER=" + destination)
