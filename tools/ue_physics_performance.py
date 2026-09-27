"""Config-driven rendered PIE comparison in a fresh, owned editor/template map only.

PMX_PHYSICS_PLAN selects assets/policy; PMX_PHYSICS_TEST_REPORT proves numerical completion.
No quality, skeleton, animation, collisions, or saved level changes. Camera
follows the animated pelvis equally for all cases, including NoPhysics.
PMX_PIE_CLOSE=1 closes only the specifically launched test editor.
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

from ue_bridge import resolve, checked
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
plan_path = Path(os.environ["PMX_PHYSICS_PLAN"])
plan = json.loads(plan_path.read_text(encoding="utf-8"))
fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
numerical = json.loads(Path(os.environ["PMX_PHYSICS_TEST_REPORT"]).read_text(encoding="utf-8"))
if plan.get("rest_only") or plan.get("status") != "ready" or not plan["performance_test"]["enabled"]:
    raise RuntimeError("A reviewed animated plan is required")
if numerical.get("plan_sha256") != fingerprint or not numerical.get("status", "").startswith("numerically_measured"):
    raise RuntimeError("Numerical report does not match this plan")
policy = plan["performance_test"]
if policy["repeats"] < 3 or policy["seconds"] < 20:
    raise RuntimeError("Performance acceptance requires >=3 repeats and >=20 seconds")
paths = dict(NoPhysics=plan["performance_controls"]["no_physics"],
             SynchronousControl=plan["performance_controls"]["synchronous"], Candidate=plan["walk_blueprint"])
names = list(paths)
cases = names * policy["repeats"]
run = "physics_performance"
output = Path(os.environ["PMX_PHYSICS_OUTPUT"])
if output.exists():
    raise RuntimeError("Refusing to overwrite a previous benchmark")
classes = {n: unreal.EditorAssetLibrary.load_blueprint_class(paths[n]) for n in names}
assert all(classes.values())
for asset_path in list(paths.values()) + [p["asset"] for p in plan["partitions"]]:
    asset = unreal.load_asset(asset_path)
    if not asset or unreal.EditorAssetLibrary.get_metadata_tag(asset, "MMD2UE.PhysicsPlanSHA256") != fingerprint:
        raise RuntimeError("Physics plan provenance mismatch: " + asset_path)
anchor_name = plan["measurement_anchor"]
measured_names = sorted({b["target_bone"] for p in plan["partitions"] for b in p["bodies"] if not b["kinematic"]})
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world = editor.get_editor_world()
assert world.get_path_name().startswith(("/Temp/Untitled", "/Engine/Maps/Templates/"))
assert not level.is_in_play_in_editor()
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
actor.set_actor_label("PMX_MotionPerf")
body = actor.get_editor_property("skeletal_mesh_component")
body.set_skeletal_mesh_asset(unreal.load_asset(plan["mesh"]))
body.set_anim_instance_class(classes[cases[0]])
body.set_update_animation_in_editor(False)
unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
resolve("visual").align_viewport_to_camera("", 90., 290., 0., 38., actor.get_actor_label())
position, rotation = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
reference_anchor = body.get_socket_location(anchor_name)
camera = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.CameraActor, position, rotation)
camera.set_actor_label("PMX_MotionPerf_Camera")
camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(55.)
previous_cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
duration = float(policy["seconds"])
report = dict(mode="rendered_PIE", quality_changes=False, map=world.get_path_name(),
              camera_fov=55., rendering_mode="offscreen" if "renderoffscreen" in unreal.SystemLibrary.get_command_line().lower() else "windowed",
              seconds_per_case=duration, warmup_seconds=8, tests=[], previous_max_fps=previous_cap,
              scope="One character, authored animation displacement and looping, camera follows reviewed anchor. Not packaged-game acceptance.")
def digest_asset(path):
    filename = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(filename.read_bytes()).hexdigest()

dependencies = list(paths.values()) + [plan["mesh"], plan["animation"],
    body.get_skeletal_mesh_asset().get_editor_property("skeleton").get_path_name()] + [p["asset"] for p in plan["partitions"]]
report["input_hashes"] = {p: digest_asset(p) for p in dependencies}
report["plan_sha256"] = fingerprint
report["performance_policy"] = policy
report["requested_viewport_size"] = [policy.get("viewport_width", 1920), policy.get("viewport_height", 1080)]
report["engine"] = unreal.SystemLibrary.get_engine_version()
gpu_query = getattr(getattr(unreal, "PlatformLibrary", None), "get_primary_gpu_brand", None)
report["graphics_adapter"] = gpu_query() if callable(gpu_query) else "See UE log"
report["quality_cvars"] = {k: unreal.SystemLibrary.get_console_variable_float_value(k) for k in
    ("sg.ViewDistanceQuality","sg.ShadowQuality","sg.TextureQuality","sg.EffectsQuality","sg.PostProcessQuality","r.DynamicRes.OperationMode")}
report["command_line"] = unreal.SystemLibrary.get_command_line()
settings_class = unreal.load_class(None, "/Script/UnrealEd.EditorPerformanceSettings")
if settings_class:
    # This class has no generated Python wrapper in this engine build: use its
    # reflected C++ property name rather than guessing a Python alias.
    report["background_cpu_throttle"] = bool(unreal.get_default_object(settings_class).get_editor_property("bThrottleCPUWhenNotForeground"))
assert report.get("background_cpu_throttle") is False, "Owned hidden benchmark must not throttle in background"
state = dict(index=0, stage="await_pie", start=time.perf_counter(), last_world=-1.,
             last_wall=time.perf_counter(), frames=[], wall=[], callback=None)
deadline = time.perf_counter() + 120 + len(cases)*(duration+20)

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
    report["capture_files_present"] = all(Path(r["capture"]["output_path"]).is_file() for r in report["tests"])
    report["input_assets_unchanged"] = all(digest_asset(p) == h for p,h in report["input_hashes"].items())
    persist()
    level.editor_request_end_play()
    if os.environ.get("PMX_PIE_CLOSE") == "1":
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
        assert resolve("workflow").set_preview_resolution(*report["requested_viewport_size"])
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
    anchor = state["body"].get_socket_location(anchor_name)
    state["camera"].set_actor_location(position + anchor - reference_anchor, False, False)
    interval = (now - state["last_wall"])*1000
    state["last_wall"] = now
    elapsed = now-state["start"]
    if state["stage"] == "running" and 8 <= elapsed < 8+duration:
        report["viewport_size"] = list(unreal.GameplayStatics.get_player_controller(game, 0).get_viewport_size())
        assert report["viewport_size"] == report["requested_viewport_size"], "Actual viewport differs from requested test size"
        state["frames"].append(unreal.GameplayStatics.get_world_delta_seconds(game)*1000)
        state["wall"].append(interval)
        if elapsed-state["last_pose_sample"] >= .5:
            state["last_pose_sample"] = elapsed
            sample = dict(elapsed=elapsed, world_time=world_time)
            for bone in [anchor_name] + measured_names[:3]:
                p = state["body"].get_socket_location(bone)
                sample[bone] = [p.x,p.y,p.z]
            state["pose_samples"].append(sample)
    if state["stage"] == "running" and elapsed >= 8+duration:
        values = sorted(state["frames"])
        assert values, "No advancing game frames"
        pct = lambda p: values[min(len(values)-1, math.ceil(len(values)*p)-1)]
        name = cases[state["index"]]
        # Capture the running game viewport, not the separate editor preview.
        capture_path = output.parent / "captures" / (run + "_" + str(state["index"]) + "_" + name + ".png")
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
    if (state["stage"] == "capturing" and cases[state["index"]] == "Candidate"
            and state["extra_captures"] < 2 and elapsed >= 9+duration+state["extra_captures"]):
        state["extra_captures"] += 1
        path = output.parent / "captures" / (run + "_" + str(state["index"]) +
            "_Candidate_phase" + str(state["extra_captures"]) + ".png")
        command('HighResShot 1000x1000 filename="' + path.as_posix() + '"')
        report["tests"][-1].setdefault("extra_captures", []).append(dict(elapsed=elapsed,output_path=str(path)))
        persist()
    if elapsed > 11+duration:
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
assert resolve("workflow").begin_preview_window(*report["requested_viewport_size"]), "Could not start owned PIE window"
