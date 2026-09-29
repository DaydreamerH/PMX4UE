"""Data checks for the bundled R-threshold/A-coverage face texture convention.

Constant G/B are allowed when highlight windows are unused. A full-white alpha
can also be valid; only the shadow threshold inside active coverage must vary.
These checks do not judge UV correspondence or the rendered shadow shape.
"""
import hashlib
import json
import math
from pathlib import Path


def summarize_pixels(pixels):
    ranges = [[math.inf, -math.inf] for _ in range(4)]
    covered_r, count = [], 0
    for pixel in pixels:
        if len(pixel) != 4 or not all(math.isfinite(float(v)) and 0 <= v <= 1 for v in pixel):
            raise ValueError("Expected finite RGBA data in 0..1")
        count += 1
        for i, value in enumerate(pixel):
            ranges[i][0] = min(ranges[i][0], float(value))
            ranges[i][1] = max(ranges[i][1], float(value))
        if pixel[3] > 0.5:
            covered_r.append(float(pixel[0]))
    if not count:
        raise ValueError("Texture has no pixels")
    errors = []
    if not covered_r:
        errors.append("Face application mask has no active pixels")
    elif max(covered_r) - min(covered_r) <= 1e-6:
        errors.append("Shadow threshold is constant inside face coverage (placeholder or failed bake)")
    return dict(status="invalid" if errors else "data_valid_visual_pending", errors=errors,
                pixel_count=count, covered_pixels=len(covered_r),
                channels={name: dict(min=limits[0], max=limits[1]) for name, limits in zip("RGBA", ranges)},
                covered_r_range=[min(covered_r), max(covered_r)] if covered_r else [],
                lit_fraction_by_threshold={str(t): sum(v >= t for v in covered_r) / len(covered_r)
                    for t in (0.0, 0.25, 0.5, 0.75, 1.0)} if covered_r else {})


def verify_texture_report(report):
    if report.get("schema") != "pmx4ue.face-sdf-texture.v1" or report.get("status") != "data_valid_visual_pending":
        raise ValueError("SDF texture audit is missing or invalid")
    path = Path(report.get("texture", ""))
    if not path.is_absolute() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != report.get("sha256"):
        raise ValueError("SDF source texture is missing or changed")
    bounds = report.get("covered_r_range", [])
    if (report.get("covered_pixels", 0) <= 0 or len(bounds) != 2 or
            not all(isinstance(v, (float, int)) and math.isfinite(v) for v in bounds) or
            not 0 <= bounds[0] < bounds[1] <= 1):
        raise ValueError("SDF has no varying shadow thresholds inside face coverage")
    provenance = report.get("encoding_provenance", {})
    if provenance.get("manifest"):
        manifest_path = Path(provenance["manifest"])
        if (not manifest_path.is_absolute() or not manifest_path.is_file() or
                hashlib.sha256(manifest_path.read_bytes()).hexdigest() != provenance.get("manifest_sha256")):
            raise ValueError("SDF encoding manifest is missing or changed")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if (manifest.get("schema") != "pmx4ue.face-sdf-bake.v2" or
                manifest.get("texture_sha256") != report["sha256"] or
                manifest.get("encoding") != report.get("encoding")):
            raise ValueError("SDF encoding manifest does not match this texture audit")
    return str(path.resolve()), report["sha256"]
