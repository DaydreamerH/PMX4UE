"""Portable outline routing and model-specific UV region checks; no visual approval."""
import math


def require(ok, message):
    if not ok:
        raise ValueError(message)


def outline_spec(value, slot_count=None):
    # Existing string profiles retain the unmasked all-slot candidate behavior.
    spec = {"material": value} if isinstance(value, str) else value
    require(isinstance(spec, dict) and set(spec) <= {
        "material", "face_material", "hair_material", "face_slots", "hair_slots", "excluded_slots"},
        "Unknown outline routing field")
    require(isinstance(spec.get("material"), str) and spec["material"].startswith("/Game/"),
            "Outline requires a general material")
    result = dict(spec)
    groups = []
    for kind in ("face", "hair", "excluded"):
        slots = spec.get(kind + "_slots", [])
        require(isinstance(slots, list) and all(type(i) is int and i >= 0 for i in slots), "Invalid outline slots")
        require(len(slots) == len(set(slots)), "Duplicate outline slots")
        if slot_count is not None:
            require(all(i < slot_count for i in slots), "Outline slot outside mesh")
        result[kind + "_slots"] = slots
        if kind != "excluded":
            path = spec.get(kind + "_material", "")
            require((not slots and not path) or
                    (bool(slots) and isinstance(path, str) and path.startswith("/Game/")),
                    "Outline specialized material and slots must be specified together")
            result[kind + "_material"] = path
        groups.append(set(slots))
    require(not any(a & b for n, a in enumerate(groups) for b in groups[n+1:]),
            "Outline face/hair/excluded slots must not overlap")
    return result


def outline_assets(value):
    spec = outline_spec(value)
    return [spec[k] for k in ("material", "face_material", "hair_material") if spec[k]]


def outline_args(value, slot_count, clear=False):
    spec = outline_spec(value, slot_count)
    csv = lambda values: ",".join(map(str, values))
    return (spec["material"], spec["face_material"], spec["hair_material"],
            csv(range(slot_count) if clear else spec["excluded_slots"]),
            csv(spec["face_slots"]), csv(spec["hair_slots"]), 6000., False)


def verify_outline_receipt(value, receipt, slot_count, clear=False):
    spec = outline_spec(value, slot_count)
    package = lambda path: str(path).split('.')[0]
    require(receipt.get("ok") is True and receipt.get("saved") is False, "Outline attachment failed or saved level")
    for field, key in (("overlay_material", "material"), ("face_overlay_material", "face_material"),
                       ("hair_overlay_material", "hair_material")):
        expected = spec[key] or "None"
        require(package(receipt.get(field)) == package(expected), "Outline material receipt mismatch: " + field)
    excluded = set(range(slot_count)) if clear else set(spec["excluded_slots"])
    require(set(receipt.get("excluded_slots", [])) == excluded and
            set(receipt.get("applied_slots", [])) == set(range(slot_count)) - excluded,
            "Outline slot receipt mismatch")


def face_regions(options):
    regions = options.get("face_internal", [])
    require(isinstance(regions, list), "face_internal must be a list")
    uv = options.get("face_uv_channel", 0)
    require(type(uv) is int and 0 <= uv <= 7, "Invalid face UV channel")
    if regions:
        require(options.get("face_internal_reviewed") is True and
                isinstance(options.get("face_internal_evidence"), str) and options["face_internal_evidence"].strip(),
                "Calibrate mouth/eye regions against actual model UVs and record evidence first")
    names = set()
    for r in regions:
        require(isinstance(r, dict) and set(r) == {"name", "center", "radius"}, "Invalid face region fields")
        require(isinstance(r["name"], str) and r["name"] and r["name"] not in names, "Invalid/duplicate face region name")
        names.add(r["name"])
        for key in ("center", "radius"):
            v = r[key]
            require(isinstance(v, list) and len(v) == 2 and
                    all(type(x) in (float, int) and math.isfinite(x) for x in v), "Invalid face region " + key)
        require(all(x > 0 for x in r["radius"]), "Face region radius must be positive")
    return regions
