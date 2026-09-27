"""Finish the owned TPose_v1 experiment after detecting stale per-Op Rig refs.

Does not repair/overwrite user originals. Kept as the experiment's recovery record.
"""
import hashlib
import json
from pathlib import Path
import sys
import unreal
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_retarget_pose import inspect
from retarget_pose_math import verify

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
folder = project / "Saved/PMX4UE/RetargetTPose"
report_path = folder / "normalize.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
namespace = "/Game/Characters/TololoSchool1001/Rigs/TPose_v1"
paths = dict(source=namespace + "/IK_UEFN_TPose_v1", target=namespace + "/IK_Tololo_UpperOnly_TPose_v1",
             basis=namespace + "/RTG_UEFN_To_Tololo_Basis_v1", result=namespace + "/RTG_UEFN_To_Tololo_TPose_v1")
assert report["profile"]["output_retargeter"] == paths["result"]
original = unreal.load_asset("/Game/Characters/TololoSchool1001/PhysicsSandbox/IK_Tololo_Mann")
oc = unreal.IKRetargeterController.get_controller(original)
for side, before in report["before"].items():
    assert inspect(original, side) == before
originals = [original.get_path_name(), *[b["mesh"] for b in report["before"].values()],
             *[oc.get_ik_rig(s).get_path_name() for s in (unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET)]]

def sha(path):
    return hashlib.sha256((project / "Content" / (path.split(".")[0].removeprefix("/Game/") + ".uasset")).read_bytes()).hexdigest()

hashes = {p: sha(p) for p in originals}
rigs = {side: unreal.load_asset(paths[side]) for side in ("source", "target")}
rc = unreal.IKRigController.get_controller(rigs["target"])
added = ["LeftArm", "RightArm", "LeftClavicle", "RightClavicle", "Neck", "Head"]
chain_names = [str(c.chain_name) for c in rc.get_retarget_chains()]
old_map = {n: str(oc.get_source_chain(n)) for n in chain_names if n not in added}
records = {}
for key in ("basis", "result"):
    asset = unreal.load_asset(paths[key])
    ctl = unreal.IKRetargeterController.get_controller(asset)
    before = {s: inspect(asset, s) for s in rigs}
    for side, rig in rigs.items():
        assert ctl.get_ik_rig(getattr(unreal.RetargetSourceOrTarget, side.upper())) == rig
        ctl.assign_ik_rig_to_all_ops(getattr(unreal.RetargetSourceOrTarget, side.upper()), rig)
    for name in chain_names:
        if not ctl.set_source_chain(name if name in added else old_map[name], name):
            raise RuntimeError("Cannot set chain mapping: " + name)
    actual_map = {n: str(ctl.get_source_chain(n)) for n in chain_names}
    assert all(actual_map[n] == n for n in added)
    assert all(actual_map[n] == value for n, value in old_map.items())
    for side, snapshot in before.items():
        verify(snapshot, inspect(asset, side))
    ops = [(ctl.get_op_controller(i).get_class().get_name(), ctl.get_retarget_op_enabled(i)) for i in range(ctl.get_num_retarget_ops())]
    assert ops == [(oc.get_op_controller(i).get_class().get_name(), oc.get_retarget_op_enabled(i)) for i in range(oc.get_num_retarget_ops())]
    op_rigs = {}
    for i in range(ctl.get_num_retarget_ops()):
        op_name = ctl.get_op_name(i)
        rig = ctl.get_target_ik_rig_for_op(op_name)
        if rig:
            assert rig == rigs["target"]
            op_rigs[str(op_name)] = rig.get_path_name()
    asset.modify()
    assert unreal.EditorAssetLibrary.save_loaded_asset(asset, False)
    records[key] = dict(mappings=actual_map, operations=ops, op_rigs=op_rigs)
assert all(sha(p) == h for p, h in hashes.items())
report.update(normalization_status="passed_needs_animation_visual_review", original_hashes=hashes,
              chain_mappings=records["result"]["mappings"], operations=records["result"]["operations"],
              added_target_chains=added, assets=paths, op_rig_verification=records,
              recovered_failure="SetIKRig does not propagate target rig to Ops; assign_ik_rig_to_all_ops now applied")
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
