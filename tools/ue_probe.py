"""Read-only API probe in an isolated blank project; creates no assets."""
import json
import os
from pathlib import Path
import unreal

required = {
    "PMX4UEPmxSkirtTools": ["inspect_physics_mesh", "build_experiment", "build_physics_blueprint"],
    "PMX4UEAgentMCPTools": ["inspect_material_compile", "capture_editor_viewport"],
    "IKRigController": ["get_controller"],
    "IKRetargeterController": ["get_controller"],
    "PMX4UERetargetTools": ["inspect_retarget_pose"],
    "AutomationUtilsBlueprintLibrary": ["finish_all_asset_compilation"],
    "SkeletalMesh": ["get_bone_parent"],
}
missing = [cls + "." + name for cls, names in required.items() for name in names
           if not hasattr(getattr(unreal, cls, None), name)]
report = dict(engine=unreal.SystemLibrary.get_engine_version(), missing=missing, passed=not missing,
              scope="Plugin load and Python API presence only; no character import")
Path(os.environ["PMX4UE_PROBE_OUTPUT"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
if missing:
    raise RuntimeError(missing)
