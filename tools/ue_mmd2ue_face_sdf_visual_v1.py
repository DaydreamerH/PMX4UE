"""Owned-editor PIE capture: reload candidate BP, freeze one animated pose, compare old/new face.
No source assets or user level saved. This is visual QA, not a performance benchmark.
"""
import hashlib
import json
import math
import time
import traceback
from pathlib import Path
import unreal

project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
folder=project/"Saved/PMX4UE/SDFHead_v1"
output=folder/"visual.json"
assert not output.exists()
build=json.loads((folder/"runtime_v2.json").read_text(encoding="utf-8"))
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world=editor.get_editor_world()
assert world.get_path_name().startswith(("/Temp/Untitled","/Engine/Maps/Templates/"))
cls=unreal.EditorAssetLibrary.load_blueprint_class(build["actor"])
actor=unreal.EditorLevelLibrary.spawn_actor_from_class(cls,unreal.Vector(),unreal.Rotator(yaw=55.))
actor.set_actor_label("SDFHead_Candidate")
camera=unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.CameraActor,unreal.Vector())
camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(25.)
unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
previous_cap=unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
state=dict(stage="await_pie",start=time.perf_counter(),callback=None)
report=dict(status="running", actor=build["actor"], visual_scope="Identical frozen animated pose, same camera/light, only face material changes", captures=[])

def command(s):
    unreal.SystemLibrary.execute_console_command(editor.get_game_world() or world,s)

def finish():
    if state["callback"]:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    command("t.MaxFPS "+str(previous_cap))
    report["input_assets_unchanged"]=all(hashlib.sha256((project/'Content'/(p.split('.')[0].removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()==h for p,h in build["input_hashes"].items())
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if level.is_in_play_in_editor(): level.editor_request_end_play()
    unreal.SystemLibrary.quit_editor()

def tick_impl():
    if time.perf_counter()-state["start"]>90:
        raise RuntimeError("Visual capture timeout")
    game=editor.get_game_world()
    if not game: return
    if state["stage"]=="await_pie":
        actors=unreal.GameplayStatics.get_all_actors_of_class(game,unreal.MMDFaceSDFPreviewActor)
        if not actors: return
        a=actors[0]
        body=a.get_editor_property("skeletal_mesh_component")
        driver=a.get_editor_property("face_sdf")
        assert str(driver.get_editor_property("head_bone"))=="Head", "Bone mapping lost on BP reload"
        assert body.get_skeletal_mesh_asset().get_path_name().split('.')[0]==build["mesh"]
        assert body.get_anim_instance(), "Animation BP was not restored"
        body.get_anim_instance().set_root_motion_mode(unreal.RootMotionMode.NO_ROOT_MOTION_EXTRACTION)
        cam=unreal.GameplayStatics.get_all_actors_of_class(game,unreal.CameraActor)[0]
        unreal.GameplayStatics.get_player_controller(game,0).set_view_target_with_blend(cam,0.)
        for pawn in unreal.GameplayStatics.get_all_actors_of_class(game,unreal.DefaultPawn): pawn.set_actor_hidden_in_game(True)
        for light in unreal.GameplayStatics.get_all_actors_of_class(game,unreal.DirectionalLight):
            light.set_actor_rotation(unreal.Rotator(pitch=-25.,yaw=-65.),False)
        command("t.MaxFPS 200")
        state.update(stage="warmup",body=body,driver=driver,camera=cam,since=time.perf_counter())
    body=state["body"]; driver=state["driver"]
    if state["stage"]=="warmup":
        if time.perf_counter()-state["since"]<5: return
        assert driver.get_editor_property("basis_valid"), "Runtime driver inactive"
        body.set_component_tick_enabled(False)
        head=body.get_socket_location("Head")
        f=driver.get_editor_property("face_forward_world")
        target=head+unreal.Vector(0,0,5.)
        position=target+f*110.+unreal.Vector(0,0,3.)
        rotation=unreal.MathLibrary.find_look_at_rotation(position,target)
        state["camera"].set_actor_location_and_rotation(position,rotation,False,False)
        report.update(face_forward_world=[f.x,f.y,f.z],head_position=[head.x,head.y,head.z],runtime_basis_valid=True,
                      actor_yaw=55.,physics_abp=body.get_anim_instance().get_class().get_path_name())
        state.update(stage="new_ready",since=time.perf_counter())
    elif state["stage"] in ("new_ready","old_ready") and time.perf_counter()-state["since"]>2:
        tag="new" if state["stage"]=="new_ready" else "old"
        path=project/"Saved/MMD2UECaptures"/("SDFHead_v1_"+tag+".png")
        path.parent.mkdir(parents=True,exist_ok=True)
        command('HighResShot 900x900 filename="'+path.as_posix()+'"')
        report["captures"].append(dict(variant=tag,path=str(path)))
        state.update(stage=tag+"_captured",since=time.perf_counter())
    elif state["stage"]=="new_captured" and time.perf_counter()-state["since"]>2:
        assert Path(report["captures"][-1]["path"]).is_file()
        old_face=unreal.load_asset("/Game/Characters/TololoSchool1001/Materials/MI_TololoSchool1001_Face")
        body.set_material(body.get_material_index("Face"),old_face)
        state.update(stage="old_ready",since=time.perf_counter())
    elif state["stage"]=="old_captured" and time.perf_counter()-state["since"]>2:
        assert all(Path(c["path"]).is_file() for c in report["captures"])
        report["status"]="captured_pending_agent_review"
        finish()

def tick(dt):
    try: tick_impl()
    except Exception:
        report.update(status="failed",error=traceback.format_exc())
        unreal.log_error(report["error"])
        finish()

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
state["callback"]=unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
