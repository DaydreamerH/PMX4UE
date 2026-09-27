"""Rendered PIE comparison in a fresh, owned editor/template map only.

PMX_MOTION_PIE_RUN selects a fresh report name; CASES and REPEATS choose tests.
No quality, skeleton, animation, collisions, or saved level changes. Camera
follows the animated pelvis equally for all cases, including NoPhysics.
PMX_MOTION_PIE_CLOSE=1 closes only the specifically launched test editor.
"""
import json
import hashlib
import math
import os
from pathlib import Path
import statistics
import time
import traceback
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
base = "/Game/Characters/TololoSchool1001/PhysicsSandbox/"
dest = base + "Performance/MotionPerf_v1/"
paths = {n: dest + "ABP_" + n + "_Travel" for n in ("Skirt6Outer4", "Both4", "Both3", "NoPhysics")}
paths["Baseline6"] = base + "Performance/Motion_v3/ABP_BoneBoundedDeferred_Travel"
paths["ChestFollow"] = base + "Performance/ChestFollow_v1/ABP_ChestFollow_Travel"
names = os.environ.get("PMX_MOTION_PIE_CASES", "Baseline6,Skirt6Outer4,Both4,Both3,NoPhysics").split(",")
cases = names * int(os.environ.get("PMX_MOTION_PIE_REPEATS", "1"))
run = os.environ.get("PMX_MOTION_PIE_RUN", "MotionPerf_PIE_v1")
assert run.replace("_", "").isalnum()
output = project / "Saved/PMX4UE" / run / "report.json"
if output.exists():
    raise RuntimeError("Refusing to overwrite a previous benchmark")
numerical = json.loads((project / "Saved/PMX4UE/MotionPerf_v1/numerical.json").read_text(encoding="utf-8"))
assert numerical["status"].startswith("numerically_measured")
classes = {n: unreal.EditorAssetLibrary.load_blueprint_class(paths[n]) for n in names}
assert all(classes.values())
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world = editor.get_editor_world()
assert world.get_path_name().startswith(("/Temp/Untitled", "/Engine/Maps/Templates/"))
assert not level.is_in_play_in_editor()
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
actor.set_actor_label("PMX_MotionPerf")
body = actor.get_editor_property("skeletal_mesh_component")
body.set_skeletal_mesh_asset(unreal.load_asset(base + "SK_TololoSchool1001_UpperOnlyCm_v1"))
body.set_anim_instance_class(classes[cases[0]])
body.set_update_animation_in_editor(False)
unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
unreal.MMD2UEAgentMCPTools.align_viewport_to_camera("", 90., 290., 0., 38., actor.get_actor_label())
position, rotation = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
reference_anchor = body.get_socket_location("LowerBody")
camera = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.CameraActor, position, rotation)
camera.set_actor_label("PMX_MotionPerf_Camera")
camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(55.)
previous_cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
duration = 20.
report = dict(mode="rendered_PIE", quality_changes=False, map=world.get_path_name(),
              camera_fov=55., rendering_mode="offscreen" if "renderoffscreen" in unreal.SystemLibrary.get_command_line().lower() else "windowed",
              seconds_per_case=duration, warmup_seconds=8, tests=[], previous_max_fps=previous_cap,
              scope="One character, authored Center displacement and looping, camera follows pelvis. Not packaged-game acceptance.")
def digest_asset(path):
    filename = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(filename.read_bytes()).hexdigest()

report["input_hashes"] = {paths[n]: digest_asset(paths[n]) for n in names}
settings_class = unreal.load_class(None, "/Script/UnrealEd.EditorPerformanceSettings")
if settings_class:
    # This class has no generated Python wrapper in this engine build: use its
    # reflected C++ property name rather than guessing a Python alias.
    report["background_cpu_throttle"] = bool(unreal.get_default_object(settings_class).get_editor_property("bThrottleCPUWhenNotForeground"))
if os.environ.get("PMX_MOTION_REQUIRE_UNTHROTTLED") == "1":
    assert report.get("background_cpu_throttle") is False, "Owned hidden benchmark must not throttle in background"
state = dict(index=0, stage="await_pie", start=time.perf_counter(), last_world=-1.,
             last_wall=time.perf_counter(), frames=[], wall=[], callback=None)
deadline = time.perf_counter() + 120 + len(cases)*40

def command(value):
    unreal.SystemLibrary.execute_console_command(editor.get_game_world() or world, value)

def persist():
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

def begin():
    command("t.MaxFPS 200")
    assert unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS") == 200
    report["vsync"] = unreal.SystemLibrary.get_console_variable_int_value("r.VSync")
    report["screen_percentage"] = unreal.SystemLibrary.get_console_variable_float_value("r.ScreenPercentage")
    b = state["body"]
    b.set_anim_instance_class(classes[cases[state["index"]]])
    instance = b.get_anim_instance()
    assert instance and instance.get_class() == classes[cases[state["index"]]]
    # Retain the actual animated Center travel for every case/control.
    instance.set_root_motion_mode(unreal.RootMotionMode.NO_ROOT_MOTION_EXTRACTION)
    state.update(stage="running", start=time.perf_counter(), frames=[], wall=[], last_world=-1.,
                 last_wall=time.perf_counter(), pose_samples=[], last_pose_sample=-1., extra_captures=0)

def finish():
    unreal.unregister_slate_post_tick_callback(state["callback"])
    command("t.MaxFPS " + str(previous_cap))
    report["restored_max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    report["input_assets_unchanged"] = all(digest_asset(p) == h for p,h in report["input_hashes"].items())
    persist()
    level.editor_request_end_play()
    if os.environ.get("PMX_MOTION_PIE_CLOSE") == "1":
        command("QUIT_EDITOR")

def tick_impl():
    now = time.perf_counter()
    assert now < deadline, "Benchmark timeout"
    game = editor.get_game_world()
    if state["stage"] == "await_pie":
        if not game:
            return
        actors = [a for a in unreal.GameplayStatics.get_all_actors_of_class(game, unreal.SkeletalMeshActor)
                  if a.get_actor_label() == "PMX_MotionPerf"]
        cameras = [a for a in unreal.GameplayStatics.get_all_actors_of_class(game, unreal.CameraActor)
                   if a.get_actor_label() == "PMX_MotionPerf_Camera"]
        if not actors or not cameras:
            return
        state["body"] = actors[0].get_editor_property("skeletal_mesh_component")
        state["camera"] = cameras[0]
        pawn = unreal.GameplayStatics.get_player_pawn(game, 0)
        if pawn and isinstance(pawn, unreal.DefaultPawn):
            # The template spectator sphere can occlude the character; it is
            # not a PMX body. Hide rendering only in this unsaved test world.
            report["hidden_template_pawn"] = pawn.get_path_name()
            pawn.set_actor_hidden_in_game(True)
        unreal.GameplayStatics.get_player_controller(game, 0).set_view_target_with_blend(cameras[0])
        report["viewport_size"] = list(unreal.GameplayStatics.get_player_controller(game, 0).get_viewport_size())
        command("stat fps")
        command("stat unit")
        begin()
        return
    assert game, "PIE ended early"
    world_time = unreal.GameplayStatics.get_time_seconds(game)
    if world_time == state["last_world"]:
        return
    state["last_world"] = world_time
    anchor = state["body"].get_socket_location("LowerBody")
    state["camera"].set_actor_location(position + anchor - reference_anchor, False, False)
    interval = (now - state["last_wall"])*1000
    state["last_wall"] = now
    elapsed = now-state["start"]
    if state["stage"] == "running" and 8 <= elapsed < 8+duration:
        state["frames"].append(unreal.GameplayStatics.get_world_delta_seconds(game)*1000)
        state["wall"].append(interval)
        if elapsed-state["last_pose_sample"] >= .5:
            state["last_pose_sample"] = elapsed
            sample = dict(elapsed=elapsed, world_time=world_time)
            for bone in ("LowerBody", "LegD_L", "Skirt_0_0"):
                p = state["body"].get_socket_location(bone)
                sample[bone] = [p.x,p.y,p.z]
            state["pose_samples"].append(sample)
    if state["stage"] == "running" and elapsed >= 8+duration:
        values = sorted(state["frames"])
        assert values, "No advancing game frames"
        pct = lambda p: values[min(len(values)-1, math.ceil(len(values)*p)-1)]
        name = cases[state["index"]]
        # Capture the running game viewport, not the separate editor preview.
        capture_path = project / "Saved/MMD2UECaptures" / (run + "_" + str(state["index"]) + "_" + name + ".png")
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        command('HighResShot 1000x1000 filename="' + capture_path.as_posix() + '"')
        capture = dict(status="requested_game_viewport", output_path=str(capture_path))
        report["tests"].append(dict(case=name, blueprint=paths[name], frames=len(values),
            mean_ms=statistics.mean(values), fps=1000/statistics.mean(values), p95_ms=pct(.95),
            p99_ms=pct(.99), max_ms=max(values), observed_fps=len(values)/duration,
            slate_mean_ms=statistics.mean(state["wall"]), max_fps=unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS"),
            over_budget_fraction=sum(v>1000/60 for v in values)/len(values), capture=capture,
            pose_samples=state["pose_samples"]))
        result = report["tests"][-1]
        result["measurement_valid"] = abs(result["fps"]-result["observed_fps"])/result["fps"] < .10
        if not result["measurement_valid"]:
            report["status"] = "invalid_measurement_stopped"
            state["abort_after_capture"] = True
        state["stage"] = "capturing"
        persist()
    if (state["stage"] == "capturing" and cases[state["index"]] == "ChestFollow"
            and state["extra_captures"] < 2 and elapsed >= 29+state["extra_captures"]):
        state["extra_captures"] += 1
        path = project / "Saved/MMD2UECaptures" / (run + "_" + str(state["index"]) +
            "_ChestFollow_phase" + str(state["extra_captures"]) + ".png")
        command('HighResShot 1000x1000 filename="' + path.as_posix() + '"')
        report["tests"][-1].setdefault("extra_captures", []).append(dict(elapsed=elapsed,output_path=str(path)))
        persist()
    if elapsed > 31:
        if state.get("abort_after_capture"):
            finish()
            return
        state["index"] += 1
        if state["index"] == len(cases):
            report["status"] = "completed"
            finish()
        else:
            begin()

def tick(delta):
    try:
        tick_impl()
    except Exception:
        report["status"] = "error"
        report["error"] = traceback.format_exc()
        unreal.log_error(report["error"])
        finish()

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
state["callback"] = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
