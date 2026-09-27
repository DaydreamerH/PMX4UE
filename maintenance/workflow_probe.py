"""Opt-in MMD2UE regression fixture, not a portable model default.

Run in an owned commandlet. Writes only /Game/PMX4UE/WorkflowProbe/v1 and
Saved/PMX4UE/WorkflowProbe_v1; accepted input assets remain read-only.
"""
import json
import os
from pathlib import Path
import runpy
import sys
import unreal

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "tools"), str(root / "tools/legacy")]
from ue_bridge import inventory, resolve, checked
from ue_animation_export import build
from pmx_physics_plan import make_plan

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert project.name == "MMD2UE", "This case fixture belongs in MMD2UE only"
out = project / "Saved/PMX4UE/WorkflowProbe_v1"
namespace = "/Game/PMX4UE/WorkflowProbe/v1"
out.mkdir(parents=True, exist_ok=True)

def write(name, value):
    with (out/name).open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

stage = os.environ.get("PMX_WORKFLOW_PROBE", "prepare")
if stage == "prepare":
    write("capabilities.json", inventory())
    mesh = "/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1"
    inspection = checked(resolve("physics").inspect_physics_mesh(mesh))
    write("physics_inspect.json", inspection)
    profile = dict(schema="pmx4ue.animation-export.v1", reviewed=True,
        source_mesh="/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin", target_mesh=mesh,
        retargeter="/Game/Characters/TololoSchool1001/Rigs/TPose_v5/RTG_UEFN_To_Tololo_TPose_v5",
        animations=["/Game/Characters/TololoSchool1001/PhysicsSandbox/SourceAnimations/UEFN_Unlocked_M_Neutral_Walk_Loop_F"],
        output_directory=namespace+"/Animations")
    write("animation_profile.json", profile)
    exported = build(profile, namespace, out/"animation_export.json")
    inv = json.loads((project/"Saved/PmxPhysicsWorkflow/Tololo/inventory.json").read_text(encoding="utf-8"))
    old = json.loads((project/"Saved/PmxFullExperiment/independent_v3/manifest.json").read_text(encoding="utf-8"))
    outer = {b["source_index"] for b in old["bodies"] if not b["kinematic"]}
    dynamic = {b["source_index"] for b in inv["bodies"] if b["mode"] == 1}
    profile = dict(schema="mmd2ue.pmx-physics-profile.v1", reviewed=True,
        source_sha256=inv["source_sha256"], mesh=mesh, measurement_anchor="LowerBody",
        variant="v1", asset_root=namespace+"/Physics", test_animation=exported["assets"][0],
        allow_same_name_bones=True, bone_map={}, landmarks={"Center":"Center", "LegD_L":"LegD_L", "LegD_R":"LegD_R", "Head":"Head"},
        cross_partition_collision="none", cross_partition_reason="Existing user-approved independent skirt/outer PMX policy; do not add avoidance",
        partitions=[dict(name="Skirt", purpose="PMX skirt dynamic group", dynamic_ids=sorted(dynamic-outer)),
                    dict(name="Outer", purpose="PMX remaining joint-connected dynamics", dynamic_ids=sorted(outer))],
        conversion=dict(reviewed=True, angular_spring_scale=10000., joint_damping_ratio=.7),
        solver=dict(position_iterations=6, fixed_time_step=1/60, use_linear_joint_solver=False),
        simulation=dict(timing="deferred", accept_one_frame_latency=True, space="base_bone", base_bone="LowerBody",
            world_alpha=1., damping_alpha=1., max_linear_velocity=600., max_linear_acceleration=2000.,
            max_angular_velocity=6., max_angular_acceleration=40.),
        performance_test=dict(enabled=True, seconds=20, repeats=3, viewport_width=1920, viewport_height=1080))
    # Preserve audited Japanese PMX identities, never guess English aliases.
    reviewed = json.loads((project/"Tools/MMDPipeline/characters/TololoSchool1001.pmx-physics.json").read_text(encoding="utf-8"))
    for key in ("asset_root", "variant", "test_animation", "simulation", "performance_test", "solver"):
        reviewed[key] = profile[key]
    profile = reviewed
    write("physics_profile.json", profile)
    write("physics_plan.json", make_plan(inv, profile, inspection))
elif stage in ("build", "test"):
    os.environ.update(PMX_PHYSICS_STAGE=stage, PMX_PHYSICS_OUTPUT=str(out/("physics_"+stage+".json")),
                      PMX_PHYSICS_PLAN=str(out/"physics_plan.json"))
    runpy.run_path(str(root/"tools/legacy/ue_pmx_physics_workflow.py"), run_name="__main__")
else:
    raise ValueError(stage)
