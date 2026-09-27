"""Data-only chest-follow variant of approved Motion_v3 (no simulation benchmark).

Only Chest_L/R body mode changes, in a new PA rebuilt from its manifest. Retain geometry,
PMX shape masks, joints, solver budget and motion-space settings. No user scene
or mesh modification. This intentionally removes independent chest dynamics.
"""
import hashlib
import json
import copy
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
base = "/Game/Characters/TololoSchool1001/PhysicsSandbox/"
mesh = base + "SK_TololoSchool1001_UpperOnlyCm_v1"
clip = base + "Animations/M_Neutral_Walk_Loop_F"
skirt = base + "Performance/Perf_v3/PA_Deferred6_60_Skirt"
outer = base + "Performance/Perf_v3/PA_Deferred6_60_Outer"
baseline = base + "Performance/Motion_v3/ABP_BoneBoundedDeferred_Travel"
dest = base + "Performance/ChestFollow_v1/"
out = project / "Saved/PMX4UE/ChestFollow_v1/build.json"
if out.exists() or unreal.EditorAssetLibrary.does_directory_exist(dest):
    raise RuntimeError("Choose a new version, do not overwrite assets/reports")
targets = {"Chest_L", "Chest_R"}
manifest = json.loads((project / "Saved/PmxFullExperiment/independent_v3/manifest.json").read_text(encoding="utf-8"))
chest_bodies = [b for b in manifest["bodies"] if b["target_bone"] in targets]
chest_joints = [j for j in manifest["joints"] if j["target_bone"] in targets]
assert len(chest_bodies) == len(chest_joints) == 2
for j in chest_joints:
    assert j["source_bone"] == "UpperBody2"
    assert j["linear_min_m"] == j["linear_max_m"]
    assert all(x == 0 for key in ("angular_min_rad", "angular_max_rad", "angular_spring", "linear_spring") for x in j[key])

def digest(path):
    filename = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
    return hashlib.sha256(filename.read_bytes()).hexdigest()

def checked(raw):
    r = json.loads(raw)
    if "error" in r or r.get("status") == "error":
        raise RuntimeError(r)
    return r

source_pa = unreal.load_asset(outer)
inspect = unreal.MMD2UEPhysicsTools.inspect_body_physics_asset
before = checked(inspect(outer))
hashes = {p: digest(p) for p in (outer, skirt, baseline, mesh, clip)}
pa_path = dest + "PA_Outer_ChestFollow"
adapted = copy.deepcopy(manifest)
adapted["asset"] = pa_path
changes = []
for b in adapted["bodies"]:
    name = b["target_bone"]
    if name in targets:
        assert not b["kinematic"]
        b["kinematic"] = True
        changes.append(dict(bone=name, before="simulated", after="kinematic"))
assert len(changes) == 2
comparison = copy.deepcopy(adapted)
comparison["asset"] = manifest["asset"]
for b in comparison["bodies"]:
    if b["target_bone"] in targets:
        b["kinematic"] = False
assert comparison == manifest, "Unexpected geometry, joint, collision or conversion change"
adapted["summary"]["dynamic_bodies"] -= 2
adapted["summary"]["kinematic_shapes"] += 2
adapted["summary"]["dynamic_families"].pop("Chest")
out.parent.mkdir(parents=True, exist_ok=True)
manifest_path = out.parent / "manifest.json"
manifest_path.write_text(json.dumps(adapted, ensure_ascii=False, indent=2), encoding="utf-8")
builder = unreal.MMD2UEPmxSkirtTools
# PhysicsAsset body arrays aren't exposed to Python in this UE build. Reuse
# the compiled manifest importer; no new native module compilation is needed.
physics_build = checked(builder.build_experiment(str(manifest_path)))
assert physics_build["dynamic_bodies"] == 295
pa = unreal.load_asset(pa_path)
pa.set_editor_property("solver_settings", source_pa.get_editor_property("solver_settings"))
assert unreal.EditorAssetLibrary.save_loaded_asset(pa)
after = checked(inspect(pa_path))
for data in (before, after):
    data.pop("asset")
assert before == after, "Saved asset geometry/constraint count differs from original"
assert pa.get_editor_property("solver_settings").export_text() == source_pa.get_editor_property("solver_settings").export_text()
build_bp = dest + "ABP_Build_ChestFollow"
built = checked(builder.build_physics_blueprint(mesh, [skirt, pa_path], clip, build_bp, True))
final_bp = dest + "ABP_ChestFollow_Travel"
motion = checked(unreal.MMD2UEPhysicsMotionTools.create_motion_variant(
    build_bp, final_bp, clip, "LowerBody", 0., True, True))
assert all(n["base_bone"] == "LowerBody" and n["space"] == 2 and n["timing"] == 2 for n in motion["nodes"])
assert all(digest(p) == h for p,h in hashes.items())
report = dict(status="built_static_checks_passed_visual_pending", asset=final_bp, physics_asset=pa_path,
    source_blueprint=baseline, source_physics=outer, source_hashes=hashes, output_hashes={p:digest(p) for p in (pa_path, final_bp)},
    changes=changes, source_chest_bodies=chest_bodies, source_chest_joints=chest_joints,
    comparison="Manifest only changes two kinematic flags plus output metadata; UE geometry/constraint-count audit and solver settings match source. Full serialized joint profiles not directly exposed to Python.",
    physics_build=physics_build, build=built, motion=motion, dynamic_bones_before=444, dynamic_bones_expected_after=442,
    scope="No rendering, simulation or FPS tests while user is gaming; no scene assignment; chest follows animation instead of simulating independently",
    caveat="Intentional mode override from PMX mode1 to kinematic, not an exact Bullet reproduction. Joint locked offset response is no longer simulated for these two bones.")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
unreal.log("CHEST_FOLLOW_BUILT " + final_bp)
# Avoid holding bound native function wrappers through Python-plugin shutdown.
del inspect, source_pa, pa
