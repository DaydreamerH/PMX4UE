"""Create unreviewed rig and physics work orders from inventory. Never infer anatomy."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmx4ue import load, read, write
from bone_identity import unique_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    c, _, a = load(args.config)
    inv = read(a / "physics_inventory.json")
    manifest = read(a / "blender_manifest.json")
    bone_map, ambiguous = unique_map(manifest["armature"].get("source_bone_identity", []))
    root = c["paths"]["ue_root"]
    mesh = root + "/Mesh/SK_" + c["character"]["id"]
    rig_path, physics_path = (Path(c["pmx4ue"][k]) for k in ("rig_profile", "physics_profile"))
    if rig_path.exists() or physics_path.exists():
        raise ValueError("Profiles already exist; edit/review them, do not overwrite")
    write(rig_path, dict(schema="pmx4ue.rig-profile.v1", reviewed=False,
        target=dict(mesh=mesh, asset=root + "/Rigs/IK_Target", pelvis="", chains={}),
        source=None, retargeter=root + "/Rigs/RTG_SourceToTarget"))
    write(physics_path, dict(schema="mmd2ue.pmx-physics-profile.v1", reviewed=False,
        source_sha256=inv["source_sha256"], mesh=mesh, measurement_anchor="", variant="Physics_v1",
        asset_root=root + "/Physics", rest_only=True, test_animation="", allow_same_name_bones=False, bone_map=bone_map, landmarks={},
        cross_partition_collision="none", cross_partition_reason="", partitions=[], ignored_dynamic={},
        conversion=dict(reviewed=False, angular_spring_scale=10000, joint_damping_ratio=.7),
        solver=dict(position_iterations=8, fixed_time_step=1/60, use_linear_joint_solver=False),
        simulation=dict(timing="synchronous", accept_one_frame_latency=False, space="component", base_bone=""),
        performance_test=dict(enabled=False, max_fps=200, seconds=60, repeats=3, viewport_width=1920, viewport_height=1080,
                              minimum_average_fps=70, maximum_p99_ms=1000/60),
        agent_review=dict(ambiguous_source_bone_names=ambiguous,
                          mapping_note="From importer metadata, must reconcile with skeleton optimization and UE inspection; no name guessing",
                          unassigned_dynamic_ids=[b["source_index"] for b in inv["bodies"] if b["mode"] != 0],
                          note="Candidate numeric settings only; review anatomy, source masks and conversion before approval.")))
    print(rig_path, physics_path)


if __name__ == "__main__":
    main()
