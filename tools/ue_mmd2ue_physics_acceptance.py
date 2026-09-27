"""Read-only current ChestFollow movement/low-FPS diagnostics; never writes assets."""
import hashlib
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
out = Path(os.environ["PMX_ACCEPTANCE_REPORT"])
assert not out.exists(), "Never overwrite diagnostics"
build = json.loads((project / "Saved/PMX4UE/ChestFollow_v1/build.json").read_text(encoding="utf-8"))
hashes = {**build["source_hashes"], **build["output_hashes"]}
def digest(path):
    return hashlib.sha256((project / "Content" / (path.split('.')[0].removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()
assert all(digest(p)==h for p,h in hashes.items()), "Assets changed since static inspection"
mesh = "/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1"
report = dict(status="running", asset=build["asset"], input_hashes=hashes, tests={},
              scope="Numerical envelope/filter checks, not contact-depth, rendered FPS or CharacterMovement acceptance")
cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
try:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS 200")
    report["max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    assert report["max_fps"] == 200
    for fps,hitch,move in ((60,False,False),(30,False,False),(15,False,False),
                           (60,True,False),(15,False,True),(60,True,True)):
        tag = f"{fps}_hitch{hitch}_component{move}"
        result = json.loads(unreal.MMD2UEPhysicsMotionTools.test_motion(mesh,build["asset"],20.,float(fps),hitch,move))
        report["tests"][tag] = result
        assert "error" not in result, result
        assert result["finite"] and result["seconds_completed"] > 19.99
        assert result["simulated_bones"] == 442 and result["filter_errors"] == 0
        assert result["filters_applied"] == 330 and result["max_skirt_radius_cm"] < 60
        assert len(result["nodes"]) == 2 and all(n["base_bone"] == "LowerBody" and n["space"] == 2
                                               and n["timing"] == 2 for n in result["nodes"])
        unreal.log("ACCEPTANCE_CASE " + tag)
    report["input_assets_unchanged"] = all(digest(p)==h for p,h in hashes.items())
    assert report["input_assets_unchanged"]
    report["status"] = "numerical_pass_visual_and_performance_pending"
except Exception as error:
    report.update(status="failed", error=str(error))
    raise
finally:
    unreal.SystemLibrary.execute_console_command(world,"t.MaxFPS "+str(cap))
    report["restored_max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
