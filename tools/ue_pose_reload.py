"""Verify a saved pose in a separate UE process; never save/mutate any asset."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def check(report_path, output):
    import unreal
    from ue_retarget_pose import inspect
    from retarget_pose_math import verify
    from retarget_workflow import fingerprint
    report = json.loads(Path(report_path).read_text(encoding="utf-8-sig"))
    if report.get("status") != "saved_native_readback_passed_needs_visual_review":
        raise ValueError("Need a successful native build report")
    if not report.get("process_id") or report["process_id"] == os.getpid():
        raise ValueError("Run this check in a separate, freshly started UE process")
    path = Path(output)
    if path.exists():
        raise ValueError("Reload report exists; no overwrite")
    asset = unreal.load_asset(report["profile"]["output_retargeter"])
    original = unreal.load_asset(report["profile"]["retargeter"])
    if not isinstance(asset, unreal.IKRetargeter) or not isinstance(original, unreal.IKRetargeter):
        raise ValueError("Saved retargeter or original missing")
    checks = {}
    for side in ("source", "target"):
        expected, actual = report["after"][side], inspect(asset, side)
        for key in ("pose", "mesh", "root_offset"):
            if actual[key] != expected[key]:
                raise ValueError("Saved " + key + " differs on " + side)
        checks[side] = verify(expected, actual)
        if fingerprint(inspect(original, side)) != fingerprint(report["before"][side]):
            raise ValueError("Original retarget pose changed since build")
    result = dict(status="fresh_reload_passed_needs_visual_animation_review", build_report_sha256=fingerprint(report),
                  process_id=os.getpid(), verification=checks, visual_review="pending", animation_review="pending")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return result


if __name__ == "__main__":
    check(os.environ["PMX4UE_POSE_BUILD_REPORT"], os.environ["PMX4UE_OUTPUT"])
