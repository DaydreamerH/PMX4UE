"""Check that a reviewed material was actually observed under changed sun direction.

This validates evidence geometry, not whether the shading looks good.
"""
import math


def _direction(sun):
    try:
        pitch, yaw = float(sun["pitch"]), float(sun["yaw"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(pitch) or not math.isfinite(yaw):
        return None
    pitch, yaw = math.radians(pitch), math.radians(yaw)
    return (math.cos(pitch) * math.cos(yaw),
            math.cos(pitch) * math.sin(yaw), math.sin(pitch))


def review_light_direction(profile, reports, issue):
    """Contract 2 requires a default-sun anchor and one rotated Lit observation."""
    if profile.get("material_review_contract") != 2:
        return
    review = profile.get("light_direction_review")
    if not isinstance(review, dict):
        issue("Light-direction review is missing")
        return
    observations = review.get("observations")
    if not isinstance(observations, dict):
        observations = {}
    if (review.get("status") != "reviewed" or review.get("images_opened") is not True or
            not review.get("reviewer") or not review.get("reason") or
            any(not isinstance(observations.get(k), str) or
                not observations[k].strip()
                for k in ("shadow_transition", "highlight_response", "failure_or_limitation"))):
        issue("Light-direction review needs opened Lit images, observations and reviewer")
        return
    effect = next((e for e in profile.get("effects", []) if e.get("id") == review.get("effect")), {})
    hashes = review.get("image_sha256", [])
    if (effect.get("status") != "reviewed" or not isinstance(hashes, list) or len(hashes) < 2 or
            len(hashes) != len(set(hashes)) or any(h not in effect.get("image_sha256", []) for h in hashes)):
        issue("Light-direction review needs >=2 distinct images from one reviewed material effect")
        return
    groups = {}
    for report_id, (kind, report) in reports.items():
        if kind != "capture" or not isinstance(report, dict):
            continue
        lights = report.get("profile", {}).get("lights", [])
        anchor = lights[0].get("name") if lights else None
        for row in report.get("captures", []):
            if row.get("image", {}).get("sha256") not in hashes or row.get("mode") != "Lit":
                continue
            direction = _direction(row.get("actual_sun", {}))
            if direction is None:
                continue
            key = (report_id, row.get("case"), row.get("camera", {}).get("name"))
            groups.setdefault(key, []).append((row.get("light", {}).get("name"), anchor, direction))
    for group in groups.values():
        if not any(name == anchor for name, anchor, _ in group):
            continue
        for i, (name_a, _, a) in enumerate(group):
            for name_b, _, b in group[i + 1:]:
                dot = max(-1.0, min(1.0, sum(x*y for x, y in zip(a, b))))
                if name_a != name_b and math.degrees(math.acos(dot)) >= 20:
                    return
    issue("Light-direction review needs same report/case/camera Lit captures with default sun and >=20 degree actual sun change")
