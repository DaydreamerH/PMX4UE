"""Require an explicit, current upper-limb decision before downstream work.

No bone edits here. Names/weights are evidence, not proof of animation quality.
"""
import hashlib
import json
from pathlib import Path
from tools.legacy.skeleton_review import analyze_audit
from tools.legacy.skeleton_plan import build_plan, verify_postconditions


def require(ok, message):
    if not ok:
        raise ValueError("Skeleton review: " + message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(config, artifact):
    artifact = Path(artifact)
    audit_path = artifact / "skeleton_audit.json"
    decision_path = Path(config["pmx4ue"].get("skeleton_decision") or artifact / "skeleton_decision.json")
    require(audit_path.is_file() and decision_path.is_file(),
            "run skeleton-audit and skeleton-review; complete skeleton_decision.json before import/IK/physics")
    audit, decision = read(audit_path), read(decision_path)
    require(decision.get("schema") == "pmx4ue.skeleton-decision.v1" and decision.get("reviewed") is True,
            "explicit reviewed decision required; preserve is not a review")
    require(decision.get("audit_sha256") == digest(audit_path), "stale audit decision")
    blend = Path(audit.get("blend", ""))
    require(blend.is_file() and decision.get("source_blend_sha256") == digest(blend), "stale source blend")
    identity = audit.get("source_file", {})
    require(identity.get("size") == blend.stat().st_size and identity.get("mtime_ns") == blend.stat().st_mtime_ns,
            "source changed since skeleton-audit; regenerate audit")
    roles = config.get("skeleton", {}).get("roles")
    require(roles and decision.get("roles") == roles, "decision must include the current explicit roles")
    review = analyze_audit(audit, roles)
    clean_goal = config.get("skeleton", {}).get("goal") == "clean_ue_fk"
    require(review["bone_references_checked"] and not review["unscanned_actions"], "incomplete reference/action scan")
    paths = [audit_path, decision_path, blend]
    optimize = []
    for part in ("arms", "shoulders"):
        item = decision.get(part, {})
        if clean_goal and any("intermediate" in row["status"] for row in review[part].values()):
            require(item.get("action") == "optimize",
                    part + ": clean_ue_fk requires actual hierarchy edits, not just IK endpoints or blanket preserve")
        require(item.get("action") in {"preserve", "optimize"} and item.get("reason"), "decide " + part)
        require(all(row["status"] != "unresolved_naming_or_hierarchy" for row in review[part].values()),
                part + " role/hierarchy unresolved; adapt semantic roles first")
        if item["action"] == "optimize":
            optimize.append(part)
        elif any("intermediate" in row["status"] or row.get("helper_bones") for row in review[part].values()):
            refs = item.get("preservation_evidence", [])
            require(refs, part + " has intermediates: provide deformation/constraint review evidence or optimize")
            for ref in refs:
                path = Path(ref.get("path", ""))
                require(path.is_absolute() and path.is_file() and digest(path) == ref.get("sha256"),
                        "missing/stale preservation evidence")
                paths.append(path)
            if part == "shoulders":
                helpers = {name for row in review[part].values() for name in row["helper_bones"]}
                decisions = item.get("helper_decisions", {})
                require(set(decisions) == helpers, "document every retained shoulder helper individually")
                for name, decision_row in decisions.items():
                    require(decision_row.get("action") == "retain" and decision_row.get("reason") and
                            decision_row.get("evidence_path") in [str(p) for p in paths],
                            "retained shoulder helper lacks linked evidence: " + name)
    policy = config["pmx4ue"]["skeleton_policy"]
    require(policy == ("upper-only" if optimize else "preserve"), "policy differs from arm/shoulder decision")
    if optimize:
        require(config["pmx4ue"].get("skeleton_reviewed") is True, "skeleton_reviewed must be true")
        require(bool(config.get("skeleton", {}).get("simplify_shoulders")) == ("shoulders" in optimize),
                "simplify_shoulders differs from decision")
        plan = build_plan(audit, roles, simplify_shoulders="shoulders" in optimize,
                          shoulder_strategy=config.get("skeleton", {}).get("shoulder_strategy", "delete_helpers"))
        require(plan["status"] == "ready", "no executable reviewed optimization: " + str(plan["blockers"]))
        if "arms" not in optimize:
            arm_bones = {roles[s][key] for s in ("left", "right") for key in ("elbow", "wrist")}
            require(not any(op["bone"] in arm_bones for op in plan["operations"]),
                    "planner would also edit arms; review that decision explicitly")
        applied_path, fbx = artifact / "skeleton_apply.json", artifact / "upper_only.fbx"
        plan_path = artifact / "skeleton_plan.json"
        require(plan_path.is_file() and read(plan_path) == plan, "current skeleton-plan differs from decision")
        require(applied_path.is_file() and fbx.is_file(), "complete skeleton-plan and skeleton-apply first")
        applied = read(applied_path)
        require(applied.get("status") == "validated_variant_exported" and
                applied.get("operations") == plan["operations"] and applied.get("weight_groups_unchanged") is True and
                Path(applied.get("source_blend", "")).resolve() == blend.resolve() and
                Path(applied.get("derived_fbx", "")).resolve() == fbx.resolve(), "apply report does not match reviewed plan")
        if "shoulders" in optimize:
            expected = verify_postconditions(plan, applied.get("final_bone_parents", {}))
            require(applied.get("postconditions") == expected, "missing final shoulder cleanup verification")
            if plan.get("shoulder_strategy") == "branch_helpers":
                require(applied.get("compatibility") == plan["compatibility"], "missing UE-FK compatibility scope")
        # Bind the report and FBX to a successful runner execution, not filenames alone.
        records = list((artifact / "runs").glob("*_skeleton-apply.json"))
        valid = []
        for record_path in records:
            record = read(record_path)
            if record.get("status") != "executed_needs_review":
                continue
            inputs, outputs = record.get("input_sha256", {}), record.get("output_sha256", {})
            if (inputs.get(str(blend)) == digest(blend) and inputs.get(str(plan_path)) == digest(plan_path)
                    and outputs.get(str(fbx)) == digest(fbx)
                    and outputs.get(str(applied_path)) == digest(applied_path)):
                valid.append(record_path)
        require(valid, "no current successful skeleton-apply record for derived FBX/report")
        paths += [plan_path, applied_path, fbx, valid[0]]
    return list(map(str, paths))


def verify_import(config, artifact, stage):
    """Prevent downstream profiles silently selecting an older unedited mesh."""
    artifact = Path(artifact)
    build_path = artifact / "ue_build_report.json"
    fbx = Path(config["paths"].get("fbx") or artifact / (config["character"]["id"] + ".fbx"))
    require(build_path.is_file() and fbx.is_file(), "import the selected FBX before downstream stages")
    mesh = read(build_path).get("skeletal_mesh", "").split(".")[0]
    require(mesh.startswith("/Game/"), "build report lacks imported mesh")
    valid = []
    for path in (artifact / "runs").glob("*_ue-build.json"):
        record = read(path)
        if (record.get("status") == "executed_needs_review"
                and record.get("input_sha256", {}).get(str(fbx)) == digest(fbx)
                and record.get("output_sha256", {}).get(str(build_path)) == digest(build_path)):
            valid.append(path)
    require(valid, "no build record links selected FBX to imported mesh")
    paths = [fbx, build_path, valid[0]]
    if config.get("skeleton", {}).get("simplify_shoulders"):
        plan_path = artifact / "skeleton_plan.json"
        structure = read(build_path).get("skeleton_structure", {})
        require(structure.get("mesh", "").split('.')[0] == mesh, "missing imported shoulder structure readback")
        expected = verify_postconditions(read(plan_path), structure.get("final_bone_parents", {}))
        require(structure.get("postconditions") == expected, "UE shoulder cleanup did not meet postconditions")
        paths.append(plan_path)
    if stage == "ik":
        profile_path = Path(config["pmx4ue"]["rig_profile"])
        target = read(profile_path).get("target", {}).get("mesh", "")
    elif stage in {"physics-build", "physics-test", "performance"}:
        profile_path = artifact / "physics_plan.json"
        target = read(profile_path).get("mesh", "")
    else:
        # Retarget-pose adapter inspects its native source/target at runtime.
        return list(map(str, paths))
    require(target.split(".")[0] == mesh, "downstream target mesh differs from selected imported mesh")
    return list(map(str, paths + [profile_path]))
