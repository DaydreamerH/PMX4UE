"""Engine-independent input and screenshot checks; never a visual acceptance test."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib
if __package__:
    from .outline_contract import outline_spec
    from .preview_framing import camera_spec, verify_framing
else:
    from outline_contract import outline_spec
    from preview_framing import camera_spec, verify_framing


def require(condition, message):
    if not condition:
        raise ValueError(message)


class CapturePixelsError(ValueError):
    """A complete screenshot has invalid pixels; waiting for the file cannot fix it."""


def _pixel_evidence(header, compressed):
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", header)
    if depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
        raise CapturePixelsError("Expected non-interlaced 8-bit RGB/RGBA viewport PNG")
    channels = 3 if color == 2 else 4
    stride = width * channels
    expected = height * (stride + 1)
    # Resource safety limit, not a minimum screenshot resolution or quality gate.
    if width < 1 or height < 1 or expected > 256 * 1024 * 1024:
        raise CapturePixelsError("Invalid or excessive decoded PNG allocation")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, expected + 1)
    except zlib.error as error:
        raise CapturePixelsError("Invalid PNG compressed pixels") from error
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise CapturePixelsError("PNG decoded pixel length/stream mismatch")
    previous = bytearray(stride)
    totals, minima, maxima = [0] * 3, [255] * 3, [0] * 3
    alpha_min, alpha_max, nonopaque, near_black, near_white = 255, 0, 0, 0, 0
    for y in range(height):
        offset = y * (stride + 1)
        kind = raw[offset]
        row = bytearray(raw[offset + 1:offset + stride + 1])
        if kind > 4:
            raise CapturePixelsError("Unknown PNG row filter")
        if kind:
            for i in range(stride):
                left = row[i-channels] if i >= channels else 0
                up = previous[i]
                corner = previous[i-channels] if i >= channels else 0
                if kind == 1:
                    predictor = left
                elif kind == 2:
                    predictor = up
                elif kind == 3:
                    predictor = (left + up) // 2
                else:
                    p = left + up - corner
                    a, b, c = abs(p-left), abs(p-up), abs(p-corner)
                    predictor = left if a <= b and a <= c else up if b <= c else corner
                row[i] = (row[i] + predictor) & 255
        rgb = [row[c::channels] for c in range(3)]
        for c in range(3):
            totals[c] += sum(rgb[c])
            minima[c], maxima[c] = min(minima[c], min(rgb[c])), max(maxima[c], max(rgb[c]))
        near_black += sum(max(pixel) <= 3 for pixel in zip(*rgb))
        near_white += sum(min(pixel) >= 252 for pixel in zip(*rgb))
        alpha = row[3::4] if channels == 4 else bytes([255]) * width
        alpha_min, alpha_max = min(alpha_min, min(alpha)), max(alpha_max, max(alpha))
        nonopaque += width - alpha.count(255)
        previous = row
    count = width * height
    if nonopaque:
        raise CapturePixelsError(
            f"Non-opaque viewport PNG: alpha {alpha_min}..{alpha_max}, {nonopaque}/{count} pixels. "
            "Rebuild the opaque capture bridge, restart the owned editor and recapture; do not adjust exposure/materials.")
    warnings = []
    if near_black / count >= .98:
        warnings.append("near_black_rgb: inspect sky/ground, camera and exposure before materials")
    if near_white / count >= .98:
        warnings.append("near_white_rgb: inspect exposure/clipping")
    if minima == maxima:
        warnings.append("uniform_rgb: inspect actual viewport and scene visibility")
    return dict(alpha_min=alpha_min, alpha_max=alpha_max, nonopaque_pixels=nonopaque,
                rgb_mean=[v/count for v in totals], rgb_min=minima, rgb_max=maxima,
                near_black_fraction=near_black/count, near_white_fraction=near_white/count,
                warnings=warnings, note="Encoded RGB byte statistics only; not visual approval or physical luminance")


def capture_jobs(profile):
    """Main appearance matrix plus explicitly targeted, non-repeated diagnostics.

    Keep legacy explicit modes working. New work orders use Lit only and name
    the exact case/camera/light for any one-off diagnostic.
    """
    modes = profile.get("modes", ["Lit"])
    require(isinstance(modes, list) and modes and all(isinstance(m, str) for m in modes)
            and len(modes) == len(set(modes)) and "Lit" in modes
            and set(modes) <= {"Lit", "Unlit", "WorldNormal"},
            "Capture modes must include Lit, contain no duplicates and use supported modes")
    lights = profile["lights"]
    primary = profile.get("primary_light")
    if primary:
        require(primary in {light["name"] for light in lights}, "Unknown primary_light")
        lights = [next(light for light in lights if light["name"] == primary),
                  *[light for light in lights if light["name"] != primary]]
    jobs = [(c, v, l, m) for c in profile["cases"] for v in profile["cameras"]
            for l in lights for m in modes]
    keys = {(c["name"], v["name"], l["name"], m) for c, v, l, m in jobs}
    diagnostics = profile.get("diagnostic_captures", [])
    require(isinstance(diagnostics, list), "diagnostic_captures must be a list")
    lookup = {field: {row["name"]: row for row in profile[field]}
              for field in ("cases", "cameras", "lights")}
    for d in diagnostics:
        require(isinstance(d, dict) and set(d) == {"case", "camera", "light", "mode", "reason"},
                "Diagnostic requires case, camera, light, mode and reason")
        require(all(isinstance(d[k], str) for k in d) and d["reason"].strip()
                and d["mode"] in {"Unlit", "WorldNormal"}, "Invalid diagnostic mode/reason")
        require(d["case"] in lookup["cases"] and d["camera"] in lookup["cameras"]
                and d["light"] in lookup["lights"], "Unknown diagnostic case/camera/light")
        key = (d["case"], d["camera"], d["light"], d["mode"])
        require(key not in keys, "Duplicate diagnostic capture")
        keys.add(key)
        jobs.append((lookup["cases"][d["case"]], lookup["cameras"][d["camera"]],
                     lookup["lights"][d["light"]], d["mode"]))
    require(len(jobs) <= 120, "Split large capture matrices into separate preview work orders")
    return jobs


def validate(profile, namespace, source_mesh=None):
    require(profile.get("schema") in {"pmx4ue.material-preview.v1", "pmx4ue.material-preview.v2", "pmx4ue.material-preview.v3"}, "Unknown preview schema")
    visible = profile["schema"] == "pmx4ue.material-preview.v3"
    daylight = profile["schema"] in {"pmx4ue.material-preview.v2", "pmx4ue.material-preview.v3"}
    if daylight:
        environment = profile.get("environment", {})
        require(set(environment) == {"template", "model_location"}, "Specify template and model_location")
        require(environment["template"] == "/Engine/Maps/Templates/OpenWorld",
                "Daylight preview requires the verified Open World template; adapt explicitly for another engine/template")
        location = environment["model_location"]
        require(isinstance(location, list) and len(location) == 3 and
                all(type(v) in (float, int) and math.isfinite(v) for v in location), "Invalid model_location")
    require(profile.get("reviewed") is True, "Review cameras, slots and A/B cases first")
    if visible:
        require("level" not in profile, "v3 loads the daylight template directly; do not create a custom preview level")
        require("width" not in profile and "height" not in profile,
                "v3 records the actual viewport size; remove legacy requested dimensions")
    else:
        require(profile["level"].startswith(namespace + "/Preview/") and
                re.fullmatch(r"/Game/[A-Za-z0-9_/]+", profile["level"]), "Preview level outside work-order namespace")
    require(profile["mesh"].startswith(namespace + "/") or (source_mesh and profile["mesh"] == source_mesh),
            "Preview mesh outside work-order namespace/explicit retained mesh")
    if visible:
        capture = profile.get("capture", {})
        require(capture == {"mode": "visible_viewport_backbuffer"}, "v3 requires visible viewport capture without a size threshold")
    else:
        require(all(type(profile[k]) is int and 256 <= profile[k] <= 4096 for k in ("width", "height")), "Capture size out of range")
    require(2 <= profile["warmup_seconds"] <= 60, "Warmup must be 2..60 seconds")
    exposure = profile["exposure_ev100"]
    require((daylight and exposure is None) or
            (type(exposure) in (float, int) and math.isfinite(exposure)), "Invalid exposure")
    if visible and "environment_review" in profile:
        review = profile["environment_review"]
        require(isinstance(review, dict), "environment_review must be an object when supplied")
        require(review.get("images_opened") is True and
                all(isinstance(review.get(k), str) and review[k].strip()
                    for k in ("reviewer", "report", "report_sha256", "exposure_reason")) and
                all(isinstance(review.get("observations", {}).get(k), str) and
                    review["observations"][k].strip() for k in ("sky", "ground", "character")) and
                isinstance(review.get("lit_image_sha256"), list) and review["lit_image_sha256"],
                "Supplied environment_review must describe an opened Baseline report")
    for field in ("cameras", "lights", "cases"):
        rows = profile[field]
        names = [r["name"] for r in rows]
        require(rows and len(names) == len(set(names)) and
                all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n) for n in names), "Invalid/duplicate " + field)
    if "primary_light" in profile:
        require(visible and isinstance(profile["primary_light"], str) and
                profile["primary_light"] in {row["name"] for row in profile["lights"]},
                "primary_light must name an existing v3 light")
    for camera in profile["cameras"]:
        if visible:
            camera_spec(camera)
            continue
        require(all(math.isfinite(camera[k]) for k in ("azimuth", "distance", "height", "fov")), "Invalid camera")
        require(100 <= camera["distance"] <= 1200 and -100 <= camera["height"] <= 200 and
                20 <= camera["fov"] <= 90, "Camera would be clamped by native bridge; adapt bridge for this model")
    for light in profile["lights"]:
        if daylight:
            require(set(light) <= {"name", "pitch", "yaw", "yaw_offset", "intensity"}, "Unknown daylight override")
            require(not ("yaw" in light and "yaw_offset" in light), "Use absolute yaw or yaw_offset, not both")
            require(all(type(v) in (float, int) and math.isfinite(v) for k, v in light.items() if k != "name"),
                    "Invalid daylight override")
            require("intensity" not in light or light["intensity"] > 0, "Invalid daylight intensity")
        else:
            require(all(math.isfinite(light[k]) for k in ("pitch", "yaw", "intensity")) and light["intensity"] > 0,
                    "Invalid light")
    if daylight:
        require(set(profile["lights"][0]) == {"name"}, "First daylight capture must retain template sun settings")
    baseline = profile["cases"][0]
    require(baseline == {"name": "Baseline", "slots": []}, "First case must be unmodified Baseline")
    for case in profile["cases"]:
        require(set(case) <= {"name", "slots", "outline", "depth_rim", "head_hair_report"}, "Unknown case field")
        if "head_hair_report" in case:
            require(isinstance(case["head_hair_report"], str) and case["head_hair_report"].strip(),
                    "head_hair_report requires a built report path")
        indices = [r["index"] for r in case["slots"]]
        require(len(indices) == len(set(indices)) and all(type(i) is int and i >= 0 for i in indices), "Invalid slots")
        for row in case["slots"]:
            require(set(row) <= {"index", "material", "scalars"}, "Unknown slot override")
            require(all(math.isfinite(v) for v in row.get("scalars", {}).values()), "Invalid scalar")
        for effect in ("outline", "depth_rim"):
            if effect in case:
                if effect == "outline":
                    outline_spec(case[effect])
                    continue
                require(isinstance(case[effect], str) and case[effect].startswith("/Game/"), "Effect requires reviewed material asset")
    capture_jobs(profile)
    return profile


def png_evidence(path, width, height):
    """Decode and check ordinary opaque screenshots; appearance still needs an agent."""
    path = Path(path)
    data = path.read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG")
    offset, kinds, compressed, header = 8, [], bytearray(), None
    while offset < len(data):
        require(offset + 12 <= len(data), "Incomplete PNG header")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        require(end <= len(data), "Incomplete PNG chunk")
        kind = data[offset+4:offset+8]
        require(zlib.crc32(data[offset+4:end-4]) & 0xffffffff == struct.unpack_from(">I", data, end-4)[0], "PNG CRC mismatch")
        if not kinds:
            require(kind == b"IHDR" and size == 13, "Missing PNG IHDR")
            require(struct.unpack_from(">II", data, offset+8) == (width, height), "Wrong screenshot size")
            header = data[offset+8:end-4]
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG IHDR")
        if kind == b"IDAT":
            compressed.extend(data[offset+8:end-4])
        kinds.append(kind)
        offset = end
        if kind == b"IEND":
            require(size == 0 and end == len(data) and b"IDAT" in kinds, "Invalid PNG end")
            return dict(path=str(path.resolve()), bytes=len(data), width=width, height=height,
                        sha256=hashlib.sha256(data).hexdigest(), pixels=_pixel_evidence(header, compressed))
    raise ValueError("PNG has no complete IEND")


def verify_environment_review(profile):
    """Verify an optional prior Baseline reference, including default-exposure runs.

    Neither multi-case capture nor fixed exposure requires a separate calibration run.
    Explicit references still must be authentic and match the current settings.
    """
    if profile.get("schema") != "pmx4ue.material-preview.v3" or "environment_review" not in profile:
        return []
    review = profile["environment_review"]
    require(isinstance(review, dict), "environment_review must be an object when supplied")
    require(review.get("images_opened") is True, "Open and review the environment Baseline before A/B")
    path = Path(review.get("report", ""))
    require(path.is_absolute() and path.is_file(), "environment_review.report must be an existing absolute path")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == review.get("report_sha256"), "Environment Baseline report changed")
    baseline = json.loads(data.decode("utf-8-sig"))
    prior = baseline["profile"]
    # Reject chained references BEFORE verification so reports cannot recurse.
    require(prior["cases"] == [{"name": "Baseline", "slots": []}], "Environment reference must be Baseline-only")
    require("environment_review" not in prior, "Environment Baseline reference must not chain environment_review")
    for key in ("mesh", "environment", "exposure_ev100", "cameras", "lights"):
        require(prior.get(key) == profile.get(key), "Environment calibration differs: " + key)
    verify_report(baseline)
    lit = [row for row in baseline["captures"] if row["mode"] == "Lit"]
    require(lit and set(review.get("lit_image_sha256", [])) == {row["image"]["sha256"] for row in lit},
            "Review every Lit environment calibration image by hash")
    for row in lit:
        sun = row.get("actual_sun", {})
        require(all(type(sun.get(k)) in (int, float) and math.isfinite(sun[k])
                    for k in ("pitch", "yaw", "roll", "intensity")), "Baseline missing actual sun readback")
    require(all(isinstance(review.get(k), str) and review[k].strip() for k in ("reviewer", "exposure_reason")) and
            all(isinstance(review.get("observations", {}).get(k), str) and review["observations"][k].strip()
                for k in ("sky", "ground", "character")), "Missing environment visual observations")
    return [str(path), *[row["image"]["path"] for row in baseline["captures"]]]


def verify_report(report):
    require(report.get("status") == "captured_visual_pending", "Preview failed; inspect its error and log")
    require(report["profile"]["schema"] == "pmx4ue.material-preview.v3",
            "Legacy screenshot cannot pass material visual evidence gate; migrate to v3")
    require(report["captures"] and len(report["captures"]) == report["expected_captures"], "Incomplete capture matrix")
    profile = report["profile"]
    expected = {(c["name"], v["name"], l["name"], m) for c, v, l, m in capture_jobs(profile)}
    actual_keys = [(r["case"], r["camera"]["name"], r["light"]["name"], r["mode"]) for r in report["captures"]]
    require(len(actual_keys) == len(expected) and set(actual_keys) == expected, "Missing or duplicated A/B capture")
    for row in report["captures"]:
        image = row["image"]
        actual = png_evidence(image["path"], image["width"], image["height"])
        require(actual["sha256"] == image["sha256"], "Screenshot changed after capture")
        if profile["schema"] == "pmx4ue.material-preview.v3":
            require(row.get("capture_source") == "visible_viewport_backbuffer", "Offscreen capture is not v3 visual evidence")
            require(image["width"] == row.get("viewport_width") and image["height"] == row.get("viewport_height"),
                    "Screenshot was resized or viewport dimensions were not recorded")
            residency = row.get("texture_residency", {})
            textures = residency.get("textures", [])
            require(residency.get("ready") is True and type(residency.get("checked")) is int and
                    residency["checked"] > 0 and residency.get("pending") == 0 and
                    len(textures) == residency["checked"] and
                    all(t.get("ready") is True and t.get("available_mips", 0) > 0 and
                        t.get("resident_mips", -1) >= t["available_mips"] for t in textures),
                    "Character textures were not fully resident at capture")
            require(type(row.get("r_screen_percentage_setting")) in (float, int),
                    "Missing screen-percentage setting")
            require(row["camera"] in profile["cameras"], "Capture camera differs from profile")
            verify_framing(row, profile["mesh"])
    daylight = report.get("daylight_map", {})
    require(daylight.get("path") == profile["environment"]["template"] and
            daylight.get("source_unchanged") is True and daylight.get("saved_by_preview") is False,
            "Open World daylight map was not used safely")
    require(report.get("input_assets_unchanged") is True, "Preview input assets changed")
    for path, digest in report["input_assets"]["game_package_sha256"].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, "Preview evidence has stale asset: " + path)
    verify_environment_review(profile)
