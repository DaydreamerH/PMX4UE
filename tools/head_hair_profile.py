"""Reviewed hair calibration in imported reference component space, without Unreal."""
import math
import re


def validate_profile(profile, namespace):
    if profile.get('version') != 1 or profile.get('reviewed') is not True:
        raise ValueError('Review hair slots, head mapping and sphere calibration first')
    if not str(profile.get('review_evidence', '')).strip():
        raise ValueError('Record calibration review_evidence')
    path = r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+'
    for key in ('mesh', 'destination'):
        if not re.fullmatch(path, str(profile.get(key, ''))):
            raise ValueError(key + ' must be a /Game package path')
    if not profile['destination'].startswith(namespace.rstrip('/') + '/'):
        raise ValueError('Destination must be inside the work order namespace')
    if profile.get('provider') not in ('mmd2ue', 'pmx4ue'):
        raise ValueError('Select an installed, compiled runtime provider')
    bone = profile.get('head_bone')
    if not isinstance(bone, str) or not bone.strip() or bone.lower() == 'none':
        raise ValueError('Provide the actual head_bone')
    slots = profile.get('hair_slots')
    if not isinstance(slots, list) or not slots or any(
            not isinstance(s, str) or not s.strip() for s in slots) or len(set(slots)) != len(slots):
        raise ValueError('hair_slots must be distinct actual material slot names')
    result = dict(profile)
    if profile.get('highlight_mode', 'preserve') not in ('preserve', 'head_band'):
        raise ValueError('highlight_mode must be preserve or head_band')
    if profile.get('highlight_mode') == 'head_band':
        from hair_reference_algorithms import validate_band
        result['band'] = validate_band(profile.get('band', {}))
    for key in ('reference_up', 'sphere_center_reference_cs'):
        value = profile.get(key)
        if not isinstance(value, list) or len(value) != 3 or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
            raise ValueError(key + ' must contain three finite numbers')
        result[key] = list(value)
    length = math.hypot(*result['reference_up'])
    if not math.isfinite(length) or length < 1e-8:
        raise ValueError('reference_up must be nonzero with finite length')
    result['reference_up'] = [x / length for x in result['reference_up']]
    return result
