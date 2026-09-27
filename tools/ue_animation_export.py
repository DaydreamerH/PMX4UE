"""UE 5.8 batch retarget, explicit reviewed inputs and isolated outputs."""
import hashlib
import json
import os
from pathlib import Path
import re
import unreal


def build(profile, namespace, output):
    if profile.get("reviewed") is not True or profile.get("schema") != "pmx4ue.animation-export.v1":
        raise ValueError("Review source/target/retarget pose and animation selection first")
    target_path = profile["output_directory"].rstrip("/")
    if not target_path.startswith(namespace.rstrip("/")+"/") or not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", target_path):
        raise ValueError("Animation output must belong to the new character namespace")
    path = Path(output)
    if path.exists() or unreal.EditorAssetLibrary.list_assets(target_path, recursive=True, include_folder=False):
        raise ValueError("Output exists; use a new animation variant")
    source = unreal.load_asset(profile["source_mesh"])
    target = unreal.load_asset(profile["target_mesh"])
    rtg = unreal.load_asset(profile["retargeter"])
    if not isinstance(source, unreal.SkeletalMesh) or not isinstance(target, unreal.SkeletalMesh) or source == target or not isinstance(rtg, unreal.IKRetargeter):
        raise ValueError("Actual different source/target meshes and an IK Retargeter required")
    ctl = unreal.IKRetargeterController.get_controller(rtg)
    for side, mesh in ((unreal.RetargetSourceOrTarget.SOURCE, source), (unreal.RetargetSourceOrTarget.TARGET, target)):
        if ctl.get_preview_mesh(side) != mesh:
            raise ValueError("Retargeter preview mesh differs from requested source/target")
    clips = [unreal.load_asset(p) for p in profile["animations"]]
    if not clips or len(set(profile["animations"])) != len(clips):
        raise ValueError("Select unique animation sequences")
    if any(not isinstance(c, unreal.AnimSequence) or c.get_editor_property("skeleton") != source.get_editor_property("skeleton") for c in clips):
        raise ValueError("Source animation skeleton mismatch")
    names = [str(c.get_name()) for c in clips]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate animation basenames require separate export batches")
    project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    inputs = [profile[k] for k in ("source_mesh", "target_mesh", "retargeter")] + profile["animations"]
    inputs += [m.get_editor_property("skeleton").get_path_name() for m in (source, target)]
    inputs += [ctl.get_ik_rig(s).get_path_name() for s in (unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET)]
    def digest(asset_path):
        package = asset_path.split(".")[0]
        if not package.startswith("/Game/"):
            raise ValueError("Only project content inputs supported for fingerprinted export")
        return hashlib.sha256((project/"Content"/(package[6:]+".uasset")).read_bytes()).hexdigest()
    hashes = {p: digest(p) for p in inputs}
    args = unreal.IKRetargetBatchOperationInputs()
    for key, value in dict(assets_to_retarget=[unreal.EditorAssetLibrary.find_asset_data(c.get_path_name()) for c in clips],
                           source_mesh=source, target_mesh=target, ik_retarget_asset=rtg,
                           target_path=target_path, use_source_path=False, include_referenced_assets=False,
                           overwrite_existing_files=False).items():
        args.set_editor_property(key, value)
    result = unreal.IKRetargetBatchOperation.run_batch_retarget(args)
    assets = [r.get_asset() for r in result]
    if len(assets) != len(clips):
        raise RuntimeError("Retarget export incomplete; retain partial destination and choose a new version")
    for asset in assets:
        if (not isinstance(asset, unreal.AnimSequence) or not asset.get_path_name().startswith(target_path+"/")
                or asset.get_editor_property("skeleton") != target.get_editor_property("skeleton")
                or asset.get_play_length() <= 0 or not unreal.EditorAssetLibrary.save_loaded_asset(asset, False)):
            raise RuntimeError("Invalid retarget output")
    if any(digest(p) != h for p, h in hashes.items()):
        raise RuntimeError("Source inputs changed during export")
    report = dict(status="exported_animation_visual_review_pending", inputs=hashes,
                  assets=[a.get_path_name() for a in assets], target_skeleton=target.get_editor_property("skeleton").get_path_name(),
                  output_hashes={a.get_path_name(): digest(a.get_path_name()) for a in assets},
                  root_lock_policy="Source settings unchanged; uses reviewed retargeter ops")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    return report


if __name__ == "__main__":
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8"))
    profile = json.loads(Path(os.environ["PMX4UE_ANIMATION_PROFILE"]).read_text(encoding="utf-8"))
    build(profile, config["paths"]["ue_root"], os.environ["PMX4UE_OUTPUT"])
