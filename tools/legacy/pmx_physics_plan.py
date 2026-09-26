"""Pure-Python reviewed PMX -> independent native-physics manifests. No UE writes."""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from pmx_physics_settings import resolve_settings


def require(condition, message):
    if not condition:
        raise ValueError(message)


def permits(a, b):
    return bool(a["mask"] & (1 << b["group"])) and bool(b["mask"] & (1 << a["group"]))


def make_plan(inventory, profile, mesh):
    require(inventory["schema"] == "mmd2ue.pmx-physics-inventory.v1", "Invalid inventory schema")
    require(profile["schema"] == "mmd2ue.pmx-physics-profile.v1", "Invalid profile schema")
    require(profile.get("reviewed") is True, "Profile requires mapping/partition review")
    settings = resolve_settings(profile)
    require(profile["source_sha256"] == inventory["source_sha256"], "PMX fingerprint changed; review selectors again")
    require(mesh.get("status") == "inspected" and mesh["mesh"] == profile["mesh"], "Wrong UE mesh inspection")
    require(profile.get("cross_partition_collision") == "none", "Only explicitly independent partitions are supported; use special-requirements prompt")
    require(profile.get("cross_partition_reason"), "Document why cross-partition collisions are disabled")
    variant = profile["variant"]
    require(bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", variant)), "Invalid variant")
    asset_root = profile["asset_root"].rstrip("/")
    require(bool(re.fullmatch(r"/Game/[A-Za-z0-9_/]+", asset_root)), "Invalid asset root")
    bodies = {b["source_index"]: b for b in inventory["bodies"]}
    require(len(bodies) == len(inventory["bodies"]), "Duplicate source rigid ID")
    mesh_bones = {b["name"]: b for b in mesh["bones"]}
    source_bones = {b["name"]: b for b in inventory["bones"]}
    require(len(source_bones) == len(inventory["bones"]), "Duplicate PMX bone names need index-based adapter")
    anchor = profile["measurement_anchor"]
    require(anchor in mesh_bones, "Missing measurement anchor")

    def target(name):
        require(name is not None, "Unbound rigid requires dedicated handling")
        mapped = profile.get("bone_map", {}).get(name)
        if mapped is None and profile.get("allow_same_name_bones") is True:
            mapped = name
        require(mapped in mesh_bones, f"Unmapped/missing UE bone: {name} -> {mapped}")
        require(all(abs(s - 1) < .001 for s in mesh_bones[mapped]["component_scale"]),
                f"Non-unit component scale on physics bone {mapped}; do not change mesh automatically")
        return mapped

    landmarks = []
    for src, dst in profile["landmarks"].items():
        require(src in source_bones and dst in mesh_bones, "Missing landmark")
        landmarks.append(dict(target_bone=dst, position_blender_m=source_bones[src]["position_blender_m"]))
    require(len(landmarks) >= 3, "Need >=3 well-spread anatomical landmarks")
    points = [l["position_blender_m"] for l in landmarks]
    v = [[p[i]-points[0][i] for i in range(3)] for p in points[1:]]
    require(any(sum((a[(i+1)%3]*b[(i+2)%3]-a[(i+2)%3]*b[(i+1)%3])**2 for i in range(3)) > 1e-12
                for a in v for b in v), "Landmarks are collinear")
    ignored = {int(k): reason for k, reason in profile.get("ignored_dynamic", {}).items()}
    require(all(i in bodies and bodies[i]["mode"] != 0 and reason for i, reason in ignored.items()), "Invalid ignored dynamic/reason")
    owners, selected = {}, {}
    for partition in profile["partitions"]:
        name = partition["name"]
        require(bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)) and name not in selected, "Invalid/duplicate partition name")
        require(bool(partition.get("purpose")), f"Explain partition purpose: {name}")
        ids = set(partition.get("dynamic_ids", []))
        require(ids <= bodies.keys(), f"Unknown rigid IDs: {ids - bodies.keys()}")
        if partition.get("dynamic_name_regex"):
            pattern = re.compile(partition["dynamic_name_regex"])
            ids.update(i for i, b in bodies.items() if b["mode"] != 0 and pattern.fullmatch(b["source_name"]))
        require(ids, f"Empty partition: {name}")
        for i in sorted(ids):
            require(i not in owners and i not in ignored, f"Rigid {i} has multiple owners or is ignored")
            require(bodies[i]["mode"] == 1, f"Rigid {i}: mode {bodies[i]['mode']} needs special handling (only mode 1 dynamics supported)")
            owners[i] = name
        selected[name] = ids
    require(selected, "No simulation partitions")
    dynamic = {i for i, b in bodies.items() if b["mode"] != 0}
    require(set(owners) | set(ignored) == dynamic, f"Unreviewed dynamic rigids: {sorted(dynamic-set(owners)-set(ignored))}")
    dynamic_targets = {i: target(bodies[i]["source_bone"]) for i in owners}
    require(len(set(dynamic_targets.values())) == len(dynamic_targets), "Multiple dynamic rigids drive the same UE bone")
    bone_owner = {bone: owners[i] for i, bone in dynamic_targets.items()}
    for bone, owner in bone_owner.items():
        parent, visited = mesh_bones[bone].get("parent"), set()
        while parent:
            require(parent not in visited and parent in mesh_bones, "Invalid UE hierarchy")
            visited.add(parent)
            require(parent not in bone_owner or bone_owner[parent] == owner,
                    f"Dynamic ancestor {parent} crosses independent partition of {bone}; review dependency")
            parent = mesh_bones[parent].get("parent")
    manifests = []
    conversion = profile["conversion"]
    require(conversion.get("reviewed") is True, "Review Bullet/Chaos conversion approximations")
    for key in ("angular_spring_scale", "joint_damping_ratio"):
        require(math.isfinite(conversion[key]) and conversion[key] >= 0, f"Invalid conversion {key}")
    disabled_cross_pairs = sum(permits(bodies[a], bodies[b]) for a in owners for b in owners
                               if a < b and owners[a] != owners[b])
    for partition in profile["partitions"]:
        name, ids = partition["name"], selected[partition["name"]]
        excluded = {int(k): v for k, v in partition.get("excluded_static", {}).items()}
        require(all(i in bodies and bodies[i]["mode"] == 0 and reason for i, reason in excluded.items()), "Invalid excluded static collider/reason")
        anchors, joints = set(), []
        for j in inventory["joints"]:
            endpoints = {j["source_rigid"], j["target_rigid"]}
            if not endpoints & ids:
                continue
            require(endpoints <= bodies.keys(), f"Joint {j['source_index']} has an unbound endpoint")
            require(j["joint_type"] == 0, f"Joint {j['source_index']} type requires adapter")
            for i in endpoints - ids:
                require(bodies[i]["mode"] == 0, f"Joint {j['source_index']} crosses dynamic partition/ignored rigid; do not silently drop it")
                require(i not in excluded, "Excluded collider is a joint anchor; needs explicit non-colliding anchor adapter")
                anchors.add(i)
            require(j["source_rigid"] != j["target_rigid"], "Self joint unsupported")
            require(all(abs(a+b) < 1e-5 for a, b in zip(j["angular_min_rad"], j["angular_max_rad"])), "Asymmetric angular limits require frame adapter")
            for lo, hi in ((j["linear_min_m"], j["linear_max_m"]), (j["angular_min_rad"], j["angular_max_rad"])):
                require(all(math.isfinite(a) and math.isfinite(b) and a <= b for a, b in zip(lo, hi)), "Invalid joint limits")
            require(all(0 <= a <= math.pi for a in j["angular_max_rad"]), "Angular limit beyond Chaos range")
            require(all(k >= 0 and math.isfinite(k) for k in j["linear_spring"] + j["angular_spring"]), "Invalid spring")
            row = copy.deepcopy(j)
            row.update(kind=name, source_bone=target(bodies[j["source_rigid"]]["source_bone"]),
                       target_bone=target(bodies[j["target_rigid"]]["source_bone"]))
            require(row["source_bone"] != row["target_bone"], "Joint endpoints collapse onto one UE body")
            joints.append(row)
        colliders = {i for i, b in bodies.items() if b["mode"] == 0 and i not in excluded
                     and any(permits(b, bodies[s]) for s in ids)} | anchors
        output = []
        materials = {}
        for i in sorted(ids | colliders):
            b = copy.deepcopy(bodies[i])
            b.update(target_bone=target(b["source_bone"]), kinematic=i not in ids, family=name if i in ids else "Body")
            require(0 <= b["group"] < 16 and 0 <= b["mask"] < 65536, "Invalid PMX group/mask")
            require(b["shape"] in ("sphere", "capsule", "box"), "Unsupported shape")
            size = b["size_blender_m"]
            require(len(size) == 3 and all(math.isfinite(x) and x >= 0 for x in size) and size[0] > 0, "Invalid shape size")
            require(b["shape"] != "box" or min(size) > 0, "Zero box dimension")
            require(b["kinematic"] or math.isfinite(b["mass"]) and b["mass"] > 0, "Dynamic rigid needs positive mass")
            require(all(0 <= b[k] <= 1 for k in ("linear_attenuation", "angular_attenuation", "restitution")) and b["friction"] >= 0, "Invalid attenuation/material")
            if b["kinematic"]:
                require(b["target_bone"] not in set(dynamic_targets.values()), "Kinematic collider aliases a dynamic bone")
                material = (b["friction"], b["restitution"])
                require(materials.setdefault(b["target_bone"], material) == material, "Same-bone shapes have different materials; native body-material adapter needed")
            output.append(b)
        pairs = set()
        for n, a in enumerate(output):
            for b in output[n+1:]:
                if a["target_bone"] != b["target_bone"] and not (a["kinematic"] and b["kinematic"]) and permits(a, b):
                    pairs.add(tuple(sorted((a["target_bone"], b["target_bone"]))))
        manifests.append(dict(schema="mmd2ue.pmx-full-experiment.v1", source_pmx=inventory["source_pmx"],
            source_sha256=inventory["source_sha256"], source_scale=inventory["source_scale"], mesh=profile["mesh"],
            asset=f"{asset_root}/PA_{name}_{variant}", landmarks=landmarks, bodies=output, joints=joints,
            collision_pairs=sorted(pairs), per_shape_filter=True, conversion=conversion, solver=copy.deepcopy(settings["solver"]),
            summary=dict(dynamic_bodies=len(ids), kinematic_shapes=len(colliders), joints=len(joints),
                         source_anchor_ids=sorted(anchors), body_setups=len({b['target_bone'] for b in output}))))
    return dict(schema="mmd2ue.pmx-physics-plan.v1", status="ready", mesh=profile["mesh"],
        measurement_anchor=anchor, source_sha256=inventory["source_sha256"],
        profile_sha256=hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        mesh_inspection_sha256=hashlib.sha256(json.dumps(mesh, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        independent_partitions=True, disabled_cross_dynamic_pairs_by_policy=disabled_cross_pairs,
        cross_partition_reason=profile["cross_partition_reason"], ignored_dynamic=ignored,
        animation=profile["test_animation"], rest_blueprint=f"{asset_root}/ABP_Rest_{variant}",
        simulation=settings["simulation"], performance_test=settings["performance_test"],
        performance_controls=dict(synchronous=f"{asset_root}/ABP_SyncControl_{variant}",
                                  no_physics=f"{asset_root}/ABP_NoPhysicsControl_{variant}") if settings["performance_test"]["enabled"] else {},
        walk_blueprint=f"{asset_root}/ABP_Walk_{variant}", partitions=manifests,
        notes=["Native Chaos approximates Bullet limits/springs; not an exact PMX solver",
               "No cross-partition proxies, thickness additions or garment avoidance"])


def main():
    parser = argparse.ArgumentParser()
    for name in ("inventory", "profile", "mesh-inspection", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Plan exists; choose a new output path")
    try:
        result = make_plan(*(json.loads(p.read_text(encoding="utf-8")) for p in
                             (args.inventory, args.profile, args.mesh_inspection)))
    except (ValueError, KeyError, TypeError) as error:
        result = dict(schema="mmd2ue.pmx-physics-plan.v1", status="blocked", blockers=[str(error)])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(result["status"], str(args.output), result.get("blockers", ""))
    if result["status"] != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
