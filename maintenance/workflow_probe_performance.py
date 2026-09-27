"""Run generic performance collector on the isolated MMD2UE fixture."""
import os
from pathlib import Path
import runpy
import sys
import unreal
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/"tools"), str(root/"tools/legacy")]
out = root.parent/"Saved/PMX4UE/WorkflowProbe_v1"
os.environ.update(PMX_PHYSICS_PLAN=str(out/"physics_plan.json"),
    PMX_PHYSICS_TEST_REPORT=str(out/"physics_test.json"),
    PMX_PHYSICS_OUTPUT=str(out/"Performance_1080p_v2/performance.json"), PMX_PIE_CLOSE="1")
try:
    runpy.run_path(str(root/"tools/ue_physics_performance.py"), run_name="__main__")
except Exception:
    unreal.SystemLibrary.execute_console_command(None, "QUIT_EDITOR")
    raise
