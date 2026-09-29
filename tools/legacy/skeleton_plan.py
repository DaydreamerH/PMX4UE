"""Create a conservative, reviewable Blender bone-edit plan from an audit.

No assets are modified. The plan is executable only when every requested
change has exact hierarchy, weight and reference evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton_review import IMPORTER_METADATA_GROUPS, _path, _weighted, resolved_roles


def build_plan(audit: dict, configured_roles: dict | None = None, *, simplify_shoulders: bool = False,
               leg_cleanup: dict | None = None, shoulder_strategy: str = "delete_helpers") -> dict:
    roles = resolved_roles(configured_roles)
    bones = {bone["name"]: bone for bone in audit.get("bones", [])}
    operations: list[dict] = []
    blockers: list[str] = []
    notes: list[str] = []
    if shoulder_strategy not in {"delete_helpers", "branch_helpers"}:
        raise ValueError("shoulder_strategy must be delete_helpers or branch_helpers")
    retained_helpers = {roles[s][k] for s in ("left", "right")
                        for k in ("upper_twist", "forearm_twist") if roles[s][k] in bones}
    neutral_controls = set()
    unmatched = [name for name in (audit.get("unmatched_weight_groups") or []) if name not in IMPORTER_METADATA_GROUPS]
    if unmatched:
        blockers.append(f"unmatched weight groups require review: {unmatched}")
    if not audit.get("source_file"):
        blockers.append("audit lacks source blend file identity; rerun skeleton-audit")
    if not audit.get("blend"):
        blockers.append("audit lacks source blend path; rerun skeleton-audit")
    if not audit.get("bone_references_checked"):
        blockers.append("audit lacks bone-reference scan; rerun skeleton-audit")
    if audit.get("unscanned_actions"):
        blockers.append(f"unscanned actions require manual review: {audit['unscanned_actions']}")

    for side in ("left", "right"):
        names = roles[side]
        upper, elbow, wrist = (names[key] for key in ("upper_arm", "elbow", "wrist"))
        for branch_key, parent in (("upper_twist_branches", upper), ("forearm_twist_branches", elbow)):
            for branch in names[branch_key]:
                if branch not in bones or bones[branch].get("parent") != parent:
                    blockers.append(f"{side}: configured twist branch {branch} is missing or not parented to {parent}")
        main_path = _path(bones, upper, wrist)
        direct = [upper, elbow, wrist]
        if main_path == direct:
            notes.append(f"{side}: arm main chain already direct")
        elif main_path and elbow in main_path:
            expected = [upper]
            if names["upper_twist"] in bones:
                expected.append(names["upper_twist"])
            expected.append(elbow)
            if names["forearm_twist"] in bones:
                expected.append(names["forearm_twist"])
            expected.append(wrist)
            if main_path != expected:
                blockers.append(f"{side}: unexpected arm intermediates: {main_path}; expected {expected}")
            else:
                if names["upper_twist"] in main_path:
                    operations.append({"op": "reparent", "bone": elbow,
                                       "expected_parent": names["upper_twist"], "new_parent": upper})
                if names["forearm_twist"] in main_path:
                    operations.append({"op": "reparent", "bone": wrist,
                                       "expected_parent": names["forearm_twist"], "new_parent": elbow})
                notes.append(f"{side}: weighted twist bones remain in the rig as side branches")
        else:
            blockers.append(f"{side}: cannot establish upper arm -> elbow -> wrist: {main_path}")

        if not simplify_shoulders:
            continue
        torso = roles["torso"]
        shoulder = names["shoulder"]
        shoulder_path = _path(bones, torso, upper)
        direct_shoulder = [torso, shoulder, upper]
        if shoulder_path == direct_shoulder:
            notes.append(f"{side}: shoulder main chain already direct")
        pre, post = names["shoulder_pre"], names["shoulder_post"]
        deleted = {name for name in [pre, post, *names["shoulder_helpers"]] if name in bones}
        # Also handle partially simplified chains and helpers left on side branches.
        if not shoulder_path or [name for name in shoulder_path if name not in deleted] != direct_shoulder:
            blockers.append(f"{side}: unexpected shoulder chain: {shoulder_path}")
            continue
        protected = {roles["torso"]} | {roles[s][k] for s in ("left", "right")
                     for k in ("shoulder", "upper_arm", "elbow", "wrist", "upper_twist", "forearm_twist")}
        if deleted & protected:
            blockers.append(f"{side}: shoulder helpers overlap protected deform roles: {sorted(deleted & protected)}")
            continue
        if shoulder_strategy == "branch_helpers":
            # Preserve P/C and all their references; change the deform main path only.
            # This is a UE-FK derivative with P held neutral, NOT a PMX control-rig conversion.
            if names["shoulder_helpers"]:
                blockers.append(f"{side}: extra helper semantics require a branch adapter; map P/C only")
                continue
            if shoulder_path != direct_shoulder:
                if pre not in bones or post not in bones:
                    blockers.append(f"{side}: partial P/C pair requires explicit adaptation")
                    continue
                facts = audit.get("control_facts", {})
                p, c = facts.get(pre, {}), facts.get(post, {})
                append = c.get("append")
                expected_append = dict(source=pre, rotation=True, translation=False, factor=-1.0)
                if (p.get("neutral") is not True or p.get("append") or
                        c.get("neutral") is not True or append not in (None, expected_append)):
                    blockers.append(f"{side}: branch mode requires audited neutral P/C and known C=-P compensation")
                    continue
                forbidden = [ref for ref in audit.get("bone_references", [])
                             if (ref.get("target") in {pre, post} and ref.get("kind") in
                                 {"action_curve", "bone_morph", "driver_path", "driver_target", "driver_target_path"})
                             or (ref.get("owner") == pre and ref.get("kind") in
                                 {"constraint", "armature_constraint_target"})]
                if forbidden:
                    blockers.append(f"{side}: P/C are actively controlled; bake/adapt before UE-FK branching: {forbidden}")
                    continue
                neutral_controls.add(pre)
            retained_helpers.update(deleted)
            for child, parent in ((shoulder, torso), (upper, shoulder)):
                if bones[child].get("parent") != parent:
                    operations.append({"op": "reparent", "bone": child,
                                       "expected_parent": bones[child].get("parent"), "new_parent": parent})
            notes.append(f"{side}: P/C retained off main path; references and attachments retained; UE FK only")
            continue
        weighted = [name for name in deleted if _weighted(bones[name])]
        if weighted:
            blockers.append(f"{side}: shoulder helper carries vertex weights; cannot delete {weighted}")
            continue
        refs = [ref for ref in audit.get("bone_references", []) if ref.get("target") in deleted]
        if refs:
            blockers.append(f"{side}: shoulder helper is referenced by constraint/driver/action/object: {refs}")
            continue
        rehome = names["rehome_before_delete"]
        # Parent pointers are authoritative; do not trust a stale children array.
        extra_children = {name for name, bone in bones.items() if bone.get("parent") in deleted
                          and name not in deleted | {shoulder, upper}}
        if set(rehome) != extra_children:
            blockers.append(f"{side}: explicitly map every extra child of removed shoulder bones: {sorted(extra_children)}")
            continue
        invalid_rehome = [f"{child}->{parent}" for child, parent in rehome.items()
                          if child not in bones or parent not in bones or parent in deleted or parent == child
                          or _path(bones, child, parent) is not None]
        if invalid_rehome:
            blockers.append(f"{side}: invalid rehome mapping: {invalid_rehome}")
            continue
        for child, parent in ((shoulder, torso), (upper, shoulder)):
            if bones[child].get("parent") != parent:
                operations.append({"op": "reparent", "bone": child,
                                   "expected_parent": bones[child].get("parent"), "new_parent": parent})
        for child, parent in sorted(rehome.items()):
            operations.append({"op": "reparent", "bone": child,
                               "expected_parent": bones[child]["parent"], "new_parent": parent})
        pending = set(deleted)
        while pending:
            leaves = sorted(name for name in pending if not any(bones[child].get("parent") == name for child in pending))
            if not leaves:
                blockers.append(f"{side}: cyclic helper hierarchy")
                break
            for name in leaves:
                operations.append({"op": "delete_unweighted_leaf", "bone": name,
                                   "expected_parent": bones[name].get("parent")})
                pending.remove(name)

    if leg_cleanup:
        for side in ("left", "right"):
            spec = leg_cleanup.get(side) or {}
            control = spec.get("control_chain") or []
            deform = spec.get("deform_chain") or []
            rehome = spec.get("rehome") or {}
            helpers = spec.get("remove_helpers") or []
            if len(control) != 3 or len(deform) != 3 or not isinstance(rehome, dict) \
                    or not isinstance(helpers, list) or len(set(control + deform + helpers)) != 6 + len(helpers):
                blockers.append(f"{side}: leg cleanup requires distinct three-bone chains and explicit helpers")
                continue
            missing = [name for name in control + deform + helpers + list(rehome) + list(rehome.values())
                       if name not in bones]
            if missing:
                blockers.append(f"{side}: leg cleanup bones missing: {sorted(set(missing))}")
                continue
            if any(bones[control[i]]["parent"] != control[i - 1] or
                   bones[deform[i]]["parent"] != deform[i - 1] for i in (1, 2)) \
                    or bones[control[0]]["parent"] != bones[deform[0]]["parent"]:
                blockers.append(f"{side}: control/deform leg chains have unexpected hierarchy")
                continue
            to_delete = set(control + helpers)
            weighted = [name for name in to_delete if _weighted(bones[name])]
            refs = [ref for ref in audit.get("bone_references", []) if ref.get("target") in to_delete]
            if weighted or refs:
                blockers.append(f"{side}: cannot remove weighted or referenced leg bones: weights={weighted}, refs={refs}")
                continue
            extra_children = {child for name in control for child in bones[name].get("children", [])
                              if child not in to_delete}
            if set(rehome) != extra_children:
                blockers.append(f"{side}: map every retained control-leg child: expected {sorted(extra_children)}, "
                                f"got {sorted(rehome)}")
                continue
            invalid = [f"{child}->{parent}" for child, parent in rehome.items()
                       if child in to_delete or parent in to_delete or parent == child
                       or _path(bones, child, parent) is not None]
            remaining_helpers = set(helpers)
            helper_order_errors = []
            for name in helpers:
                live_children = set(bones[name].get("children", [])) & remaining_helpers
                foreign_children = set(bones[name].get("children", [])) - to_delete - set(rehome)
                if live_children or foreign_children:
                    helper_order_errors.append(name)
                remaining_helpers.remove(name)
            if invalid or helper_order_errors:
                blockers.append(f"{side}: invalid leg rehome or helper deletion order: "
                                f"{invalid}, {helper_order_errors}")
                continue
            for child, parent in sorted(rehome.items()):
                operations.append({"op": "reparent", "bone": child,
                                   "expected_parent": bones[child]["parent"], "new_parent": parent})
            for name in helpers:
                operations.append({"op": "delete_unweighted_leaf", "bone": name,
                                   "expected_parent": bones[name]["parent"]})
            for name in reversed(control):
                operations.append({"op": "delete_unweighted_leaf", "bone": name,
                                   "expected_parent": bones[name]["parent"]})
            notes.append(f"{side}: removed unweighted control leg; deform chain {deform} retained")

    animated_edits = {op["bone"] for op in operations if op["op"] == "reparent"}
    action_refs = [ref for ref in audit.get("bone_references", [])
                   if ref.get("kind") == "action_curve" and ref.get("target") in animated_edits]
    if action_refs:
        blockers.append(f"actions animate bones to be reparented; review animation before editing: {action_refs}")

    return {
        "schema": "mmd2ue.skeleton-edit-plan.v1",
        "source_blend": audit.get("blend"),
        "source_file": audit.get("source_file"),
        "source_bone_count": len(bones),
        "roles": roles,
        "simplify_shoulders": simplify_shoulders,
        "shoulder_strategy": shoulder_strategy,
        "compatibility": {"target": "ue_fk", "pmx_control_animation_preserved": False,
                          "neutral_controls": sorted(neutral_controls)},
        "leg_cleanup": leg_cleanup or {},
        "status": "blocked" if blockers else ("ready" if operations else "already_direct"),
        "operations": operations if not blockers else [],
        "postconditions": {
            "retained": sorted(retained_helpers),
            "absent": sorted(op["bone"] for op in operations if op["op"] == "delete_unweighted_leaf"),
            "parents": {**{roles[s][k]: roles[s][p] for s in ("left", "right")
                           for k, p in (("elbow", "upper_arm"), ("wrist", "elbow"))},
                        **({roles[s]["shoulder"]: roles["torso"] for s in ("left", "right")} if simplify_shoulders else {}),
                        **({roles[s]["upper_arm"]: roles[s]["shoulder"] for s in ("left", "right")} if simplify_shoulders else {}),
                        **{op["bone"]: op["new_parent"] for op in operations if op["op"] == "reparent"}},
        },
        "blockers": blockers,
        "notes": notes,
        "max_allowed_vertex_delta": 0.0001,
        "max_allowed_bone_matrix_delta": 0.0001,
        "max_allowed_pose_delta": 0.0001,
        "animation_validated": False,
    }


def verify_postconditions(plan, parents):
    conditions = plan.get("postconditions")
    if not conditions:
        raise ValueError("Missing skeleton postconditions; regenerate the plan")
    remaining = set(conditions["absent"]) & set(parents)
    missing = set(conditions.get("retained", [])) - set(parents)
    wrong = {name: {"expected": parent, "actual": parents.get(name)}
             for name, parent in conditions["parents"].items() if name not in parents or parents[name] != parent}
    if remaining or wrong or missing:
        raise ValueError(f"Skeleton postconditions failed: residual bones={sorted(remaining)}, wrong parents={wrong}, missing retained={sorted(missing)}")
    return {"status": "passed", "conditions": conditions}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--simplify-shoulders", action="store_true")
    parser.add_argument("--simplify-legs", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    skeleton = config.get("skeleton") or {}
    if args.simplify_legs and not skeleton.get("leg_cleanup"):
        parser.error("--simplify-legs requires skeleton.leg_cleanup in --config")
    plan = build_plan(
        json.loads(args.audit.read_text(encoding="utf-8")),
        skeleton.get("roles"),
        simplify_shoulders=args.simplify_shoulders or bool(skeleton.get("simplify_shoulders")),
        shoulder_strategy=skeleton.get("shoulder_strategy", "delete_helpers"),
        leg_cleanup=skeleton.get("leg_cleanup") if args.simplify_legs else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": plan["status"],
                      "operations": len(plan["operations"]), "blockers": plan["blockers"]}, ensure_ascii=False))
    return 2 if plan["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
