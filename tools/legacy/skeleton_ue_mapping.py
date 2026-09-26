"""Pure configuration helpers shared by UE skeletal import and retargeting."""

from __future__ import annotations

from skeleton_review import resolved_roles


DEFAULT_TARGET_CHAINS = {
    "Spine": ("UpperBody", "UpperBody2"),
    "Neck": ("Neck", "Neck"),
    "Head": ("Head", "Head"),
    "LeftLeg": ("Leg_L", "Ankle_L"),
    "RightLeg": ("Leg_R", "Ankle_R"),
}


def variant_has_single_shoulder(config: dict, variant: str) -> bool:
    skeleton = config.get("skeleton") or {}
    return bool(skeleton.get("simplify_shoulders")) and variant == skeleton.get("variant")


def target_chains(config: dict, variant: str) -> dict[str, tuple[str, str]]:
    skeleton = config.get("skeleton") or {}
    roles = resolved_roles(skeleton.get("roles"))
    chains = dict(DEFAULT_TARGET_CHAINS)
    for side, label in (("left", "Left"), ("right", "Right")):
        names = roles[side]
        chains[f"{label}Arm"] = (names["upper_arm"], names["wrist"])
        if variant_has_single_shoulder(config, variant):
            chains[f"{label}Shoulder"] = (names["shoulder"], names["shoulder"])
    for name, endpoints in ((skeleton.get("retarget") or {}).get("target_chains") or {}).items():
        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2 or not all(isinstance(part, str) and part for part in endpoints):
            raise ValueError(f"invalid target chain {name}: expected [start_bone, end_bone]")
        chains[name] = tuple(endpoints)
    return chains


def expected_arm_parents(config: dict, variant: str) -> dict[str, str]:
    skeleton = config.get("skeleton") or {}
    roles = resolved_roles(skeleton.get("roles"))
    expected = {}
    for side in ("left", "right"):
        names = roles[side]
        expected[names["elbow"]] = names["upper_arm"]
        expected[names["wrist"]] = names["elbow"]
        if variant_has_single_shoulder(config, variant):
            expected[names["shoulder"]] = roles["torso"]
            expected[names["upper_arm"]] = names["shoulder"]
    return expected
