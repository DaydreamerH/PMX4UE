"""Unreal bootstrap: env transport avoids Python argument quoting ambiguities."""
import json
import os
from pathlib import Path
import runpy
import sys
import unreal

package = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(package / "tools"))
sys.path.insert(0, str(package / "tools/legacy"))
config_path = Path(os.environ["PMX4UE_CONFIG"])
config = json.loads(config_path.read_text(encoding="utf-8"))
actual = Path(unreal.Paths.project_dir()).resolve()
if actual != Path(config["pmx4ue"]["project"]).resolve().parent:
    raise RuntimeError("Wrong UE project; refusing asset writes")
stage = os.environ["PMX4UE_STAGE"]
if stage == "physics-build":
    plan = json.loads(Path(os.environ["PMX_PHYSICS_PLAN"]).read_text(encoding="utf-8"))
    paths = [p["asset"] for p in plan["partitions"]] + [p for p in (plan["rest_blueprint"], plan["walk_blueprint"]) if p]
    paths += list(plan.get("performance_controls", {}).values())
    if any(not p.startswith(config["paths"]["ue_root"] + "/") for p in paths):
        raise RuntimeError("Physics destinations must belong to this character variant")
if stage in {"ue-build", "material-build"}:
    root = config["paths"]["ue_root"]
    occupied = unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False)
    if any(not path.startswith(root + "/Preflight/") for path in occupied):
        raise RuntimeError("Destination namespace occupied; choose a new character variant")
    # Strict map validation occurs before any imports in BuildContext.
script = Path(os.environ["PMX4UE_SCRIPT"]).resolve()
if not script.is_relative_to(package / "tools"):
    raise RuntimeError("Entry script must be part of this PMX4UE checkout")
sys.argv = [str(script), "--", "--config", str(config_path)]
runpy.run_path(str(script), run_name="__main__")
