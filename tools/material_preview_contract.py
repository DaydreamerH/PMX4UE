"""Engine-independent input and screenshot checks; never a visual acceptance test."""
import hashlib
import math
from pathlib import Path
import re
import struct
import zlib


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(profile, namespace, source_mesh=None):
    require(profile.get("schema") == "pmx4ue.material-preview.v1", "Unknown preview schema")
    require(profile.get("reviewed") is True, "Review cameras, slots and A/B cases first")
    require(profile["level"].startswith(namespace + "/Preview/") and
            re.fullmatch(r"/Game/[A-Za-z0-9_/]+", profile["level"]), "Preview level outside work-order namespace")
    require(profile["mesh"].startswith(namespace + "/") or (source_mesh and profile["mesh"] == source_mesh),
            "Preview mesh outside work-order namespace/explicit retained mesh")
    require(all(type(profile[k]) is int and 256 <= profile[k] <= 4096 for k in ("width", "height")), "Capture size out of range")
    require(2 <= profile["warmup_seconds"] <= 60, "Warmup must be 2..60 seconds")
    require(math.isfinite(profile["exposure_ev100"]), "Invalid exposure")
    require(set(profile["modes"]) == {"Lit", "Unlit", "WorldNormal"} and len(profile["modes"]) == 3,
            "Include Lit, Unlit and WorldNormal once each")
    for field in ("cameras", "lights", "cases"):
        rows = profile[field]
        names = [r["name"] for r in rows]
        require(rows and len(names) == len(set(names)) and
                all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n) for n in names), "Invalid/duplicate " + field)
    for camera in profile["cameras"]:
        require(all(math.isfinite(camera[k]) for k in ("azimuth", "distance", "height", "fov")), "Invalid camera")
        require(100 <= camera["distance"] <= 1200 and -100 <= camera["height"] <= 200 and
                20 <= camera["fov"] <= 90, "Camera would be clamped by native bridge; adapt bridge for this model")
    for light in profile["lights"]:
        require(all(math.isfinite(light[k]) for k in ("pitch", "yaw", "intensity")) and light["intensity"] > 0,
                "Invalid light")
    baseline = profile["cases"][0]
    require(baseline == {"name": "Baseline", "slots": []}, "First case must be unmodified Baseline")
    for case in profile["cases"]:
        require(set(case) <= {"name", "slots", "outline", "depth_rim"}, "Unknown case field")
        indices = [r["index"] for r in case["slots"]]
        require(len(indices) == len(set(indices)) and all(type(i) is int and i >= 0 for i in indices), "Invalid slots")
        for row in case["slots"]:
            require(set(row) <= {"index", "material", "scalars"}, "Unknown slot override")
            require(all(math.isfinite(v) for v in row.get("scalars", {}).values()), "Invalid scalar")
        for effect in ("outline", "depth_rim"):
            if effect in case:
                require(isinstance(case[effect], str) and case[effect].startswith("/Game/"), "Effect requires reviewed material asset")
    require(len(profile["cases"])*len(profile["cameras"])*len(profile["lights"])*3 <= 120,
            "Split large capture matrices into separate preview work orders")
    return profile


def png_evidence(path, width, height):
    """Reject missing, partial, CRC-invalid or wrong-size PNG; appearance still needs an agent."""
    path = Path(path)
    data = path.read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG")
    offset, kinds = 8, []
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
        kinds.append(kind)
        offset = end
        if kind == b"IEND":
            require(size == 0 and end == len(data) and b"IDAT" in kinds, "Invalid PNG end")
            return dict(path=str(path.resolve()), bytes=len(data), width=width, height=height,
                        sha256=hashlib.sha256(data).hexdigest())
    raise ValueError("PNG has no complete IEND")


def verify_report(report):
    require(report.get("status") == "captured_visual_pending", "Preview failed; inspect its error and log")
    require(report["captures"] and len(report["captures"]) == report["expected_captures"], "Incomplete capture matrix")
    profile = report["profile"]
    expected = {(c["name"], v["name"], l["name"], m) for c in profile["cases"]
                for v in profile["cameras"] for l in profile["lights"] for m in profile["modes"]}
    actual_keys = [(r["case"], r["camera"]["name"], r["light"]["name"], r["mode"]) for r in report["captures"]]
    require(len(actual_keys) == len(expected) and set(actual_keys) == expected, "Missing or duplicated A/B capture")
    for row in report["captures"]:
        image = row["image"]
        actual = png_evidence(image["path"], image["width"], image["height"])
        require(actual["sha256"] == image["sha256"], "Screenshot changed after capture")
    require(report.get("input_assets_unchanged") is True, "Preview input assets changed")
    for path, digest in report["input_assets"]["game_package_sha256"].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, "Preview evidence has stale asset: " + path)
