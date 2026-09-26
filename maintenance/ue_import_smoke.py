"""UE-only isolated mesh import probe, never a visual/material acceptance test."""
import json
import os
from pathlib import Path
import sys
import unreal

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tools/legacy"))
from ue_context import BuildContext

ctx = BuildContext(os.environ["PMX4UE_CONFIG"], strict=False, require_map=False)
expected = Path(ctx.config["pmx4ue"]["project"]).resolve().parent
if Path(unreal.Paths.project_dir()).resolve() != expected:
    raise RuntimeError("Wrong project")
if unreal.EditorAssetLibrary.list_assets(ctx.names["ue_root"], True, False):
    raise RuntimeError("Smoke import requires empty destination namespace")
mesh = ctx.import_skeletal_mesh()
report = json.loads(unreal.PMX4UEPmxSkirtTools.inspect_physics_mesh(mesh.get_path_name()))
if report.get("status") != "inspected":
    raise RuntimeError(report)
report["non_unit_bones"] = [b["name"] for b in report["bones"] if any(abs(x-1) > .001 for x in b["component_scale"])]
report["scope"] = "Mesh import/component scales only; default materials; no animation/visual acceptance"
Path(os.environ["PMX4UE_PROBE_OUTPUT"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
if report["non_unit_bones"]:
    raise RuntimeError("Non-unit imported bones")
