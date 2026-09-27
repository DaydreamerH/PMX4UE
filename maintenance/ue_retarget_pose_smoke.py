"""Run in isolated UE test project, then rerun with PMX4UE_POSE_RELOAD=1.

Uses the supplied rig on both sides: validates native pose editing, NOT
cross-character retarget quality. No source character content is distributed.
"""
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ue_retarget_pose import build, inspect
from retarget_pose_math import verify

config = json.loads(Path(os.environ["PMX4UE_POSE_TEST_CONFIG"]).read_text(encoding="utf-8"))
folder = Path(config["report_dir"])
folder.mkdir(parents=True, exist_ok=True)
root = config["namespace"]
original_path = root + "/RTG_PoseBaseline"

if os.environ.get("PMX4UE_POSE_RELOAD") == "1":
    results = {}
    for filename in ("auto.json", "manual.json"):
        report = json.loads((folder / filename).read_text(encoding="utf-8"))
        asset = unreal.load_asset(report["profile"]["output_retargeter"])
        results[filename] = {side: verify(expected, inspect(asset, side)) for side, expected in report["after"].items()}
    base = unreal.load_asset(original_path)
    before = json.loads((folder / "auto.json").read_text(encoding="utf-8"))["before"]
    assert all(inspect(base, side) == snapshot for side, snapshot in before.items())
    (folder / "reload.json").write_text(json.dumps(dict(passed=True, results=results,
        source_unchanged=True, scope="Same-rig pose editing only; not animation retarget quality"), indent=2), encoding="utf-8")
else:
    if unreal.EditorAssetLibrary.does_asset_exist(original_path):
        raise RuntimeError("Test baseline already exists: use a fresh namespace")
    rig = unreal.load_asset(config["rig"])
    assert isinstance(rig, unreal.IKRigDefinition)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset("RTG_PoseBaseline", root, unreal.IKRetargeter, unreal.IKRetargetFactory())
    ctl = unreal.IKRetargeterController.get_controller(asset)
    ctl.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, rig)
    ctl.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, rig)
    ctl.add_default_ops()
    assert unreal.EditorAssetLibrary.save_loaded_asset(asset, False)
    profile = dict(reviewed=True, retargeter=original_path, output_retargeter=root + "/RTG_TPose",
                   sides={side: dict(pose_name="PMX4UE_TPose", auto_arms=True,
                                     up_axis=config["up_axis"], arms=config["arms"])
                          for side in ("source", "target")})
    automatic = build(profile, root, folder / "auto.json")
    for side in ("source", "target"):
        modified = set(automatic["plans"][side]["offsets"])
        for before, after in zip(automatic["before"][side]["bones"], automatic["after"][side]["bones"]):
            assert before["ref_position"] == after["ref_position"]
            assert before["ref_rotation"] == after["ref_rotation"]
            assert before["local_position"] == after["local_position"]
            if before["name"] not in modified:
                assert before["offset"] == after["offset"]
    manual = dict(reviewed=True, retargeter=profile["output_retargeter"], output_retargeter=root + "/RTG_TPose_Manual",
                  sides=dict(target=dict(pose_name="PMX4UE_TPose_Manual", auto_arms=False,
                      edits=[dict(bone=config["arms"]["left"][2], mode="add_local", axis=[0, 1, 0], degrees=5)])))
    build(manual, root, folder / "manual.json")
    # A second attempt must fail instead of overwriting our verified asset.
    try:
        build(profile, root, folder / "should_not_exist.json")
    except ValueError:
        pass
    else:
        raise AssertionError("Overwrite guard failed")
    (folder / "smoke.json").write_text(json.dumps(dict(passed=True,
        automatic={side: {"errors": automatic["verification"][side], "segments": automatic["plans"][side]["segments"]}
                   for side in ("source", "target")},
        original_unchanged=True, nonedited_local_transforms_unchanged=True), indent=2), encoding="utf-8")
