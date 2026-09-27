"""Read existing retargeters in the active MMD2UE project; do not save assets."""
import json
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
if not (project / "MMD2UE.uproject").is_file():
    raise RuntimeError("This inventory is for MMD2UE, not a new host project")
registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.search_all_assets(True)
rows = []
for data in registry.get_assets_by_path("/Game/Characters/TololoSchool1001", True):
    if str(data.asset_class_path.asset_name) != "IKRetargeter":
        continue
    asset = data.get_asset()
    ctl = unreal.IKRetargeterController.get_controller(asset)
    row = dict(asset=asset.get_path_name(), sides={})
    for side in ("source", "target"):
        enum = getattr(unreal.RetargetSourceOrTarget, side.upper())
        rig = ctl.get_ik_rig(enum)
        mesh = ctl.get_preview_mesh(enum)
        info = dict(rig=rig.get_path_name() if rig else None, mesh=mesh.get_path_name() if mesh else None,
                    pose=str(ctl.get_current_retarget_pose_name(enum)))
        if rig:
            rc = unreal.IKRigController.get_controller(rig)
            info["pelvis"] = str(rc.get_retarget_root())
            info["chains"] = {str(c.chain_name): [str(rc.get_retarget_chain_start_bone(c.chain_name)),
                                                   str(rc.get_retarget_chain_end_bone(c.chain_name))]
                              for c in rc.get_retarget_chains()}
        row["sides"][side] = info
    row["ops"] = [dict(type=ctl.get_op_controller(i).get_class().get_name(), enabled=ctl.get_retarget_op_enabled(i))
                  for i in range(ctl.get_num_retarget_ops())]
    rows.append(row)
output = project / "Saved/PMX4UE/RetargetTPose/inventory.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
unreal.log("POSE_INVENTORY=" + str(output))
