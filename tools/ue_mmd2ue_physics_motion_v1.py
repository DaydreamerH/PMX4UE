"""Root/pelvis displacement stability A/B in MMD2UE. Editor must be closed.

Synthetic 60/30/15 FPS and 100ms hitches; t.MaxFPS 200 is set/read/restored.
Does not claim rendered performance or CharacterMovement root extraction coverage.
"""
import hashlib
import json
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
base = "/Game/Characters/TololoSchool1001/PhysicsSandbox/"
source = base + "Performance/Perf_v3/ABP_Deferred6_60_Walk"
mesh = base + "SK_TololoSchool1001_UpperOnlyCm_v1"
clips = dict(Travel=base + "Animations/M_Neutral_Walk_Loop_F",
             InPlace=base + "Animations/Test_PmxSkirt_InPlace_Walk_v1")
dest = base + "Performance/Motion_v3/"
out = project / "Saved/PMX4UE/PhysicsMotion_v3/report.json"
if out.exists():
    raise RuntimeError("Use a new version, never overwrite experiment reports")
api = unreal.MMD2UEPhysicsMotionTools
variants = dict(Component=("", 1., False, False), BoneBounded=("LowerBody", 0., True, False),
                ComponentDeferred=("", 1., False, True), BoneBoundedDeferred=("LowerBody", 0., True, True))
report = dict(status="in_progress", source=source, mesh=mesh, clips=clips, builds={}, tests={},
    scope="unextracted animated translation + loop wrap; separate continuous component travel; synthetic dt not FPS benchmark",
    collision_policy="reuse original PA and per-shape PMX filters; no garment proxies or changed contacts")
inputs = [source, mesh, *clips.values()]
def digest(path):
    p = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(p.read_bytes()).hexdigest()
def persist():
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
def checked(raw):
    value = json.loads(raw)
    if "error" in value:
        raise RuntimeError(value)
    return value
report["original_hashes"] = {p: digest(p) for p in inputs}
report["animation_settings"] = {tag: {k: str(unreal.load_asset(p).get_editor_property(k))
    for k in ("enable_root_motion", "force_root_lock", "root_motion_root_lock")} for tag,p in clips.items()}
previous_cap = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
try:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS 200")
    report["max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    assert report["max_fps"] == 200
    for name, (bone, damping, bounded, deferred) in variants.items():
        for clip in ("Travel", "InPlace"):
            path = dest + "ABP_" + name + "_" + clip
            result = checked(api.create_motion_variant(source, path, clips[clip], bone, damping, bounded, deferred))
            report["builds"][name + "_" + clip] = result
            for node in result["nodes"]:
                p = node["physics_asset"]
                report["original_hashes"].setdefault(p, digest(p))
    persist()
    cases = [(60., False), (30., False), (15., False), (60., True)]
    for name in variants:
        for clip in ("Travel", "InPlace"):
            # The full matrix isolates animation displacement from actor travel.
            for fps, hitch in cases:
                key = f"{name}_{clip}_{int(fps)}" + ("_hitch" if hitch else "")
                path = report["builds"][name + "_" + clip]["asset"]
                value = checked(api.test_motion(mesh, path, 8., fps, hitch, clip=="InPlace"))
                report["tests"][key] = value
                persist()
                assert value["finite"] and value["filter_errors"] == 0 and value["simulated_bones"] == 444
                unreal.log("MOTION_CASE " + key + " " + json.dumps({k:v for k,v in value.items() if k not in ("samples","nodes")}))
    assert all(digest(p)==h for p,h in report["original_hashes"].items())
    report["status"] = "measured_needs_comparison_and_visual_review"
finally:
    unreal.SystemLibrary.execute_console_command(world, "t.MaxFPS " + str(previous_cap))
    report["restored_max_fps"] = unreal.SystemLibrary.get_console_variable_float_value("t.MaxFPS")
    persist()
