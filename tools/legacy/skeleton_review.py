"""Read-only retarget readiness review of blender_skeleton_audit.py output.

This identifies common MMD arm/shoulder patterns. It never rewrites a rig:
unknown naming, constraints and animation behaviour require a character review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

IMPORTER_METADATA_GROUPS = {"mmd_edge_scale", "mmd_vertex_order"}


def resolved_roles(configured: dict | None = None) -> dict:
    """Default English MMD names, with per-character overrides when supplied."""
    configured = configured or {}
    roles = {"torso": configured.get("torso", "UpperBody2")}
    for side, suffix in (("left", "L"), ("right", "R")):
        provided = configured.get(side) or {}
        roles[side] = {
            key: provided.get(key, f"{name}_{suffix}")
            for key, name in (
                ("shoulder_pre", "ShoulderP"), ("shoulder", "Shoulder"),
                ("shoulder_post", "ShoulderC"), ("upper_arm", "Arm"),
                ("upper_twist", "ArmTwist"), ("elbow", "Elbow"),
                ("forearm_twist", "HandTwist"), ("wrist", "Wrist"),
            )
        }
        rehome = provided.get("rehome_before_delete") or {}
        if not isinstance(rehome, dict) or not all(isinstance(name, str) and isinstance(parent, str)
                                                    for name, parent in rehome.items()):
            raise ValueError(f"{side}.rehome_before_delete must map bone names to bone names")
        roles[side]["rehome_before_delete"] = rehome
        for key in ("upper_twist_branches", "forearm_twist_branches", "shoulder_helpers"):
            values = provided.get(key) or []
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"{side}.{key} must be a list of bone names")
            roles[side][key] = values
    return roles


def _path(bones: dict[str, dict], start: str, end: str) -> list[str] | None:
    if start not in bones or end not in bones:
        return None
    path = []
    current = end
    visited = set()
    while current and current not in visited:
        visited.add(current)
        path.append(current)
        if current == start:
            return list(reversed(path))
        current = bones.get(current, {}).get("parent")
    return None


def _weighted(bone: dict) -> bool:
    return float((bone.get("weight") or {}).get("sum") or 0) > 1e-8


def analyze_audit(audit: dict, configured_roles: dict | None = None) -> dict:
    bones = {bone["name"]: bone for bone in audit.get("bones", [])}
    roles = resolved_roles(configured_roles)
    arms = {}
    shoulders = {}
    issues = []
    for side in ("left", "right"):
        names = roles[side]
        arm, elbow, wrist = (names[part] for part in ("upper_arm", "elbow", "wrist"))
        path = _path(bones, arm, wrist)
        expected = [arm, elbow, wrist]
        if path is None or elbow not in path:
            state = "unresolved_naming_or_hierarchy"
            issues.append(f"{side}: cannot establish Arm -> Elbow -> Wrist; inspect names and hierarchy")
        elif path == expected:
            state = "direct_three_joint_chain"
        else:
            state = "intermediate_bones_in_main_chain"
            issues.append(f"{side}: main arm chain contains intermediate bones: {path}")
        arms[side] = {"status": state, "main_chain": path, "expected_chain": expected}

        shoulder = names["shoulder"]
        shoulder_path = _path(bones, roles["torso"], arm)
        helpers = sorted({name for name in [names["shoulder_pre"], names["shoulder_post"], *names["shoulder_helpers"]] if name in bones})
        weighted_helpers = [name for name in helpers if _weighted(bones[name])]
        if shoulder_path is None or shoulder not in shoulder_path:
            shoulder_state = "unresolved_naming_or_hierarchy"
            issues.append(f"{side}: cannot establish torso -> shoulder -> upper arm")
        elif shoulder_path == [roles["torso"], shoulder, arm]:
            shoulder_state = "residual_shoulder_helpers" if helpers else "direct_single_shoulder_chain"
            if helpers:
                issues.append(f"{side}: direct main chain still has shoulder helpers: {helpers}")
        else:
            shoulder_state = "intermediate_bones_in_shoulder_chain"
            issues.append(f"{side}: shoulder chain contains intermediate bones: {shoulder_path}")
        if weighted_helpers:
            issues.append(f"{side}: shoulder helpers carry vertex weights; do not delete: {weighted_helpers}")
        shoulders[side] = {
            "status": shoulder_state,
            "main_chain": shoulder_path,
            "helper_bones": helpers,
            "weighted_helpers": weighted_helpers,
            "unweighted_helpers_are_not_deletion_approval": True,
        }

    # Only known importer metadata is ignored; an arbitrary mmd_* group may
    # still be an animation weight and must remain visible for review.
    unmatched = [name for name in (audit.get("unmatched_weight_groups") or []) if name not in IMPORTER_METADATA_GROUPS]
    if unmatched:
        issues.append(f"weight groups without bones: {unmatched}")
    ready = all(item["status"] == "direct_three_joint_chain" for item in arms.values()) and all(
        item["status"] == "direct_single_shoulder_chain" for item in shoulders.values()
    ) and not unmatched
    return {
        "schema": "mmd2ue.skeleton-review.v1",
        "source_audit": audit.get("blend"),
        "roles": roles,
        "retarget_structure": "direct_chain_candidate" if ready else "manual_review_required",
        "arms": arms,
        "shoulders": shoulders,
        "ue_fk_proposal": {
            "goal": "clean_ue_fk", "shoulder_strategy": "branch_helpers",
            "arms": "optimize" if any("intermediate" in row["status"] for row in arms.values()) else "review_direct_chain",
            "shoulders": "optimize" if any("intermediate" in row["status"] for row in shoulders.values()) else "review_direct_chain",
            "rule": "Weighted twists remain as branches; P/C dependencies do not imply keeping them in the main path. IK endpoints are not hierarchy edits.",
            "scope": "UE FK retargeting only; PMX control animation compatibility is not required. Unknown mappings remain blocked.",
        },
        "issues": issues,
        "ignored_metadata_groups": [name for name in (audit.get("unmatched_weight_groups") or []) if name in IMPORTER_METADATA_GROUPS],
        "bone_references_checked": bool(audit.get("bone_references_checked")),
        "unscanned_actions": audit.get("unscanned_actions") or [],
        "animation_validated": False,
        "note": "Name-based preflight only; pose and animation tests are separate acceptance gates.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    report = analyze_audit(json.loads(args.audit.read_text(encoding="utf-8")), (config.get("skeleton") or {}).get("roles"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "retarget_structure": report["retarget_structure"], "issues": len(report["issues"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
