"""Read-only inventory of the actual source/target retargeter; no asset writes."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def collect(asset):
    import unreal
    from ue_retarget_pose import inspect
    from retarget_workflow import asset_path
    ctl = unreal.IKRetargeterController.get_controller(asset)
    sides = {}
    for side in ("source", "target"):
        enum = getattr(unreal.RetargetSourceOrTarget, side.upper())
        rig = ctl.get_ik_rig(enum)
        if not rig:
            raise ValueError("Missing actual " + side + " IK Rig")
        rc = unreal.IKRigController.get_controller(rig)
        chains = {str(c.chain_name): [str(rc.get_retarget_chain_start_bone(c.chain_name)),
                                     str(rc.get_retarget_chain_end_bone(c.chain_name))]
                  for c in rc.get_retarget_chains()}
        sides[side] = dict(rig=rig.get_path_name(), pelvis=str(rc.get_retarget_root()),
                           chains=chains, snapshot=inspect(asset, side))
    return dict(schema="pmx4ue.pose-inventory.v1", retargeter=asset_path(asset.get_path_name()), sides=sides,
        mappings={name: str(ctl.get_source_chain(name)) for name in sides["target"]["chains"]},
        ops=[dict(type=ctl.get_op_controller(i).get_class().get_name(), enabled=ctl.get_retarget_op_enabled(i))
             for i in range(ctl.get_num_retarget_ops())])


def export(retargeter, output):
    import unreal
    path = Path(output)
    if path.exists():
        raise ValueError("Inventory exists; choose a new file")
    asset = unreal.load_asset(retargeter)
    if not isinstance(asset, unreal.IKRetargeter):
        raise ValueError("Expected an existing IK Retargeter")
    data = collect(asset)
    from retarget_workflow import validate_inventory
    validate_inventory(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return data


if __name__ == "__main__":
    export(os.environ["PMX4UE_RETARGETER"], os.environ["PMX4UE_OUTPUT"])
