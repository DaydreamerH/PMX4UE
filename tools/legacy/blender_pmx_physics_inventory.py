"""Read-only, character-independent PMX inventory; run with Blender/mmd_tools."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mmd_tools.core import pmx
from blender_pmx_skirt_experiment import point, rotation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.exists():
        raise ValueError("Inventory exists; choose a new output path")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    source = Path(config["source"]["pmx"])
    scale = float(config["source"]["scale"])
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("source.scale must be positive meters per PMX unit")
    model = pmx.load(str(source))
    bones = [dict(index=i, name=b.name, parent_index=b.parent,
                  position_blender_m=point(b.location, scale)) for i, b in enumerate(model.bones)]
    bodies = []
    for i, r in enumerate(model.rigids):
        bodies.append(dict(source_index=i, source_name=r.name,
            source_bone=bones[r.bone]["name"] if 0 <= r.bone < len(bones) else None,
            source_bone_index=r.bone, mode=r.mode,
            shape=("sphere", "box", "capsule")[r.type],
            size_blender_m=[float(v)*scale for v in r.size],
            position_blender_m=point(r.location, scale), rotation_blender_xyzw=rotation(r.rotation),
            mass=r.mass, linear_attenuation=r.velocity_attenuation, angular_attenuation=r.rotation_attenuation,
            friction=r.friction, restitution=r.bounce, group=r.collision_group_number, mask=r.collision_group_mask))
    joints = []
    for i, j in enumerate(model.joints):
        joints.append(dict(source_index=i, source_name=j.name, joint_type=j.mode,
            source_rigid=j.src_rigid, target_rigid=j.dest_rigid,
            position_blender_m=point(j.location, scale), rotation_blender_xyzw=rotation(j.rotation),
            linear_min_m=point(j.minimum_location, scale), linear_max_m=point(j.maximum_location, scale),
            angular_min_rad=point(j.maximum_rotation, -1), angular_max_rad=point(j.minimum_rotation, -1),
            linear_spring=point(j.spring_constant), angular_spring=point(j.spring_rotation_constant)))
    result = dict(schema="mmd2ue.pmx-physics-inventory.v1", source_pmx=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), source_scale=scale,
        mask_semantics="mmd_tools allowed bits; both masks must permit the other group",
        bones=bones, bodies=bodies, joints=joints)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"PMX_PHYSICS_INVENTORY {len(bodies)} shapes, {len(joints)} joints -> {args.output}")


if __name__ == "__main__":
    main()
