"""Real PIE benchmark in an owned editor, temporary template world only.

No mesh/scene saves or quality changes. Uses t.MaxFPS 200 for every case and
restores the previous cap on exit. PMX_PIE_CASES selects
cases; PMX_PIE_SECONDS defaults 20 measured seconds, PMX_PIE_REPEATS defaults 1.
PMX_PIE_TRACE=1 captures traces per case (do not compare with untraced runs).
PMX_PIE_CLOSE=1 exits only the editor launched specifically for this script.
"""
import json
import math
import os
import statistics
import hashlib
import sys
import time
import traceback
from pathlib import Path

import unreal
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pmx_physics_settings import performance_verdict

plan_path = os.environ.get("PMX_PHYSICS_PLAN")
if not plan_path:
    raise RuntimeError("PMX_PHYSICS_PLAN is required; no character-specific fallback")
plan = None
fingerprint = None
if plan_path:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    policy = plan.get("performance_test", {})
    if plan.get("status") != "ready" or not policy.get("enabled"):
        raise RuntimeError("Plan is not ready for performance testing")
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    numerical = json.loads(Path(os.environ["PMX_PHYSICS_TEST_REPORT"]).read_text(encoding="utf-8"))
    if numerical.get("plan_sha256") != fingerprint or not numerical.get("status", "").startswith("numerically_measured"):
        raise RuntimeError("Fresh numerical test must pass for the same plan first")
    paths = dict(Candidate=plan["walk_blueprint"], SynchronousControl=plan["performance_controls"]["synchronous"],
                 NoPhysics=plan["performance_controls"]["no_physics"])
    for path in list(paths.values()) + [p["asset"] for p in plan["partitions"]]:
        asset = unreal.load_asset(path)
        if not asset or unreal.EditorAssetLibrary.get_metadata_tag(asset, "MMD2UE.PhysicsPlanSHA256") != fingerprint:
            raise RuntimeError("Plan provenance mismatch: " + path)
    mesh_path = plan["mesh"]
    cases = [("SynchronousControl", paths["SynchronousControl"])] + [("Candidate", paths["Candidate"])] * policy["repeats"] + [("NoPhysics", paths["NoPhysics"])]
# EditorAssetLibrary refuses asset loads during PIE. Resolve classes beforehand,
# otherwise a failed load could silently benchmark animation disabled.
classes = {path: unreal.EditorAssetLibrary.load_blueprint_class(path) for _, path in cases}
if any(value is None for value in classes.values()):
    raise RuntimeError("Missing test AnimBlueprint class")
duration = float(plan["performance_test"]["seconds"] if plan else os.environ.get("PMX_PIE_SECONDS", "20"))
run = os.environ.get("PMX_PIE_RUN", "PIE_v3")
if not run.replace("_", "").isalnum():
    raise ValueError("Unsafe run name")
out = Path(unreal.Paths.project_dir()) / "Saved/PmxPerformance" / run
output = Path(os.environ["PMX_PHYSICS_OUTPUT"]) if plan else out / "report.json"
if plan:
    out = output.parent
    if output.exists():
        raise RuntimeError("Performance report exists; choose a new output")
out.mkdir(parents=True, exist_ok=True)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world = editor.get_editor_world()
if not world.get_path_name().startswith(("/Temp/Untitled", "/Engine/Maps/Templates/")) or level.is_in_play_in_editor():
    raise RuntimeError("Requires a new temporary editor world, not a user PIE session")
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
actor.set_actor_label("PMX_PIE_Benchmark")
body = actor.get_editor_property("skeletal_mesh_component")
body.set_skeletal_mesh_asset(unreal.load_asset(mesh_path))
body.set_anim_instance_class(classes[cases[0][1]])
body.set_update_animation_in_editor(False)
unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
unreal.PMX4UEAgentMCPTools.align_viewport_to_camera("", 90., 290., 0., 38., actor.get_actor_label())
position, rotation = unreal.EditorLevelLibrary.get_level_viewport_camera_info()
camera = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.CameraActor, position, rotation)
camera.set_actor_label("PMX_PIE_Camera")
camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(38.)
report = {"mode": "PIE", "seconds_per_case": duration, "quality_changes": False, "tests": [],
          "metric": "PIE world delta seconds, once per observed game frame; Slate intervals stored separately",
          "trace_enabled": os.environ.get("PMX_PIE_TRACE") == "1"}
if plan:
    report.update(plan_sha256=fingerprint, plan=plan_path, performance_policy=plan["performance_test"])
previous_max_fps = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
report["previous_max_fps"] = previous_max_fps
state = dict(index=0, stage="await_pie", start=time.perf_counter(), callback=None, frames=[], wall=[], samples=[],
             last_world=-1., last_wall=time.perf_counter(), game_actor=None, captured=False, tracing=False)
deadline = time.perf_counter() + 90 + len(cases)*(duration+30)


def command(text):
    unreal.SystemLibrary.execute_console_command(editor.get_game_world() or world, text)


def persist():
    if plan:
        report["acceptance"] = performance_verdict(report["tests"], plan["performance_test"])
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")


def begin_case():
    name, path = cases[state["index"]]
    command("t.MaxFPS 200")
    cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    if abs(cap-200.) > .01:
        raise RuntimeError("t.MaxFPS 200 was not applied")
    report["max_fps"] = cap
    report["vsync"] = unreal.SystemLibrary.get_console_variable_int_value("r.VSync")
    game_body = state["game_actor"].get_editor_property("skeletal_mesh_component")
    game_body.set_anim_instance_class(classes[path])
    if not game_body.get_anim_instance() or game_body.get_anim_instance().get_class() != classes[path]:
        raise RuntimeError("Expected animation class is not actually running")
    state.update(stage="running", start=time.perf_counter(), last_world=-1., last_wall=time.perf_counter(),
                 frames=[], wall=[], samples=[], captured=False, tracing=False)


def finish():
    unreal.unregister_slate_post_tick_callback(state["callback"])
    command("t.MaxFPS " + str(previous_max_fps))
    level.editor_request_end_play()
    if os.environ.get("PMX_PIE_CLOSE") == "1":
        command("QUIT_EDITOR")


def tick_impl(delta):
    now = time.perf_counter()
    if now > deadline:
        raise RuntimeError("PIE benchmark timed out (paused or not advancing)")
    game = editor.get_game_world()
    if state["stage"] == "await_pie":
        if now-state["start"] > 90:
            raise RuntimeError("PIE startup timed out")
        if not game:
            return
        actors = unreal.GameplayStatics.get_all_actors_of_class(game, unreal.SkeletalMeshActor)
        matches = [a for a in actors if a.get_actor_label() == "PMX_PIE_Benchmark"]
        if not matches:
            return
        state["game_actor"] = matches[0]
        cameras = [a for a in unreal.GameplayStatics.get_all_actors_of_class(game, unreal.CameraActor)
                   if a.get_actor_label() == "PMX_PIE_Camera"]
        unreal.GameplayStatics.get_player_controller(game, 0).set_view_target_with_blend(cameras[0])
        command("stat fps")
        command("stat unit")
        begin_case()
        return
    elapsed = now-state["start"]
    if not game:
        raise RuntimeError("PIE ended before the benchmark completed")
    name = cases[state["index"]][0]
    world_time = unreal.GameplayStatics.get_time_seconds(game)
    if world_time == state["last_world"]:
        return
    state["last_world"] = world_time
    interval = (now-state["last_wall"])*1000
    state["last_wall"] = now
    if 5 <= elapsed < 5+duration:
        if report["trace_enabled"] and not state["tracing"]:
            command('Trace.File "' + str(out / (str(state["index"])+"_"+name+".utrace")) + '" cpu,frame,bookmark,task')
            state["tracing"] = True
        state["frames"].append(unreal.GameplayStatics.get_world_delta_seconds(game)*1000)
        state["wall"].append(interval)
    if elapsed >= 5+duration and not state["captured"]:
        if state["tracing"]:
            command("Trace.Stop")
        # Native viewport capture saves asynchronously; do not include it in timings.
        capture = json.loads(unreal.PMX4UEAgentMCPTools.capture_editor_viewport(
            run+"_"+str(state["index"])+"_"+name+".png", 1000, 1000))
        values = sorted(state["frames"])
        if not values:
            raise RuntimeError("No PIE frames measured")
        percentile = lambda p: values[min(len(values)-1, math.ceil(p*len(values))-1)]
        report["tests"].append(dict(case=name, blueprint=cases[state["index"]][1], frames=len(values),
            mean_ms=statistics.mean(values), fps=1000/statistics.mean(values), p95_ms=percentile(.95),
            p99_ms=percentile(.99), max_ms=max(values), over_16_667_fraction=sum(v>1000/60 for v in values)/len(values),
            slate_mean_ms=statistics.mean(state["wall"]), observed_frames_per_second=len(values)/duration,
            max_fps=unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS"), capture=capture))
        persist()
        state["captured"] = True
    if elapsed > 8+duration:
        state["index"] += 1
        if state["index"] == len(cases):
            finish()
        else:
            begin_case()


def tick(delta):
    try:
        tick_impl(delta)
    except Exception:
        report["error"] = traceback.format_exc()
        persist()
        unreal.log_error(report["error"])
        finish()


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
state["callback"] = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
