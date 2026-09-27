"""Read-only runtime capability report, callable through the workbench runner."""
import json
import os
from pathlib import Path
import unreal
from ue_bridge import inventory

data = dict(schema="pmx4ue.capabilities.v1", project=unreal.Paths.project_dir(),
            engine=unreal.SystemLibrary.get_engine_version(), capabilities=inventory())
data["retarget_export"] = all(hasattr(unreal, name) for name in ("IKRetargetBatchOperation", "IKRetargetBatchOperationInputs"))
data["status"] = "available" if all(r["available"] for r in data["capabilities"].values()) and data["retarget_export"] else "missing_capabilities"
path = Path(os.environ["PMX4UE_OUTPUT"])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("x", encoding="utf-8") as stream:
    json.dump(data, stream, indent=2)
if data["status"] != "available":
    raise RuntimeError(data)
