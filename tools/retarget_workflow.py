"""Agent-reviewed humanoid pose contracts. Pure Python; no Unreal dependency.

Model semantics are reusable across pairs. Pair decisions are tied to an exact
inventory. This module never guesses deformation bones from names or edits rigs.
"""
import copy
import hashlib
import json
import math
import re

try:
    from .retarget_pose_math import plan, sub, unit, dot, vector
except ImportError:
    from retarget_pose_math import plan, sub, unit, dot, vector

SIDES = ("source", "target")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def asset_path(path):
    require(isinstance(path, str) and re.fullmatch(r"/Game/\w+(?:/\w+)*(?:\.\w+)?", path), "Expected /Game/ asset path")
    return path.split(".")[0]


def reference_identity(snapshot):
    """Independent of current pose/role as Source or Target; sensitive to bind data."""
    return fingerprint(dict(mesh=asset_path(snapshot["mesh"]), bones=[
        {k: b[k] for k in ("name", "parent", "ref_position", "ref_rotation", "ref_scale")}
        for b in snapshot["bones"]]))


def validate_snapshot(snapshot):
    require(snapshot.get("status") == "inspected", "Need native inspected pose")
    bones = snapshot["bones"]
    require(bool(bones), "Empty skeleton")
    require(len({b["name"] for b in bones}) == len(bones), "Duplicate bones")
    require(sum(b["parent"] == -1 for b in bones) == 1, "Expected a single rooted skeleton")
    for i, b in enumerate(bones):
        require(type(b["parent"]) is int and -1 <= b["parent"] < i, "Invalid parent-first hierarchy")
        for k in ("ref_position", "local_position", "global_position", "ref_scale", "local_scale", "global_scale"):
            vector(b[k])
        for k in ("ref_rotation", "offset", "global_rotation"):
            unit(vector(b[k], 4))
    # Use the existing native-consistency and scale gates even for a draft.
    plan(snapshot, {"restore_reference_rotations": [bones[0]["name"]]})


def validate_inventory(inventory):
    require(inventory.get("schema") == "pmx4ue.pose-inventory.v1", "Unknown inventory schema")
    asset_path(inventory["retargeter"])
    require(set(inventory["sides"]) == set(SIDES), "Inventory needs actual Source and Target")
    for side in SIDES:
        validate_snapshot(inventory["sides"][side]["snapshot"])


def draft_model(inventory, side, model_id):
    validate_inventory(inventory)
    snapshot = inventory["sides"][side]["snapshot"]
    return dict(schema="pmx4ue.pose-model.v1", model_id=model_id, mesh=snapshot["mesh"],
        reference_sha256=reference_identity(snapshot),
        basis=dict(left=None, forward=None, up=None),
        roles=dict(pelvis=None, spine=None, arms=dict(left=None, right=None), legs=dict(left=None, right=None)),
        spine_chain=None, limb_chains={k: dict(left=None, right=None) for k in ("arms", "legs")},
        review=dict(by="", rationale="", evidence=[], unresolved=["Identify deformation roles and body axes"]),
        role_evidence={k: [] for k in ("pelvis", "spine", "arms", "legs", "basis")},
        notes="Fill from actual hierarchy/positions/weights/views; chain names are clues, not proof.")


def draft_pair(inventory):
    validate_inventory(inventory)
    return dict(schema="pmx4ue.pose-pair.v1", inventory_sha256=fingerprint(inventory),
        retargeter=inventory["retargeter"], namespace="", output_retargeter="",
        review=dict(by="", rationale="", evidence=[], unresolved=["Choose neutral stance and review chains"]),
        stance=dict(mode="match", reference_side="target", max_foot_height_change_cm=1.0),
        sides={s: dict(pose_name="TPose_"+s.title()+"_v1", restore_reference_rotations=[],
                       posture_checks=[], pre_edits=[], edits=[], edit_reasons={}) for s in SIDES},
        max_segment_error_degrees=0.5,
        test_animations=[],
        visual_checks=["front_arms_and_stance", "side_torso_and_knees", "palms_and_shoulders", "soles"],
        animation_checks=["idle", "walk", "turn_or_stop"])


def reviewed(review, label):
    require(isinstance(review, dict) and all(isinstance(review.get(k), str) and review[k].strip()
            for k in ("by", "rationale")), label + ": reviewer and rationale required")
    require(isinstance(review.get("evidence"), list) and review["evidence"]
            and all(isinstance(e, str) and e.strip() for e in review["evidence"]), label + ": evidence required")
    require(review.get("unresolved") == [], label + ": unresolved decisions")


def ancestor(bones, names, a, b):
    i = names[b]
    while i >= 0:
        if bones[i]["name"] == a:
            return True
        i = bones[i]["parent"]
    return False


def chain_path(bones, names, start, end):
    require(start in names and end in names, "Chain endpoint missing")
    require(ancestor(bones, names, start, end), "Chain endpoints are not an ancestor path")
    result, i = [], names[end]
    while True:
        result.append(bones[i]["name"])
        if bones[i]["name"] == start:
            return result[::-1]
        i = bones[i]["parent"]


def validate_model(model, side_data):
    snapshot = side_data["snapshot"]
    require(model.get("schema") == "pmx4ue.pose-model.v1", "Unknown model schema")
    require(model["reference_sha256"] == reference_identity(snapshot), "Stale model reference/bind data")
    require(asset_path(model["mesh"]) == asset_path(snapshot["mesh"]), "Model mesh mismatch")
    reviewed(model["review"], model["model_id"])
    for role in ("pelvis", "spine", "arms", "legs", "basis"):
        evidence = model.get("role_evidence", {}).get(role)
        require(isinstance(evidence, list) and evidence and all(isinstance(e, str) and e.strip() for e in evidence),
                "Missing role evidence: " + role)
    basis = {k: unit(vector(model["basis"][k])) for k in ("left", "forward", "up")}
    require(all(abs(dot(basis[a], basis[b])) < 1e-4 for a,b in
                (("left", "up"), ("left", "forward"), ("forward", "up"))), "Body axes must be orthogonal")
    bones = snapshot["bones"]
    names = {b["name"]: i for i,b in enumerate(bones)}
    roles = model["roles"]
    pelvis = roles["pelvis"]
    require(pelvis in names and side_data["pelvis"] == pelvis, "Rig pelvis differs from reviewed role")
    limbs = []
    for kind in ("arms", "legs"):
        require(set(roles[kind]) == {"left", "right"}, "Both limb sides required")
        for limb_side, chain in roles[kind].items():
            require(isinstance(chain, list) and len(chain) == 3 and len(set(chain)) == 3, "Three limb landmarks required")
            for a,b in zip(chain, chain[1:]):
                chain_path(bones, names, a,b)
            chain_name = model["limb_chains"][kind][limb_side]
            require(side_data["chains"].get(chain_name) == [chain[0], chain[-1]],
                    "Rig limb endpoints differ from reviewed deformation landmarks")
            limbs += chain
    require(len(set(limbs)) == 12, "Limb roles overlap")
    spine = roles["spine"]
    require(isinstance(spine, list) and len(spine) == 2, "Spine needs start/end")
    path = chain_path(bones, names, *spine)
    require(side_data["chains"].get(model["spine_chain"]) == spine, "Rig Spine endpoints differ; repair isolated Rig before posing")
    hips = [c[0] for c in roles["legs"].values()]
    require(all(ancestor(bones, names, pelvis, n) for n in hips + [spine[0]]), "Pelvis must drive upper and lower body")
    require(not any(ancestor(bones, names, p, hip) for p in path for hip in hips),
            "Spine path includes a leg ancestor; review chain semantics, not mesh hierarchy")
    for kind in ("arms", "legs"):
        l,r = (bones[names[roles[kind][s][0]]]["global_position"] for s in ("left", "right"))
        require(dot(sub(l,r), basis["left"]) > 0, "Left axis conflicts with limb positions")
    return basis


def transfer_direction(direction, source_basis, target_basis):
    return unit(tuple(sum(dot(direction, source_basis[k])*target_basis[k][i]
                          for k in ("left", "forward", "up")) for i in range(3)))


def compile_pair(inventory, models, pair):
    """Generate legacy executable pose profile and predictions, no asset writes."""
    validate_inventory(inventory)
    require(pair.get("schema") == "pmx4ue.pose-pair.v1", "Unknown pair schema")
    require(pair["inventory_sha256"] == fingerprint(inventory), "Stale pair inventory")
    require(asset_path(pair["retargeter"]) == asset_path(inventory["retargeter"]), "Wrong retargeter")
    reviewed(pair["review"], "pair")
    for key in ("visual_checks", "animation_checks"):
        require(isinstance(pair[key], list) and pair[key] and all(isinstance(k, str) and k.strip() for k in pair[key])
                and len(set(pair[key])) == len(pair[key]), "Nonempty distinct acceptance checks required")
    limit = pair["max_segment_error_degrees"]
    require(isinstance(limit, (int, float)) and math.isfinite(limit) and 0 < limit <= 5,
            "Review a segment error limit in (0, 5] degrees")
    require(set(models) == set(SIDES) and set(pair["sides"]) == set(SIDES), "Normalize both actual sides")
    namespace, destination = asset_path(pair["namespace"]), asset_path(pair["output_retargeter"])
    require(destination.startswith(namespace.rstrip("/")+"/") and destination != asset_path(pair["retargeter"]),
            "Output must be independent and inside namespace")
    basis, specs, prepared = {}, {}, {}
    for side in SIDES:
        data, model = inventory["sides"][side], models[side]
        basis[side] = validate_model(model, data)
        user = pair["sides"][side]
        require(set(user) <= {"pose_name", "restore_reference_rotations", "posture_checks", "pre_edits", "edits", "edit_reasons"},
                "Unsupported side decision; extend adapter explicitly")
        require(bool(user["posture_checks"]), "Review at least one torso posture check for each side")
        edits = user.get("edits", [])
        changed = set(user.get("restore_reference_rotations", [])) | {e["bone"] for e in edits + user.get("pre_edits", [])}
        reasons = user.get("edit_reasons", {})
        require(all(isinstance(reasons.get(n), str) and reasons[n].strip() for n in changed), "Each explicit edit/reset needs a reason")
        specs[side] = dict(pose_name=user["pose_name"], auto_arms=True,
            arms=copy.deepcopy(model["roles"]["arms"]), up_axis=list(basis[side]["up"]), left_axis=list(basis[side]["left"]),
            restore_reference_rotations=user.get("restore_reference_rotations", []),
            posture_checks=user["posture_checks"], pre_edits=user.get("pre_edits", []), edits=edits)
        # Stance reference comes from normalized base, not old compensating edits.
        base_spec = {**specs[side], "edits": [], "posture_checks": []}
        prepared[side] = plan(data["snapshot"], base_spec)
    for role, limb_side in [("spine", None)] + [(k, s) for k in ("arms", "legs") for s in ("left", "right")]:
        chain_names = {s: models[s]["spine_chain"] if role == "spine" else models[s]["limb_chains"][role][limb_side]
                       for s in SIDES}
        require(inventory.get("mappings", {}).get(chain_names["target"]) == chain_names["source"],
                "Retarget chain mapping differs from reviewed roles: " + role)
    stance = pair["stance"]
    require(stance["mode"] in ("match", "preserve"), "Unknown stance policy")
    if stance["mode"] == "match":
        ref = stance["reference_side"]
        require(ref in SIDES, "Choose reviewed source or target stance")
        positions = {b["name"]: b["global_position"] for b in prepared[ref]["bones"]}
        directions = {s: [unit(sub(positions[b], positions[a])) for a,b in zip(c,c[1:])]
                      for s,c in models[ref]["roles"]["legs"].items()}
        for side in SIDES:
            specs[side]["leg_alignment"] = dict(legs=models[side]["roles"]["legs"],
                directions={s: [transfer_direction(d, basis[ref], basis[side]) for d in ds] for s,ds in directions.items()},
                left_axis=list(basis[side]["left"]), up_axis=list(basis[side]["up"]),
                max_foot_height_change_cm=stance["max_foot_height_change_cm"])
    predictions = {s: plan(inventory["sides"][s]["snapshot"], specs[s]) for s in SIDES}
    require(all(item["final_degrees"] <= limit for p in predictions.values() for item in p["segments"]),
            "Final manual edits broke reviewed limb directions; use pre_edits for torso corrections")
    warnings = ["Joint directions are not sole/skin contact evidence; palm twist needs agent visual review",
                "No chain or Root Motion op repair is performed; changes require a new inventory and pair"]
    for side in SIDES:
        expected = predictions[side]
        names = {b["name"]: i for i,b in enumerate(expected["bones"])}
        hips = [c[0] for c in models[side]["roles"]["legs"].values()]
        changed = set(expected["offsets"])
        ancestor_changes = sorted(n for n in changed if any(ancestor(expected["bones"], names, n,h) and n!=h for h in hips))
        if ancestor_changes:
            warnings.append(side + ": shared lower-body ancestors edited; review retained descendant offsets: " + ", ".join(ancestor_changes))
    profile = dict(reviewed=True, retargeter=pair["retargeter"], output_retargeter=destination, sides=specs,
        agent_contract=dict(schema="pmx4ue.pose-contract.v1", inventory_sha256=fingerprint(inventory),
                            models=copy.deepcopy(models), pair=copy.deepcopy(pair)))
    return dict(schema="pmx4ue.pose-plan.v1", status="planned_needs_native_visual_animation_review",
        profile=profile, predictions=predictions, warnings=warnings,
        acceptance=dict(native_readback="pending", fresh_reload="pending",
            views={k: dict(status="pending", evidence=[]) for k in pair["visual_checks"]},
            animations={k: dict(status="pending", evidence=[]) for k in pair["animation_checks"]},
            requested_clips=pair["test_animations"], user_review="pending"))
