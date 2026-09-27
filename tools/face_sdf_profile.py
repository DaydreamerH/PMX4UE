"""Model-specific, agent-reviewed face basis. No Unreal dependency."""
import math
import re


def validate_profile(profile, namespace):
    if profile.get("version") != 1 or profile.get("reviewed") is not True:
        raise ValueError("Review the head bone, face slot and SDF hemisphere axes first")
    if not str(profile.get("review_evidence", "")).strip():
        raise ValueError("Record review_evidence, not just a review flag")
    path_pattern = r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+"
    for key in ("mesh", "destination"):
        if not re.fullmatch(path_pattern, str(profile.get(key, ""))):
            raise ValueError(f"{key} must be a /Game package path (no object suffix)")
    if not profile["destination"].startswith(namespace.rstrip("/") + "/"):
        raise ValueError("Destination must be inside the work order namespace")
    abp = profile.get("animation_blueprint")
    if abp and not re.fullmatch(path_pattern, str(abp)):
        raise ValueError("animation_blueprint must be a /Game package path")
    for key in ("head_bone", "face_slot"):
        value = profile.get(key)
        if not isinstance(value, str) or not value.strip() or value.lower() == "none":
            raise ValueError(f"Provide the actual {key}; no model-specific default")
    if profile.get("provider") not in ("mmd2ue", "pmx4ue"):
        raise ValueError("Select the compiled runtime provider: mmd2ue or pmx4ue")
    result = dict(profile)
    for key in ("reference_forward", "reference_left"):
        value = profile.get(key)
        if not isinstance(value, list) or len(value) != 3 or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
            raise ValueError(f"{key} must contain three finite numbers")
        length = math.hypot(*value)
        if not math.isfinite(length) or length < 1e-8:
            raise ValueError(f"{key} must be nonzero with finite length")
        result[key] = [x / length for x in value]
    forward, left = result["reference_forward"], result["reference_left"]
    dot = sum(a*b for a, b in zip(forward, left))
    if abs(dot) > 0.999:
        raise ValueError("Face axes must not be parallel")
    left = [b-dot*a for a, b in zip(forward, left)]
    length = math.hypot(*left)
    result["reference_left"] = [x/length for x in left]
    return result
