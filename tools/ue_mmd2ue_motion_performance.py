"""Independent solver-cost experiment, preserving Motion_v3 motion/filter policy.

Run in an owned MMD2UE commandlet. Never overwrites assets or existing reports.
Synthetic timings are NOT game FPS; follow with rendered PIE benchmark.
"""
import hashlib
import json
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
base = "/Game/Characters/TololoSchool1001/PhysicsSandbox/"
mesh = base + "SK_TololoSchool1001_UpperOnlyCm_v1"
clip = base + "Animations/M_Neutral_Walk_Loop_F"
baseline = base + "Performance/Motion_v3/ABP_BoneBoundedDeferred_Travel"
sources = [base + "Performance/Perf_v3/PA_Deferred6_60_" + p for p in ("Skirt", "Outer")]
dest = base + "Performance/MotionPerf_v1/"
out = project / "Saved/PMX4UE/MotionPerf_v1/numerical.json"
if out.exists() or unreal.EditorAssetLibrary.does_directory_exist(dest):
    raise RuntimeError("Choose a fresh experiment namespace")
api = unreal.MMD2UEPhysicsMotionTools
builder = unreal.MMD2UEPmxSkirtTools
report = dict(status="in_progress", baseline=baseline, mesh=mesh, clip=clip, builds={}, tests={},
              policy="Only PA solver iteration counts change. Preserve all bodies, joints, PMX masks and Motion_v3 follow behavior.",
              timing_scope="Synthetic animation submission/wait, not rendered FPS")

def checked(raw):
    r = json.loads(raw)
    if "error" in r or r.get("status") == "error":
        raise RuntimeError(r)
    return r

def digest(path):
    p = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(p.read_bytes()).hexdigest()

def persist():
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

report["source_hashes"] = {p: digest(p) for p in [mesh, clip, baseline, *sources]}
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
previous = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
try:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS 200")
    report["max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    assert report["max_fps"] == 200
    for name, iterations in dict(Skirt6Outer4=(6, 4), Both4=(4, 4), Both3=(3, 3)).items():
        assets = []
        settings = []
        for part, source, count in zip(("Skirt", "Outer"), sources, iterations):
            path = dest + "PA_" + name + "_" + part
            pa = unreal.EditorAssetLibrary.duplicate_asset(source, path)
            assert pa
            solver = pa.get_editor_property("solver_settings")
            assert abs(solver.get_editor_property("fixed_time_step") - 1/60) < 1e-6
            assert not solver.get_editor_property("use_linear_joint_solver")
            solver.set_editor_property("position_iterations", count)
            pa.set_editor_property("solver_settings", solver)
            assert unreal.EditorAssetLibrary.save_loaded_asset(pa)
            settings.append(dict(asset=path, position_iterations=count, fixed_step=1/60))
            assets.append(path)
        intermediate = dest + "ABP_Build_" + name
        checked(builder.build_physics_blueprint(mesh, assets, clip, intermediate, True))
        built = checked(api.create_motion_variant(intermediate, dest + "ABP_" + name + "_Travel",
                                                  clip, "LowerBody", 0., True, True))
        report["builds"][name] = dict(**built, solvers=settings)
    no_physics = dest + "ABP_NoPhysics_Travel"
    checked(builder.build_physics_blueprint(mesh, [], clip, no_physics, False))
    report["no_physics"] = no_physics
    persist()
    for name, path in [("Baseline6", baseline)] + [(k, v["asset"]) for k,v in report["builds"].items()]:
        for fps, hitches in [(60., False), (15., False), (60., True)]:
            tag = name + "_" + str(int(fps)) + ("_hitch" if hitches else "")
            r = checked(api.test_motion(mesh, path, 12., fps, hitches, False))
            report["tests"][tag] = r
            persist()
            assert r["finite"] and r["filter_errors"] == 0
            assert r["simulated_bones"] == 444 and r["filters_applied"] == 330
            assert r["seconds_completed"] > 11.99 and r["max_skirt_radius_cm"] < 60
            assert all(n["base_bone"] == "LowerBody" and n["space"] == 2 and n["timing"] == 2 for n in r["nodes"])
            unreal.log("MOTION_PERF " + tag + " " + str(r["evaluation_mean_ms"]))
    assert all(digest(p) == h for p,h in report["source_hashes"].items())
    report["status"] = "numerically_measured_needs_rendered_and_visual_review"
finally:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS " + str(previous))
    report["restored_max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    persist()
