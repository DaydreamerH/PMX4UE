"""Pure pose planning. Quaternions are XYZW; positions are component-space cm.

UE retarget offsets compose as reference_local_rotation * offset.
Only rotations are edited; local translations/scales and root offset are retained.
"""
import copy
import math


def vector(value, size=3):
    if len(value) != size or any(not math.isfinite(x) for x in value):
        raise ValueError("Expected finite vector of length " + str(size))
    return tuple(float(x) for x in value)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def unit(v):
    v = vector(v, len(v))
    length = math.sqrt(dot(v, v))
    if length < 1e-8:
        raise ValueError("Degenerate direction/quaternion")
    return tuple(x / length for x in v)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def mul(a, b):
    xyz = tuple(a[3]*b[i] + b[3]*a[i] + cross(a, b)[i] for i in range(3))
    return unit((*xyz, a[3]*b[3]-dot(a[:3], b[:3])))


def inv(q):
    return (-q[0], -q[1], -q[2], q[3])


def rotate(q, v):
    uv = cross(q[:3], v)
    uuv = cross(q[:3], uv)
    return tuple(v[i] + 2*(q[3]*uv[i]+uuv[i]) for i in range(3))


def swing(a, b):
    a, b = unit(a), unit(b)
    cosine = max(-1, min(1, dot(a, b)))
    if cosine < -0.999999:
        raise ValueError("180-degree alignment is ambiguous; review axes or base pose")
    return unit((*cross(a, b), 1 + cosine))


def axis_angle(axis, degrees):
    if not math.isfinite(degrees):
        raise ValueError("Non-finite angle")
    half = math.radians(degrees) / 2
    return (*[x * math.sin(half) for x in unit(vector(axis))], math.cos(half))


def forward(bones):
    for i, row in enumerate(bones):
        parent = row["parent"]
        if not isinstance(parent, int) or parent < -1 or parent >= i:
            raise ValueError("Hierarchy must be parent-first with valid indices")
        local = mul(row["ref_rotation"], row["offset"])
        row["local_rotation"] = local
        if parent < 0:
            row["global_rotation"] = local
            row["global_position"] = row["local_position"]
        else:
            p = bones[parent]
            row["global_rotation"] = mul(p["global_rotation"], local)
            t = rotate(p["global_rotation"], row["local_position"])
            row["global_position"] = tuple(x+y for x, y in zip(p["global_position"], t))


def angle(a, b):
    return math.degrees(math.acos(max(-1, min(1, dot(unit(a), unit(b))))))


def posture_metrics(bones, checks):
    """Measure reviewed component-space landmark lines, not bone Euler angles."""
    names = {b["name"]: b for b in bones}
    results = []
    for check in checks:
        start, end = check["start"], check["end"]
        if start not in names or end not in names or start == end:
            raise ValueError("Posture landmarks must be distinct existing bones")
        up = unit(vector(check["up_axis"]))
        delta = sub(names[end]["global_position"], names[start]["global_position"])
        height = dot(delta, up)
        horizontal = sub(delta, tuple(height*x for x in up))
        limit = check["max_tilt_degrees"]
        if not math.isfinite(limit) or not 0 <= limit <= 180:
            raise ValueError("Invalid posture tilt limit")
        results.append(dict(start=start, end=end, delta_cm=delta,
                            horizontal_cm=math.sqrt(dot(horizontal, horizontal)),
                            tilt_degrees=angle(delta, up), max_tilt_degrees=limit))
    return results


def stance_metrics(bones, alignment):
    names = {b["name"]: b for b in bones}
    legs = alignment["legs"]
    left, up = unit(vector(alignment["left_axis"])), unit(vector(alignment["up_axis"]))
    result = {}
    for index, label in enumerate(("hip", "knee", "ankle")):
        delta = sub(names[legs["left"][index]]["global_position"], names[legs["right"][index]]["global_position"])
        result[label + "_gap_cm"] = dot(delta, left)
    result["ankle_heights_cm"] = {s: dot(names[chain[2]]["global_position"], up) for s, chain in legs.items()}
    result["knee_bend_degrees"] = {s: angle(
        sub(names[c[1]]["global_position"], names[c[0]]["global_position"]),
        sub(names[c[2]]["global_position"], names[c[1]]["global_position"])) for s, c in legs.items()}
    return result


def align_leg_directions(bones, alignment):
    """Match reviewed segment directions; retain lengths, hips and foot world rotations."""
    names = {b["name"]: i for i, b in enumerate(bones)}
    legs, goals = alignment["legs"], alignment["directions"]
    if set(legs) != {"left", "right"} or set(goals) != set(legs):
        raise ValueError("Provide both leg chains and direction pairs")
    if any(len(c) != 3 for c in legs.values()) or any(len(g) != 2 for g in goals.values()):
        raise ValueError("Legs require hip/knee/ankle and two directions")
    landmarks = [n for c in legs.values() for n in c]
    if len(set(landmarks)) != 6 or any(n not in names for n in landmarks):
        raise ValueError("Leg landmarks must be distinct existing bones")
    up, left = unit(vector(alignment["up_axis"])), unit(vector(alignment["left_axis"]))
    if abs(dot(up, left)) > 1e-4:
        raise ValueError("Leg left/up axes must be perpendicular")
    for chain in legs.values():
        for a, b in zip(chain, chain[1:]):
            p = bones[names[b]]["parent"]
            while p >= 0 and p != names[a]:
                p = bones[p]["parent"]
            if p < 0:
                raise ValueError("Leg landmarks must follow hierarchy")
    initial = copy.deepcopy(bones)
    before = stance_metrics(bones, alignment)
    if before["hip_gap_cm"] <= 0:
        raise ValueError("Leg left axis conflicts with hip landmarks")
    segments, changed = [], set()
    for side, chain in legs.items():
        for (a, b), goal in zip(zip(chain, chain[1:]), goals[side]):
            desired = unit(vector(goal))
            if dot(desired, up) >= -0.5:
                raise ValueError("Neutral standing leg directions must point down")
            row, child = bones[names[a]], bones[names[b]]
            direction = sub(child["global_position"], row["global_position"])
            world = mul(swing(direction, desired), row["global_rotation"])
            parent_q = bones[row["parent"]]["global_rotation"] if row["parent"] >= 0 else (0, 0, 0, 1)
            row["offset"] = mul(inv(row["ref_rotation"]), mul(inv(parent_q), world))
            changed.add(a)
            forward(bones)
            segments.append(dict(bone=a, child=b, desired=desired, kind="leg",
                before_degrees=angle(sub(initial[names[b]]["global_position"], initial[names[a]]["global_position"]), desired)))
        # Minimal hip swing would otherwise roll the sole inward with the leg.
        ankle = bones[names[chain[2]]]
        parent_q = bones[ankle["parent"]]["global_rotation"]
        ankle["offset"] = mul(inv(ankle["ref_rotation"]), mul(inv(parent_q), initial[names[chain[2]]]["global_rotation"]))
        changed.add(chain[2])
        forward(bones)
    after = stance_metrics(bones, alignment)
    if after["ankle_gap_cm"] <= 0 or after["knee_gap_cm"] <= 0:
        raise ValueError("Leg alignment would cross legs")
    height_limit = alignment.get("max_foot_height_change_cm", 1.0)
    if not math.isfinite(height_limit) or height_limit < 0:
        raise ValueError("Invalid foot height tolerance")
    if any(abs(after["ankle_heights_cm"][s] - before["ankle_heights_cm"][s]) > height_limit for s in legs):
        raise ValueError("Leg alignment moves feet vertically beyond reviewed tolerance")
    for item in segments:
        item["auto_degrees"] = angle(sub(bones[names[item["child"]]]["global_position"], bones[names[item["bone"]]]["global_position"]), item["desired"])
        if item["auto_degrees"] > .05:
            raise ValueError("Leg direction alignment failed")
    return changed, segments, dict(before=before, after=after)


def plan(snapshot, spec):
    """Return all offset changes plus predicted native pose, without UE writes.

    auto_arms=true requires explicit left/right [upper, elbow, wrist] landmarks.
    restore_reference_rotations resets explicit offsets before auto alignment.
    Optional edits append local-axis rotations or replace an offset quaternion.
    Optional posture_checks reject excessive final landmark-line tilt.
    Never changes limb lengths to match another character's proportions.
    """
    bones = copy.deepcopy(snapshot["bones"])
    names = {b["name"]: i for i, b in enumerate(bones)}
    if len(names) != len(bones):
        raise ValueError("Duplicate bone names")
    for b in bones:
        # Runtime retargeting strips scale. Reject legacy scale=100 assets rather
        # than pretending the editor preview and runtime resolve identically.
        for field in ("ref_scale", "local_scale", "global_scale"):
            if any(abs(x-1) > 1e-4 for x in vector(b[field])):
                raise ValueError("Pose editor requires unit bone scale: " + b["name"])
        for field in ("ref_rotation", "offset"):
            b[field] = unit(vector(b[field], 4))
        b["local_position"] = vector(b["local_position"])
    forward(bones)
    # Check that our planning model reproduces UE before computing any edits.
    if any(math.dist(b["global_position"], a["global_position"]) > 0.01
           for a, b in zip(snapshot["bones"], bones)):
        raise ValueError("Native pose differs from planning model; do not write offsets")
    initial = copy.deepcopy(bones)
    changed, segments = set(), []
    # Explicit allowlist, never infer torso roles from model-specific names.
    # Restore BEFORE solving arms: restoring ancestors afterwards invalidates T.
    restored = spec.get("restore_reference_rotations", [])
    if (not isinstance(restored, list) or any(not isinstance(n, str) for n in restored)
            or len(set(restored)) != len(restored) or any(n not in names for n in restored)):
        raise ValueError("restore_reference_rotations requires distinct existing bone names")
    for name in restored:
        bones[names[name]]["offset"] = (0, 0, 0, 1)
        changed.add(name)
    forward(bones)
    if spec.get("auto_arms", False):
        arms = spec["arms"]
        if set(arms) != {"left", "right"} or any(len(v) != 3 for v in arms.values()):
            raise ValueError("Provide left/right upper-arm, elbow and wrist landmarks")
        landmarks = [n for chain in arms.values() for n in chain]
        if len(set(landmarks)) != 6 or any(n not in names for n in landmarks):
            raise ValueError("Arm landmarks must be distinct existing bones")
        for chain in arms.values():
            for ancestor, child in zip(chain, chain[1:]):
                p = bones[names[child]]["parent"]
                while p >= 0 and p != names[ancestor]:
                    p = bones[p]["parent"]
                if p < 0:
                    raise ValueError(f"{ancestor} is not ancestor of {child}")
        up = unit(vector(spec["up_axis"]))
        shoulder_line = sub(bones[names[arms["left"][0]]]["global_position"],
                            bones[names[arms["right"][0]]]["global_position"])
        inferred_left = unit(sub(shoulder_line, tuple(dot(shoulder_line, up)*x for x in up)))
        left = unit(vector(spec.get("left_axis", inferred_left)))
        if abs(dot(left, up)) > 1e-4 or dot(left, inferred_left) < 0.5:
            raise ValueError("Left/up axes conflict with shoulder landmarks")
        for side, chain in arms.items():
            desired = tuple(x * (1 if side == "left" else -1) for x in left)
            for bone, child in zip(chain, chain[1:]):
                i, j = names[bone], names[child]
                row = bones[i]
                direction = sub(bones[j]["global_position"], row["global_position"])
                delta = swing(direction, desired)
                world = mul(delta, row["global_rotation"])
                parent_q = bones[row["parent"]]["global_rotation"] if row["parent"] >= 0 else (0, 0, 0, 1)
                row["offset"] = mul(inv(row["ref_rotation"]), mul(inv(parent_q), world))
                changed.add(bone)
                forward(bones)
                segments.append(dict(bone=bone, child=child, desired=desired,
                                     before_degrees=angle(sub(initial[j]["global_position"], initial[i]["global_position"]), desired)))
        for item in segments:
            item["auto_degrees"] = angle(sub(bones[names[item["child"]]]["global_position"], bones[names[item["bone"]]]["global_position"]), item["desired"])
            if item["auto_degrees"] > 0.05:
                raise ValueError("Auto arm alignment failed")
    stance = None
    if "leg_alignment" in spec:
        leg_changes, leg_segments, stance = align_leg_directions(bones, spec["leg_alignment"])
        changed.update(leg_changes)
        segments.extend(leg_segments)
    for edit in spec.get("edits", []):
        if edit["bone"] not in names:
            raise ValueError("Unknown edit bone: " + edit["bone"])
        row = bones[names[edit["bone"]]]
        if edit.get("mode") == "set_offset":
            row["offset"] = unit(vector(edit["quaternion_xyzw"], 4))
        elif edit.get("mode") == "add_local":
            row["offset"] = mul(row["offset"], axis_angle(edit["axis"], edit["degrees"]))
        else:
            raise ValueError("Edit mode must be set_offset or add_local")
        changed.add(edit["bone"])
        forward(bones)
    if not changed:
        raise ValueError("No auto alignment or bone edits requested")
    for item in segments:
        item["final_degrees"] = angle(sub(bones[names[item["child"]]]["global_position"], bones[names[item["bone"]]]["global_position"]), item["desired"])
    checks = spec.get("posture_checks", [])
    posture = dict(before=posture_metrics(initial, checks), after=posture_metrics(bones, checks))
    if any(row["tilt_degrees"] > row["max_tilt_degrees"] for row in posture["after"]):
        raise ValueError("Final torso/posture tilt exceeds reviewed limit; do not create asset")
    return dict(offsets={b["name"]: b["offset"] for b in bones if b["name"] in changed},
                bones=bones, segments=segments, restored_reference_rotations=restored, posture=posture, stance=stance,
                limitations=["No automatic palm twist or clavicle calibration; leg directions require reviewed goals",
                             "Stance measures joints, not shoe surfaces; foot contact/penetration requires visual review",
                             "Manual edits are applied after auto alignment and may intentionally break T alignment"])


def verify(expected, actual, position_tolerance=0.01, angular_tolerance=0.05):
    if [b["name"] for b in expected["bones"]] != [b["name"] for b in actual["bones"]]:
        raise ValueError("Native skeleton changed")
    position_error = rotation_error = 0.0
    for a, b in zip(expected["bones"], actual["bones"]):
        position_error = max(position_error, math.dist(a["global_position"], b["global_position"]))
        cosine = min(1, abs(dot(unit(a["global_rotation"]), unit(b["global_rotation"]))))
        rotation_error = max(rotation_error, math.degrees(2*math.acos(cosine)))
    if position_error > position_tolerance or rotation_error > angular_tolerance:
        raise ValueError(f"Native readback mismatch: {position_error} cm, {rotation_error} degrees")
    return dict(max_position_error_cm=position_error, max_rotation_error_degrees=rotation_error)
