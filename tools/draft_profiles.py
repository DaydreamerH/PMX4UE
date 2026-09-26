"""Create unreviewed rig and physics work orders from inventory. Never infer anatomy."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmx4ue import load, read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    c, _, a = load(args.config)
    inv = read(a / "physics_inventory.json")
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
        asset_root=root + "/Physics", test_animation="", allow_same_name_bones=False, bone_map={}, landmarks={},
        cross_partition_collision="none", cross_partition_reason="", partitions=[], ignored_dynamic={},
        conversion=dict(reviewed=False, angular_spring_scale=10000, joint_damping_ratio=.7),
        solver=dict(position_iterations=8, fixed_time_step=1/60, use_linear_joint_solver=False),
        simulation=dict(timing="synchronous", accept_one_frame_latency=False),
        performance_test=dict(enabled=True, max_fps=200, seconds=60, repeats=3,
                              minimum_average_fps=70, maximum_p99_ms=1000/60),
        agent_review=dict(unassigned_dynamic_ids=[b["source_index"] for b in inv["bodies"] if b["mode"] != 0],
                          note="Candidate numeric settings only; review anatomy, source masks and conversion before approval.")))
    print(rig_path, physics_path)


if __name__ == "__main__":
    main()
