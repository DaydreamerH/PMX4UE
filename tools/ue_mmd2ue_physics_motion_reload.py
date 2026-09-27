"""Fresh-process persistence/long-loop check for Motion_v3; no asset writes."""
import hashlib
import json
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
folder = project / "Saved/PMX4UE/PhysicsMotion_v3"
output = folder / "reload.json"
if output.exists():
    raise RuntimeError("Reload report exists")
report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
assert report["status"] == "measured_needs_comparison_and_visual_review"
def digest(path):
    return hashlib.sha256((project / "Content" / (path.split('.')[0].removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()
assert all(digest(p)==h for p,h in report["original_hashes"].items())
result = dict(tests={}, original_assets_unchanged=True, visual_review="pending",
              root_motion_scope="unextracted bone movement and synthetic actor movement, not CharacterMovement")
cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
try:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS 200")
    assert unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS") == 200
    for clip, fps, hitch in (("Travel",15.,False),("Travel",60.,True),("InPlace",15.,False)):
        build = report["builds"]["BoneBoundedDeferred_"+clip]
        value = json.loads(unreal.MMD2UEPhysicsMotionTools.test_motion(
            report["mesh"],build["asset"],20.,fps,hitch,clip=="InPlace"))
        assert "error" not in value and value["finite"] and value["seconds_completed"]>19.99
        assert value["simulated_bones"]==444 and value["filter_errors"]==0
        assert len(value["nodes"])==2 and all(n["base_bone"]=="LowerBody" and n["space"]==2
            and n["damping_alpha"]==0 and n["timing"]==2 for n in value["nodes"])
        result["tests"][f"{clip}_{int(fps)}_{hitch}"] = value
        assert value["max_skirt_radius_cm"]<60, "Skirt escaped local safety envelope"
    lib = getattr(unreal,"AnimationLibrary",None)
    if lib and hasattr(lib,"get_bone_pose_for_time"):
        clip = unreal.load_asset(report["clips"]["Travel"])
        result["animation_length"] = clip.get_play_length()
        result["local_bone_tracks"] = {}
        for name in ("SK_TololoPmxCmNative_v2_Skeleton","ParentNode","Center"):
            rows=[]
            for t in (0.,1.,2.,3.,clip.get_play_length()-.001):
                p=lib.get_bone_pose_for_time(clip,name,t,False).translation
                rows.append(dict(time=t,position=[p.x,p.y,p.z]))
            result["local_bone_tracks"][name]=rows
    assert all(digest(p)==h for p,h in report["original_hashes"].items())
    result["passed"] = True
finally:
    unreal.SystemLibrary.execute_console_command(world,"t.MaxFPS "+str(cap))
    result["restored_cap"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
