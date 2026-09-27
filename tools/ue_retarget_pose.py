"""Edit native UE Retarget Poses on an independent retargeter copy, never a mesh.

Can be called by pmx4ue.py or from UE Python:
    build(profile_dict, '/Game/PMX4UE/Character/v1', report_path)
"""
import json
import os
from pathlib import Path
import re
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retarget_pose_math import plan, verify, angle, sub, posture_metrics, stance_metrics


def inspect(asset, side):
    bridge = getattr(unreal, "MMD2UERetargetTools", None) or getattr(unreal, "PMX4UERetargetTools", None)
    if bridge is None:
        raise RuntimeError("Missing retarget pose inspection bridge in the current project")
    data = json.loads(bridge.inspect_retarget_pose(asset.get_path_name(), side == "source"))
    if data.get("status") != "inspected":
        raise RuntimeError(data)
    return data


def build(profile, namespace, output):
    if profile.get("reviewed") is not True:
        raise ValueError("Review bone landmarks and component-space up axis first")
    source_path, destination = profile["retargeter"], profile["output_retargeter"]
    if not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", destination) or not destination.startswith(namespace.rstrip("/") + "/"):
        raise ValueError("New retargeter must use the work order namespace")
    if unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise ValueError("Destination exists: no overwrite; choose a new pose variant")
    if Path(output).exists():
        raise ValueError("Report exists: choose a new report")
    asset = unreal.load_asset(source_path)
    if not isinstance(asset, unreal.IKRetargeter):
        raise ValueError("Input must be an IK Retargeter")
    agent_plan = None
    if "agent_contract" in profile:
        from ue_pose_inventory import collect
        from retarget_workflow import compile_pair, fingerprint
        contract = profile["agent_contract"]
        if contract.get("schema") != "pmx4ue.pose-contract.v1":
            raise ValueError("Unknown agent pose contract")
        agent_plan = compile_pair(collect(asset), contract["models"], contract["pair"])
        if fingerprint(agent_plan["profile"]) != fingerprint(profile):
            raise ValueError("Executable profile differs from reviewed plan; regenerate offline")
        if namespace.rstrip("/") != contract["pair"]["namespace"].rstrip("/"):
            raise ValueError("Work order namespace differs from reviewed pair")
    sides = profile["sides"]
    if not sides or set(sides) - {"source", "target"}:
        raise ValueError("Sides must contain source, target or both")
    controller = unreal.IKRetargeterController.get_controller(asset)
    before = {side: inspect(asset, side) for side in ("source", "target")}
    plans = {}
    for side, spec in sides.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", spec["pose_name"]):
            raise ValueError("Use a simple new pose_name")
        enum = getattr(unreal.RetargetSourceOrTarget, side.upper())
        if spec["pose_name"].casefold() in {str(n).casefold() for n in controller.get_retarget_poses(enum)}:
            raise ValueError("Pose name exists; use a new name")
        plans[side] = plan(before[side], spec)
    report = dict(status="planned", profile=profile, before=before, plans=plans,
                  modified_mesh=False, modified_skeleton=False, visual_review="pending", process_id=os.getpid())
    if agent_plan:
        report["acceptance"] = agent_plan["acceptance"]
        report["warnings"] = agent_plan["warnings"]
    result = None
    try:
        result = unreal.EditorAssetLibrary.duplicate_asset(source_path, destination)
        if not result:
            raise RuntimeError("Could not duplicate retargeter")
        ctl = unreal.IKRetargeterController.get_controller(result)
        for side, spec in sides.items():
            enum = getattr(unreal.RetargetSourceOrTarget, side.upper())
            name = ctl.duplicate_retarget_pose(before[side]["pose"], spec["pose_name"], enum)
            if str(name) != spec["pose_name"] or not ctl.set_current_retarget_pose(name, enum):
                raise RuntimeError("Could not activate new retarget pose")
            for bone, q in plans[side]["offsets"].items():
                ctl.set_rotation_offset_for_retarget_pose_bone(bone, unreal.Quat(*q), enum)
        after = {side: inspect(result, side) for side in before}
        report["verification"] = {side: verify(plans.get(side, before[side]), after[side]) for side in before}
        for side, planned in plans.items():
            native = {b["name"]: b for b in after[side]["bones"]}
            if "leg_alignment" in sides[side]:
                planned["stance"]["native_after"] = stance_metrics(after[side]["bones"], sides[side]["leg_alignment"])
            planned["posture"]["native_after"] = posture_metrics(after[side]["bones"], sides[side].get("posture_checks", []))
            if any(row["tilt_degrees"] > row["max_tilt_degrees"] for row in planned["posture"]["native_after"]):
                raise RuntimeError("Native posture exceeds reviewed tilt limit")
            for segment in planned["segments"]:
                segment["native_final_degrees"] = angle(sub(native[segment["child"]]["global_position"],
                                                            native[segment["bone"]]["global_position"]), segment["desired"])
        for side in before:
            if inspect(asset, side) != before[side]:
                raise RuntimeError("Original retargeter changed unexpectedly")
            if after[side]["root_offset"] != before[side]["root_offset"]:
                raise RuntimeError("Root offset changed unexpectedly")
        result.modify()
        if not unreal.EditorAssetLibrary.save_loaded_asset(result, False):
            raise RuntimeError("Saving independent retargeter failed")
        report.update(status="saved_native_readback_passed_needs_visual_review", after=after,
                      original_retargeter_unchanged=True)
        if agent_plan:
            report["acceptance"]["native_readback"] = "passed"
    except Exception as error:
        report.update(status="failed_do_not_use", error=str(error),
                      partial_asset=destination if result else None)
        raise
    finally:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8-sig"))
    profile = json.loads(Path(os.environ["PMX4UE_POSE_PROFILE"]).read_text(encoding="utf-8-sig"))
    build(profile, config["paths"]["ue_root"], os.environ["PMX4UE_OUTPUT"])
