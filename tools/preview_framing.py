"""Subject-aware camera contract. Geometry checks do not replace opening images."""
import math


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def camera_spec(camera):
    require(set(camera) == {"name", "azimuth", "elevation", "fov", "framing"},
            "Migrate camera: use azimuth/elevation/fov/framing; distance/height no longer define v3 framing")
    require(all(finite(camera[k]) for k in ("azimuth", "elevation", "fov")) and
            abs(camera["elevation"]) <= 80 and 20 <= camera["fov"] <= 90, "Invalid framing camera angles")
    f = camera["framing"]
    require(isinstance(f, dict) and f.get("kind") in ("full_body", "detail"), "Specify full_body or detail framing")
    require(finite(f.get("margin")) and .02 <= f["margin"] <= .2, "Framing margin must be .02.. .2")
    if f["kind"] == "full_body":
        require(set(f) == {"kind", "margin"}, "Full-body framing uses actual mesh bounds")
    else:
        require(("bone" in f) != ("bounds_fraction" in f), "Detail needs one actual bone or bounds_fraction")
        target = "bone" if "bone" in f else "bounds_fraction"
        require(set(f) == {"kind", "margin", target, "extent_cm", "offset_cm"}, "Incomplete/unknown detail framing")
        for key in ("extent_cm", "offset_cm", *(["bounds_fraction"] if target == "bounds_fraction" else [])):
            require(isinstance(f[key], list) and len(f[key]) == 3 and all(finite(v) for v in f[key]),
                    "Detail vectors must contain three finite numbers")
        require(min(f["extent_cm"]) > 0, "Detail extent_cm must be positive")
        if target == "bone":
            require(isinstance(f["bone"], str) and f["bone"].strip(), "Specify an actual bone name")
        else:
            require(max(abs(v) for v in f[target]) <= 1, "bounds_fraction outside [-1,1]")
    return {**f, **{k: camera[k] for k in ("azimuth", "elevation", "fov")}}


def verify_framing(row, mesh):
    spec = camera_spec(row["camera"])
    frame = row.get("framing", {})
    require(frame.get("schema") == "pmx4ue.subject-frame.v1" and frame.get("ok") is True,
            "Missing/passing subject framing receipt required; recapture with updated bridge")
    require(frame.get("subject_visible") is True and frame.get("in_front") is True,
            "Screenshot subject hidden or behind camera")
    require(frame.get("mesh", "").split(".")[0] == mesh.split(".")[0] and frame.get("actor"),
            "Screenshot framing belongs to a different/missing subject")
    require(frame.get("kind") == spec["kind"] and frame.get("margin") == spec["margin"] and
            finite(frame.get("fov")) and abs(frame["fov"]-spec["fov"]) < .01,
            "Screenshot framing does not match requested camera")
    target = "mesh_bounds" if spec["kind"] == "full_body" else spec.get("bone", "bounds_fraction")
    require(frame.get("target") == target, "Screenshot targets wrong body part")
    require(all(frame.get("viewport_"+k) == row.get("viewport_"+k) for k in ("width", "height")),
            "Viewport changed after framing; refit and recapture")
    rect = frame.get("rect")
    require(isinstance(rect, list) and len(rect) == 4 and all(finite(v) for v in rect), "Invalid projected subject bounds")
    x0, y0, x1, y1 = rect
    margin = spec["margin"]-.005
    require(margin <= x0 < x1 <= 1-margin and margin <= y0 < y1 <= 1-margin and
            max(x1-x0, y1-y0) >= .5, "Screenshot subject clipped or too small")
