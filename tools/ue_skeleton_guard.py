"""Read back actual UE upper-limb structure; never equate an export flag with cleanup."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.skeleton_gate import verify, verify_import
from tools.legacy.skeleton_plan import verify_postconditions
from ue_bridge import resolve


def inspect_imported_skeleton(config, mesh):
    report = json.loads(resolve("physics").inspect_physics_mesh(mesh.get_path_name()))
    if report.get("status") != "inspected":
        raise RuntimeError(report)
    parents = {b["name"]: b.get("parent") or None for b in report["bones"]}
    result = dict(mesh=mesh.get_path_name(), final_bone_parents=parents,
                  scope="Structure readback only; binding warnings and animation remain separate")
    if config.get("pmx4ue", {}).get("skeleton_policy") == "upper-only":
        plan = json.loads((Path(config["paths"]["artifact_dir"]) / "skeleton_plan.json").read_text(encoding="utf-8-sig"))
        result["postconditions"] = verify_postconditions(plan, parents)
    return result


def guard(config, mesh, stage):
    """Used by supported UE write entry points as well as the outer runner."""
    artifact = config["paths"]["artifact_dir"]
    verify(config, artifact)
    verify_import(config, artifact, stage)
    build = json.loads((Path(artifact) / "ue_build_report.json").read_text(encoding="utf-8-sig"))
    if mesh.get_path_name().split('.')[0] != build["skeletal_mesh"].split('.')[0]:
        raise RuntimeError("Live target mesh differs from reviewed import")
    return inspect_imported_skeleton(config, mesh)
