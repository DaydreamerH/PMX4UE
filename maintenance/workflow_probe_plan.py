"""Offline Tololo regression fixture; reads historical evidence without changing it."""
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/"tools/legacy"))
from pmx_physics_plan import make_plan
project = root.parent
out = project/"Saved/PMX4UE/WorkflowProbe_v1"
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
profile = read(project/"Tools/MMDPipeline/characters/TololoSchool1001.pmx-physics.json")
test_profile = read(out/"physics_profile.json")
for key in ("asset_root", "variant", "test_animation", "simulation", "performance_test", "solver"):
    profile[key] = test_profile[key]
plan = make_plan(read(project/"Saved/PmxPhysicsWorkflow/Tololo/inventory.json"), profile, read(out/"physics_inspect.json"))
for name, value in (("physics_profile_reviewed.json", profile), ("physics_plan.json", plan)):
    with (out/name).open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
