"""Pure-Python discovery, configuration, and planning for MMD2UE.

This module deliberately does not import Blender or Unreal.  It is the stable
control plane shared by command-line, Blender, Unreal Python, and agent tools.
Heuristic classification produces review candidates only; it never binds a
texture to a material automatically.

It also defines the canonical, schema-independent material-map shape that every
Unreal-side builder consumes.  A character's on-disk map may be the older
``slot_groups`` form or the newer ``slots`` form; both normalise to one output.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = "mmd2ue.character.v1"
REPORT_SCHEMA = "mmd2ue.source-audit.v1"
PLAN_SCHEMA = "mmd2ue.execution-plan.v1"
MATERIAL_MAP_SCHEMA = "mmd2ue.material-map.v3"
MATERIAL_MAP_SCHEMAS = {"mmd2ue.material-map.v2", "mmd2ue.material-map.v3"}
TEXTURE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".dds", ".exr",
    ".spa", ".sph",
}
CHARACTER_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")

PROFILE_PRESETS_PATH = "Tools/MMDPipeline/framework/profiles/material_profile_presets.v1.json"


@dataclass(frozen=True)
class TextureCandidate:
    role: str
    confidence: str
    reason: str


ROLE_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("face_sdf", ("facesdf", "face_sdf"), ("sdf",)),
    ("normal", ("_normal", "normalmap", "_nrm", "_nor"), ("_n", "normal")),
    ("rmo", ("_rmo", "_orm", "roughnessmetallic", "occlusionroughness"), ("rmo", "orm")),
    ("spec_mask", ("_spc", "specmask", "spec_mask", "highlightmask"), ("spec", "highlight")),
    ("base_color", ("_basecolor", "base_color", "_albedo", "_diffuse"), ("_d", "_da", "albedo", "diffuse")),
    ("toon_ramp", ("toon", "ramp"), ("toon", "ramp")),
    ("sphere_map", (".spa", ".sph", "matcap"), ("sphere", "shine", "matcap")),
    ("opacity_mask", ("opacity", "alpha", "mask"), ("opacity", "alpha")),
)

# Canonical texture roles and the material parameter each one drives.
ROLE_ORDER: tuple[str, ...] = (
    "base_color",
    "normal",
    "rmo",
    "spec_mask",
    "opacity_mask",
    "toon_ramp",
    "sphere_map",
    "face_sdf",
)
TEXTURE_PARAMETER_NAMES: dict[str, str] = {
    "base_color": "BaseColorTexture",
    "normal": "NormalTexture",
    "rmo": "RMOTexture",
    "spec_mask": "DetailMaskTexture",
    "face_sdf": "FaceSDFTexture",
    "toon_ramp": "ToonRampTexture",
}

# Slot-name hints used only to propose a profile in the review draft.  They
# never bind a texture; a human or agent must still approve every slot.
PROFILE_SLOT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("stocking", ("stocking", "sock", "pantyhose", "tights", "丝袜", "タイツ")),
    ("nails", ("nail", "zhijia", "指甲", "爪")),
    ("teeth", ("teeth", "tooth", "牙")),
    ("mouth", ("mouth", "tongue", "口", "舌")),
    ("facial_detail", ("brow", "lash", "eyebrow", "eyelash", "眉", "睫毛")),
    ("eye_white", ("eyewhite", "eye_white", "eyeball")),
    ("eye_overlay", ("eyeblend", "eyeshadow", "eyeshine", "eye_overlay")),
    ("iris", ("eye", "iris", "pupil", "目", "瞳")),
    ("hair", ("hair", "髪", "发", "毛")),
    ("face_skin", ("face", "顔", "脸")),
    ("effect", ("effect", "glow", "emissive", "aura", "闪光", "光效")),
    ("body_skin", ("body", "skin", "hada", "肌", "身体")),
    ("weapon", ("weapon", "sword", "blade", "gun", "武器", "刀", "枪")),
    ("leather", ("leather", "shoe", "boot", "belt", "glove", "皮革", "鞋")),
    ("metal", ("metal", "necklace", "buckle", "earring", "金属")),
    ("gem", ("gem", "jewel", "crystal", "钻石", "宝石")),
    ("glass", ("glass", "lens", "眼镜", "玻璃")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_root_from(start: Path) -> Path:
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if any(candidate.glob("*.uproject")):
            return candidate
    raise ValueError(f"no .uproject found above {start}")


def resolve_path(project_root: Path, value: str) -> Path:
    expanded = str(value).replace("${PROJECT_ROOT}", str(project_root))
    path = Path(expanded)
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def portable_path(project_root: Path, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def classify_texture(path: Path) -> list[TextureCandidate]:
    """Return conservative filename-based role candidates in priority order."""
    name = Path(path).stem.casefold().replace("-", "_").replace(" ", "_")
    suffix = Path(path).suffix.casefold()
    candidates: list[TextureCandidate] = []
    for role, strong_tokens, weak_tokens in ROLE_RULES:
        searchable = name + suffix
        strong = next((token for token in strong_tokens if token in searchable), None)
        if strong:
            candidates.append(TextureCandidate(role, "high", f"name contains explicit token '{strong}'"))
            continue
        weak = next((token for token in weak_tokens if token in searchable), None)
        if weak:
            candidates.append(TextureCandidate(role, "medium", f"name contains token '{weak}'"))
    if not candidates:
        candidates.append(TextureCandidate("unclassified", "none", "no reliable filename token"))
    return candidates


def image_metadata(path: Path) -> dict:
    """Read cheap PNG/BMP dimensions without optional image libraries."""
    result: dict[str, object] = {}
    try:
        with Path(path).open("rb") as stream:
            header = stream.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 26:
            width, height = struct.unpack(">II", header[16:24])
            color_type = header[25]
            result.update(width=width, height=height, alpha_capable=color_type in {4, 6})
        elif header.startswith(b"BM") and len(header) >= 30:
            width, height = struct.unpack("<ii", header[18:26])
            bits = struct.unpack("<H", header[28:30])[0]
            result.update(width=abs(width), height=abs(height), bits_per_pixel=bits, alpha_capable=bits == 32)
    except (OSError, struct.error):
        pass
    return result


def iter_source_textures(source_root: Path) -> Iterable[Path]:
    if not Path(source_root).is_dir():
        return ()
    return (
        path
        for path in sorted(Path(source_root).rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file() and path.suffix.casefold() in TEXTURE_EXTENSIONS
    )


def suggest_profile(slot_name: str, config: dict | None = None) -> str:
    """Propose a profile from slot-name tokens.  Advisory only."""
    name = str(slot_name).casefold()
    for profile, tokens in PROFILE_SLOT_HINTS:
        if any(token in name for token in tokens):
            if profile == "iris" and "white" in name:
                return "eye_white"
            return profile
    if config:
        for token in config.get("discovery", {}).get("face_slot_candidates", []):
            if token.casefold() in name:
                return "face_skin"
    return "cloth"


def validate_config(config: dict, project_root: Path) -> list[dict]:
    issues: list[dict] = []

    def issue(level: str, code: str, message: str) -> None:
        issues.append({"level": level, "code": code, "message": message})

    if config.get("schema") != SCHEMA:
        issue("error", "schema", f"schema must be '{SCHEMA}'")
    character = config.get("character") or {}
    character_id = character.get("id", "")
    if not CHARACTER_ID_RE.fullmatch(character_id):
        issue("error", "character_id", "character.id must match [A-Za-z][A-Za-z0-9_]{1,63}")
    source = config.get("source") or {}
    pmx_value = source.get("pmx")
    root_value = source.get("root")
    if not pmx_value:
        issue("error", "source_pmx", "source.pmx is required")
    elif not resolve_path(project_root, pmx_value).is_file():
        issue("error", "source_pmx_missing", f"PMX does not exist: {pmx_value}")
    if not root_value:
        issue("error", "source_root", "source.root is required")
    elif not resolve_path(project_root, root_value).is_dir():
        issue("error", "source_root_missing", f"source root does not exist: {root_value}")
    paths = config.get("paths") or {}
    ue_root = paths.get("ue_root", "")
    if ue_root and not re.fullmatch(r"/Game(?:/[A-Za-z0-9_]+)+", ue_root):
        issue("error", "ue_root", "paths.ue_root must be a /Game/... content path using safe identifiers")
    if character_id and ue_root and not ue_root.endswith("/" + character_id):
        issue("warning", "ue_root_id", "UE root does not end with character.id; verify collision isolation")
    if not config.get("features"):
        issue("warning", "features", "no optional rendering features are declared")
    return issues


def build_source_audit(config: dict, project_root: Path) -> dict:
    source = config["source"]
    pmx = resolve_path(project_root, source["pmx"])
    source_root = resolve_path(project_root, source["root"])
    textures = []
    stems: dict[str, list[str]] = {}
    for path in iter_source_textures(source_root):
        relative = path.relative_to(source_root).as_posix()
        candidates = classify_texture(path)
        stems.setdefault(path.stem.casefold(), []).append(relative)
        textures.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "metadata": image_metadata(path),
                "candidates": [candidate.__dict__ for candidate in candidates],
                "binding_status": "review_required",
            }
        )
    duplicate_stems = {key: values for key, values in stems.items() if len(values) > 1}
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": utc_now(),
        "character_id": config["character"]["id"],
        "source": {
            "pmx": str(pmx),
            "pmx_exists": pmx.is_file(),
            "pmx_bytes": pmx.stat().st_size if pmx.is_file() else None,
            "root": str(source_root),
        },
        "summary": {
            "texture_count": len(textures),
            "duplicate_stem_count": len(duplicate_stems),
            "unclassified_count": sum(item["candidates"][0]["role"] == "unclassified" for item in textures),
            "automatic_bindings": 0,
        },
        "duplicate_stems": duplicate_stems,
        "textures": textures,
        "rules": [
            "Candidates are filename hints, not material bindings.",
            "Normal/RMO may only be enabled after material-slot and UV-family verification.",
            "Sphere maps and toon ramps require dedicated coordinates and are never ordinary UV textures.",
        ],
    }


def make_character_config(
    project_root: Path,
    character_id: str,
    display_name: str,
    pmx: Path,
    source_root: Path,
    scale: float,
) -> dict:
    if not CHARACTER_ID_RE.fullmatch(character_id):
        raise ValueError("character id must match [A-Za-z][A-Za-z0-9_]{1,63}")
    artifact = f"Artifacts/{character_id}"
    return {
        "schema": SCHEMA,
        "character": {"id": character_id, "display_name": display_name},
        "source": {
            "pmx": portable_path(project_root, pmx),
            "root": portable_path(project_root, source_root),
            "scale": scale,
            "preserve_original": True,
        },
        "paths": {
            "artifact_dir": artifact,
            "source_assets_dir": f"SourceAssets/{character_id}",
            "ue_root": f"/Game/Characters/{character_id}",
            "material_map": f"{artifact}/material_map.json",
        },
        "orientation": {
            "character_forward": "+Y",
            "character_left": "+X",
            "up": "+Z",
            "verify_in_blender": True,
        },
        "discovery": {
            "face_slot_candidates": ["Face", "face", "顔"],
            "hair_slot_tokens": ["hair", "髪"],
            "stocking_slot_tokens": ["stocking", "socks", "pantyhose", "丝袜", "タイツ"],
            "eye_slot_tokens": ["eye", "iris", "目"],
        },
        "features": {
            "face_sdf": {"mode": "probe_then_decide", "required": False},
            "hair_highlight": {"mode": "when_uv_and_mask_exist", "required": False},
            "bang_shadow": {"mode": "requires_stencil_design", "required": False},
            "bang_transparency": {"mode": "requires_mesh_or_stencil_mask", "required": False},
            "cloth_stylized_pbr": {"mode": "default", "required": True},
            "stocking_pbr": {"mode": "when_slots_exist", "required": False},
            "outline": {"mode": "inverse_hull", "required": True},
            "depth_rim": {"mode": "post_process", "required": False},
        },
        "validation": {
            "reference_map": "Untitled",
            "shader_platform": "PCD3D_SM6",
            "require_zero_compile_errors": True,
            "require_original_asset_paths": True,
            "forbid_asset_name_tokens": ["_Fixed", "_Fixed2", "_TestCopy"],
            "light_azimuths": [0, 90, 180, 270],
            "capture_views": ["front", "face_closeup", "legs_closeup", "three_quarter"],
        },
        "notes": [
            "Fill material_map only after the Blender slot/UV audit.",
            "Do not enable a normal map solely because its filename looks plausible.",
            "The preview stage configures the current default (Untitled) editor level in place.",
        ],
    }


def build_execution_plan(config: dict, project_root: Path) -> dict:
    issues = validate_config(config, project_root)
    character_id = config.get("character", {}).get("id", "Unknown")
    paths = config.get("paths", {})
    artifact = resolve_path(project_root, paths.get("artifact_dir", f"Artifacts/{character_id}"))
    blender_manifest = artifact / "blender_manifest.json"
    material_map = resolve_path(project_root, paths.get("material_map", f"Artifacts/{character_id}/material_map.json"))
    audit = artifact / "source_audit.json"
    ue_audit = artifact / "ue_audit.json"
    mapping_ready = material_map.is_file()
    stages = [
        {"id": "source_audit", "status": "complete" if audit.is_file() else "ready", "output": str(audit)},
        {
            "id": "blender_prepare",
            "status": "complete" if blender_manifest.is_file() else "ready",
            "gate": "PMX imports with mesh, armature, material slots, UVs and morphs inventoried",
        },
        {
            "id": "semantic_mapping",
            "status": "complete" if mapping_ready else "blocked",
            "gate": "Every render slot has an approved profile and explicit texture bindings",
        },
        {"id": "ue_import", "status": "requires_live_audit" if mapping_ready and not ue_audit.is_file() else ("ready" if mapping_ready else "blocked")},
        {"id": "material_build", "status": "ready" if mapping_ready else "blocked"},
        {"id": "optional_features", "status": "ready" if mapping_ready else "blocked", "gate": "Run only after base materials compile and render"},
        {"id": "visual_validation", "status": "requires_live_audit" if mapping_ready else "blocked", "gate": "Use the default level, four light azimuths and fixed captures"},
        {"id": "acceptance", "status": "requires_live_audit" if mapping_ready else "blocked", "gate": "SM6 zero errors, no duplicate Fixed assets, report archived"},
    ]
    return {
        "schema": PLAN_SCHEMA,
        "generated_at": utc_now(),
        "character_id": character_id,
        "config_issues": issues,
        "stages": stages,
        "artifacts": {
            "source_audit": str(audit),
            "blender_manifest": str(blender_manifest),
            "material_map": str(material_map),
            "ue_audit": str(ue_audit),
        },
    }


TOON_OR_SPHERE_STEMS = {
    "toon01", "toon02", "toon03", "toon04", "toon05", "toon06", "toon07", "toon08",
    "toon09", "toon10", "stoon01", "stoon03", "skin", "hair-a", "socks2", "ssshine1",
    "ssshine2", "spa",
}
BASE_SUFFIX_RE = re.compile(r"(_da|_d|_basecolor|_albedo|_diffuse|_col)$")


def _texture_stem_map(blender_manifest: dict) -> dict[str, str]:
    stems: dict[str, str] = {}
    for relative in blender_manifest.get("textures", []) or []:
        stem = Path(relative).stem.casefold()
        stems.setdefault(stem, relative)
    return stems


def _material_records(blender_manifest: dict) -> dict[str, dict]:
    return {record.get("name"): record for record in blender_manifest.get("materials", []) or []}


def autofill_textures(slot_name: str, records: dict, stems: dict[str, str]) -> tuple[dict, list[str], str | None]:
    """Propose texture bindings for one slot from real references, for review.

    The result is always a *candidate*: ``profile`` stays ``unassigned`` so the
    map cannot build until a human or agent approves it.
    """
    evidence: list[str] = []
    textures = {role: None for role in ROLE_ORDER}
    record = records.get(slot_name)
    base_stem = None
    if record:
        for image in record.get("images", []) or []:
            stem = Path(image.get("path") or image.get("image") or "").stem.casefold()
            if not stem or stem in TOON_OR_SPHERE_STEMS:
                continue
            if stem.startswith("toon") or "_rmo" in stem or stem.endswith("_n") or stem.endswith(("_spc", "_orm")):
                continue
            base_stem = stem
            break
    if base_stem:
        textures["base_color"] = base_stem
        evidence.append(f"base_color from PMX material reference '{base_stem}'")
        prefix = BASE_SUFFIX_RE.sub("", base_stem)
        for stem in sorted(stems):
            if textures["normal"] is None and stem.startswith(prefix) and stem.endswith("_n"):
                textures["normal"] = stem
            if textures["rmo"] is None and stem.startswith(prefix) and ("_rmo" in stem or "_orm" in stem):
                textures["rmo"] = stem
            if textures["spec_mask"] is None and stem.startswith(prefix) and ("_spc" in stem or "spec" in stem):
                textures["spec_mask"] = stem
        for role in ("normal", "rmo", "spec_mask"):
            if textures[role]:
                evidence.append(f"{role} candidate '{textures[role]}' matched base prefix '{prefix}'")
    for stem in sorted(stems):
        if textures["toon_ramp"] is None and "toon" in stem:
            textures["toon_ramp"] = stem
        if textures["sphere_map"] is None and stem.endswith((".spa", ".sph")):
            textures["sphere_map"] = stem
    if textures["toon_ramp"]:
        evidence.append(f"toon ramp candidate '{textures['toon_ramp']}' (verify orientation)")
    if textures["sphere_map"]:
        evidence.append(f"sphere/matcap candidate '{textures['sphere_map']}' (opt-in; never an ordinary UV sample)")
    return textures, evidence, base_stem


def build_material_map_draft(config: dict, blender_manifest: dict) -> dict:
    """Create a review draft with auto-filled texture candidates.

    Profile and texture bindings are proposals only; ``profile`` stays
    ``unassigned`` and ``review_status`` stays ``blocked`` until approved.
    """
    records = _material_records(blender_manifest)
    stems = _texture_stem_map(blender_manifest)
    slots = []
    for mesh in blender_manifest.get("meshes", []):
        material_slots = mesh.get("material_slots")
        if material_slots is None:
            material_slots = [
                {"index": index, "material": name, "polygon_count": None}
                for index, name in enumerate(mesh.get("materials", []))
            ]
        for slot in material_slots:
            slot_name = slot.get("material")
            textures, evidence, base_stem = autofill_textures(slot_name, records, stems)
            overrides: dict = {}
            if not base_stem:
                record = records.get(slot_name) or {}
                diffuse = record.get("diffuse_color")
                if diffuse and len(diffuse) >= 3:
                    overrides = {"vectors": {"Tint": [float(diffuse[0]), float(diffuse[1]), float(diffuse[2]), 1.0]}}
                    evidence.append("solid colour candidate from PMX diffuse_color; no base texture")
                else:
                    evidence.append("no PMX base reference found; sample a solid colour via Tint, bind manually, or research the material")
            slots.append(
                {
                    "mesh": mesh.get("name"),
                    "slot_index": slot.get("index"),
                    "slot": slot_name,
                    "polygon_count": slot.get("polygon_count"),
                    "profile": "unassigned",
                    "suggested_profile": suggest_profile(slot_name, config),
                    "parent": None,
                    "textures": textures,
                    "uv_sets": {},
                    "alpha_mode": "review_required",
                    "two_sided": None,
                    "overrides": overrides,
                    "evidence": evidence,
                    "review_status": "blocked",
                }
            )
    return {
        "schema": MATERIAL_MAP_SCHEMA,
        "character_id": config["character"]["id"],
        "status": "draft_review_required",
        "generated_at": utc_now(),
        "profile_library": PROFILE_PRESETS_PATH,
        "source_audit": f"{config['paths']['artifact_dir']}/source_audit.json",
        "policies": {
            "automatic_texture_binding": False,
            "normal_requires_uv_evidence": True,
            "rmo_requires_channel_evidence": True,
            "unknown_slots_block_ue_build": True,
        },
        "slots": slots,
    }


def build_character_asset_names(config: dict, project_root: Path | None = None) -> dict:
    """Derive every UE/asset path for a character from its config."""
    character = config.get("character", {})
    character_id = character.get("id", "Character")
    paths = config.get("paths", {})
    ue_root = paths.get("ue_root", f"/Game/Characters/{character_id}").rstrip("/")
    artifact_rel = paths.get("artifact_dir", f"Artifacts/{character_id}")
    if project_root is not None:
        artifact = resolve_path(project_root, artifact_rel)
        material_map = resolve_path(project_root, paths.get("material_map", f"{artifact_rel}/material_map.json"))
    else:
        artifact = Path(artifact_rel)
        material_map = Path(paths.get("material_map", f"{artifact_rel}/material_map.json"))
    return {
        "character_id": character_id,
        "display_name": character.get("display_name", character_id),
        "ue_root": ue_root,
        "texture_root": f"{ue_root}/Textures",
        "mesh_root": f"{ue_root}/Mesh",
        "material_root": f"{ue_root}/Materials",
        "mesh_asset": f"SK_{character_id}",
        "master_asset": f"M_MMD_{character_id}_Master",
        "eye_add_asset": f"M_MMD_{character_id}_EyeAdd",
        "eye_multiply_asset": f"M_MMD_{character_id}_EyeMultiply",
        "glass_asset": f"M_MMD_{character_id}_Glass",
        "invisible_asset": f"M_MMD_{character_id}_PassInvisible",
        "bang_shadow_asset": f"M_MMD_{character_id}_BangShadow",
        "bang_overlay_asset": f"M_MMD_{character_id}_BangOverlay",
        "outline_asset": f"M_MMD_{character_id}_Outline",
        "cloth_asset": f"M_MMD_{character_id}_Cloth",
        "stocking_asset": f"M_MMD_{character_id}_Stocking",
        "rim_asset": f"M_MMD_{character_id}_DepthRim",
        "instance_prefix": f"MI_{character_id}",
        "artifact_dir": str(artifact),
        "fbx": str(artifact / f"{character_id}.fbx"),
        "manifest": str(artifact / "blender_manifest.json"),
        "material_map": str(material_map),
        "face_sdf": str(artifact / "SDF" / "final" / f"T_{character_id}_FaceSDF_RGBA.png"),
        "ue_build_report": str(artifact / "ue_build_report.json"),
        "ue_audit": str(artifact / "ue_audit.json"),
        "validation_report": str(artifact / "ue_validation.json"),
        "capture": str(artifact / "ue_validation.png"),
    }


def normalize_material_map(
    config: dict,
    material_map: dict,
    profile_presets: dict | None = None,
) -> dict:
    """Collapse v2 slot_groups and v3 slots into one canonical structure.

    The returned shape is schema-independent and is the single interface used
    by every Unreal-side builder and validator.
    """
    profiles: dict[str, dict] = {}
    if profile_presets:
        profiles.update(profile_presets.get("profiles", {}))
    profiles.update(material_map.get("profiles", {}) or {})

    slots: list[dict] = []

    def add_slot(slot_name, profile, textures, uv_sets=None, alpha_mode=None, parent=None, evidence=None, overrides=None):
        if not slot_name:
            return
        slots.append(
            {
                "slot": str(slot_name),
                "profile": profile or "unassigned",
                "textures": {role: textures.get(role) for role in ROLE_ORDER},
                "uv_sets": uv_sets or {},
                "alpha_mode": alpha_mode or "review_required",
                "parent": parent,
                "overrides": dict(overrides or {}),
                "evidence": list(evidence or []),
            }
        )

    for group in material_map.get("slot_groups", []) or []:
        textures = {
            "base_color": group.get("base"),
            "normal": group.get("normal"),
            "rmo": group.get("rmo"),
            "spec_mask": group.get("detail_mask"),
            "opacity_mask": group.get("opacity_mask"),
            "toon_ramp": group.get("source_toon"),
            "sphere_map": group.get("source_sphere"),
            "face_sdf": group.get("face_sdf"),
        }
        for slot_name in group.get("slots", []) or []:
            add_slot(slot_name, group.get("profile"), textures, parent=group.get("parent"), overrides=group.get("overrides"))

    for entry in material_map.get("slots", []) or []:
        declared = dict(entry.get("textures") or {})
        for role in ROLE_ORDER:
            if declared.get(role) is None and entry.get(role) is not None:
                declared[role] = entry.get(role)
        add_slot(
            entry.get("slot") or entry.get("material"),
            entry.get("profile"),
            declared,
            entry.get("uv_sets"),
            entry.get("alpha_mode"),
            entry.get("parent"),
            entry.get("evidence"),
            entry.get("overrides"),
        )

    defaults: dict[str, str | None] = {}
    for role in ROLE_ORDER:
        defaults[role] = next(
            (slot["textures"].get(role) for slot in slots if slot["textures"].get(role)), None
        )

    return {
        "character_id": config.get("character", {}).get("id"),
        "schema": material_map.get("schema"),
        "profiles": profiles,
        "slots": slots,
        "defaults": defaults,
        "specials": material_map.get("specials", {}) or {},
        "policies": material_map.get("policies", {}) or {},
    }


def validate_material_map(normalized: dict) -> list[dict]:
    issues: list[dict] = []

    def issue(level, code, message):
        issues.append({"level": level, "code": code, "message": message})

    if not normalized.get("slots"):
        issue("error", "no_slots", "material map resolved to zero slots")
    seen = set()
    profiles = normalized.get("profiles", {})
    allow_plain = {"glass", "emotion", "hidden"}
    for slot in normalized.get("slots", []):
        name = slot["slot"]
        if name in seen:
            issue("error", "duplicate_slot", f"slot appears more than once: {name}")
        seen.add(name)
        profile = slot.get("profile")
        if profile in (None, "unassigned"):
            issue("error", "unassigned_profile", f"slot {name!r} has no approved profile")
        elif profile not in profiles:
            issue("error", "unknown_profile", f"slot {name!r} uses undefined profile {profile!r}")
        if not slot["textures"].get("base_color") and profile not in allow_plain:
            issue("warning", "missing_base", f"slot {name!r} has no base color texture")
    for role in ("normal", "rmo", "spec_mask"):
        for slot in normalized.get("slots", []):
            if slot["textures"].get(role) and not slot["textures"].get("base_color"):
                issue("warning", "orphan_detail", f"slot {slot['slot']!r} has {role} without base color")
    return issues
