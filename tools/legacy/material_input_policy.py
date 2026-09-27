"""Pure input contract for the bundled master; custom graphs define their own.

Neutral resources satisfy sampler types, not missing artistic intent. Never
borrow another slot's texture. Automatic feature reductions remain review debt.
"""
import struct
import zlib

NEUTRALS = {
    "base_color": (255, 255, 255, 255), "normal": (128, 128, 255, 255),
    "rmo": (128, 0, 255, 255), "spec_mask": (0, 0, 0, 255),
    "face_sdf": (255, 255, 255, 255), "toon_ramp": (255, 255, 255, 255),
    "opacity_mask": (255, 255, 255, 255), "sphere_map": (255, 255, 255, 255),
}
DEPENDENCIES = {
    "normal": ("NormalStrength",), "rmo": ("UseRMO",),
    "spec_mask": ("HairHighlightStrength",), "toon_ramp": ("ToonRampStrength",),
    "face_sdf": ("FaceMode", "FaceSDFSpecularStrength"),
}


def neutral_png(role):
    pixel = bytes(NEUTRALS[role])
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    # Four pixels avoid relying on an importer's special handling of 1x1 normals.
    raw = (b"\0" + pixel * 4) * 4
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def effective_scalars(entry, profile, route):
    values = dict(profile.get("scalars") or {})
    values.update((entry.get("overrides") or {}).get("scalars") or {})
    debt = []
    if route == "master":
        for role, parameters in DEPENDENCIES.items():
            if entry["textures"].get(role):
                continue
            for parameter in parameters:
                requested = float(values.get(parameter, 0))
                values[parameter] = 0.0
                if requested != 0:
                    debt.append(dict(id=f"{entry['slot']}:{parameter}", slot=entry["slot"],
                                     parameter=parameter, missing_role=role, requested=requested,
                                     effective=0, status="pending",
                                     next_action="Provide reviewed input or evaluate an alternative algorithm; not visual completion"))
    return values, debt
