"""Shared Unreal-side context and helpers for the generic MMD2UE build.

Every Unreal builder module imports this.  It resolves a character config into
derived asset names, normalises the material map, imports the FBX and texture
package, and exposes small material-graph helpers.  No character-specific
texture name or slot name appears here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import unreal
from material_input_policy import neutral_png

FRAMEWORK_DIR = Path(__file__).resolve().parent
if str(FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_DIR))

from mmd2ue_core import (  # noqa: E402
    PROFILE_PRESETS_PATH,
    ROLE_ORDER,
    TEXTURE_PARAMETER_NAMES,
    build_character_asset_names,
    normalize_material_map,
    project_root_from,
    read_json,
    resolve_path,
    validate_material_map,
)

NORMAL_TOKENS = ("_normal", "normalmap", "_nrm", "_nor")
NORMAL_SUFFIXES = ("_n.png", "_n.tga", "_n.tif", "_normal.png")
MASK_TOKENS = ("_rmo", "_orm", "_spc", "_mask", "facesdf", "face_sdf", "_sdf")
SPHERE_SUFFIXES = (".spa", ".sph")


class BuildError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(unreal.Paths.project_dir()).resolve()


def safe_set(obj, name: str, value) -> bool:
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception:
        try:
            setattr(obj, name, value)
            return True
        except Exception:
            return False


def asset_exists(path: str) -> bool:
    return unreal.EditorAssetLibrary.does_asset_exist(path)


def load(path: str):
    return unreal.EditorAssetLibrary.load_asset(path)


def mkdir(path: str) -> None:
    if path:
        unreal.EditorAssetLibrary.make_directory(path)


def import_one(filename: Path, destination: str, options=None, destination_name: str | None = None):
    task = unreal.AssetImportTask()
    task.filename = str(filename)
    task.destination_path = destination
    task.automated = True
    task.replace_existing = False
    task.save = True
    if destination_name:
        safe_set(task, "destination_name", destination_name)
    if options is not None:
        task.options = options
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = getattr(task, "imported_object_paths", []) or []
    return [asset for asset in (load(path) for path in paths) if asset]


def expression(material, cls, x: int, y: int):
    node = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    if node is None:
        raise BuildError(f"failed to create material expression {getattr(cls, '__name__', cls)}")
    return node


def connect(source, output: str, target, input_name: str) -> None:
    if not unreal.MaterialEditingLibrary.connect_material_expressions(source, output, target, input_name):
        query = getattr(unreal.MaterialEditingLibrary, "get_material_expression_input_names", None)
        try:
            actual_inputs = list(map(str, query(target))) if callable(query) else "API unavailable"
        except Exception as error:
            actual_inputs = "query failed: " + str(error)
        raise BuildError(
            f"failed to connect {source.get_class().get_name()}[{output or 'default'}] "
            f"-> {target.get_class().get_name()}[{input_name or 'default'}]; "
            f"actual_inputs={actual_inputs}; engine={unreal.SystemLibrary.get_engine_version()}. "
            "Inspect this node's API before adapting its pin or using a mathematically equivalent graph."
        )


def connect_property(source, output: str, prop) -> None:
    if not unreal.MaterialEditingLibrary.connect_material_property(source, output, prop):
        raise BuildError(
            f"failed to connect {source.get_class().get_name()}[{output or 'default'}] to {prop}"
        )


def sampler_type(name: str):
    enum = getattr(unreal, "MaterialSamplerType", None)
    if not enum:
        return None
    for candidate in (name, name.upper(), name.lower()):
        if hasattr(enum, candidate):
            return getattr(enum, candidate)
    return None


def scalar(material, name: str, default, x: int, y: int):
    node = expression(material, unreal.MaterialExpressionScalarParameter, x, y)
    safe_set(node, "parameter_name", name)
    safe_set(node, "default_value", default)
    return node


def vector(material, name: str, rgba, x: int, y: int):
    node = expression(material, unreal.MaterialExpressionVectorParameter, x, y)
    safe_set(node, "parameter_name", name)
    safe_set(node, "default_value", unreal.LinearColor(*rgba))
    return node


def texture_parameter(material, name: str, default_texture, x: int, y: int, sampler=None):
    if not isinstance(default_texture, unreal.Texture2D):
        raise BuildError(f"Texture parameter {name} requires a real default Texture2D, even when its branch is optional")
    node = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    properties = {"parameter_name": name, "texture": default_texture}
    if sampler is not None:
        properties["sampler_type"] = sampler
    for key, value in properties.items():
        if not safe_set(node, key, value):
            raise BuildError(f"Cannot configure texture parameter {name}.{key}; inspect engine API")
    return node


def constant3(material, rgba, x: int, y: int):
    node = expression(material, unreal.MaterialExpressionConstant3Vector, x, y)
    safe_set(node, "constant", unreal.LinearColor(*rgba))
    return node


def component_mask(material, source, output: str, channels: str, x: int, y: int):
    node = expression(material, unreal.MaterialExpressionComponentMask, x, y)
    for channel in "rgba":
        safe_set(node, channel, channel in channels)
    connect(source, output, node, "")
    return node


def smooth_threshold(material, value, threshold, softness, x: int, y: int, marker: str = ""):
    """Hermite smoothstep(value, threshold-softness, threshold+softness)."""
    edge_min = expression(material, unreal.MaterialExpressionSubtract, x, y)
    if marker:
        safe_set(edge_min, "desc", marker)
    connect(threshold, "", edge_min, "A")
    connect(softness, "", edge_min, "B")
    delta = expression(material, unreal.MaterialExpressionSubtract, x + 220, y)
    connect(value, "", delta, "A")
    connect(edge_min, "", delta, "B")
    span = expression(material, unreal.MaterialExpressionMultiply, x, y + 100)
    connect(softness, "", span, "A")
    safe_set(span, "const_b", 2.0)
    normalized = expression(material, unreal.MaterialExpressionDivide, x + 440, y)
    connect(delta, "", normalized, "A")
    connect(span, "", normalized, "B")
    t = expression(material, unreal.MaterialExpressionSaturate, x + 660, y)
    connect(normalized, "", t, "")
    t_squared = expression(material, unreal.MaterialExpressionMultiply, x + 880, y)
    connect(t, "", t_squared, "A")
    connect(t, "", t_squared, "B")
    two_t = expression(material, unreal.MaterialExpressionMultiply, x + 880, y + 100)
    connect(t, "", two_t, "A")
    safe_set(two_t, "const_b", 2.0)
    hermite_tail = expression(material, unreal.MaterialExpressionSubtract, x + 1100, y + 100)
    safe_set(hermite_tail, "const_a", 3.0)
    connect(two_t, "", hermite_tail, "B")
    result = expression(material, unreal.MaterialExpressionMultiply, x + 1320, y)
    connect(t_squared, "", result, "A")
    connect(hermite_tail, "", result, "B")
    return result


def stencil_equal(material, stencil_value: float, x: int, y: int):
    """Return 1 only where CustomStencil equals stencil_value."""
    scene_stencil = expression(material, unreal.MaterialExpressionSceneTexture, x, y)
    safe_set(scene_stencil, "scene_texture_id", unreal.SceneTextureId.PPI_CUSTOM_STENCIL)
    r = component_mask(material, scene_stencil, "Color", "r", x + 220, y)
    delta = expression(material, unreal.MaterialExpressionSubtract, x + 440, y)
    connect(r, "", delta, "A")
    safe_set(delta, "const_b", stencil_value)
    absolute = expression(material, unreal.MaterialExpressionAbs, x + 660, y)
    connect(delta, "", absolute, "")
    saturated = expression(material, unreal.MaterialExpressionSaturate, x + 880, y)
    connect(absolute, "", saturated, "")
    one_minus = expression(material, unreal.MaterialExpressionOneMinus, x + 1100, y)
    connect(saturated, "", one_minus, "")
    return one_minus


def reset_expressions(material) -> None:
    """Remove every node; UE 5.8 can retain nodes after the bulk delete."""
    try:
        unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    except Exception:
        pass
    try:
        for old in list(unreal.MaterialEditingLibrary.get_material_expressions(material)):
            unreal.MaterialEditingLibrary.delete_material_expression(material, old)
    except Exception:
        pass
    if unreal.MaterialEditingLibrary.get_num_material_expressions(material) != 0:
        raise BuildError(f"legacy expressions could not be removed from {material.get_path_name()}")


def load_or_create_material(asset_name: str, material_root: str, fresh: bool = False):
    path = f"{material_root}/{asset_name}"
    material = load(path) if asset_exists(path) else None
    if material is None:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name, material_root, unreal.Material, unreal.MaterialFactoryNew()
        )
    if material is None:
        raise BuildError(f"failed to create material {path}")
    if not isinstance(material, unreal.Material):
        raise BuildError(f"{path} exists but is not a UMaterial")
    if fresh:
        reset_expressions(material)
    return material


def configure_texture(texture, filename: Path, role: str | None = None) -> None:
    """Prefer the reviewed texture role; filenames are only a fallback."""
    name = Path(filename).name.lower()
    desired = {}
    if role in {"base_color", "sphere_map", "toon_ramp"}:
        desired = {"srgb": True, "compression_settings": unreal.TextureCompressionSettings.TC_DEFAULT}
    elif role == "normal" or (role is None and (name.endswith(NORMAL_SUFFIXES) or any(token in name for token in NORMAL_TOKENS))):
        desired = {"srgb": False, "compression_settings": unreal.TextureCompressionSettings.TC_NORMALMAP}
    elif role in {"rmo", "spec_mask", "opacity_mask", "face_sdf"} or (role is None and any(token in name for token in MASK_TOKENS)):
        desired = {"srgb": False, "compression_settings": unreal.TextureCompressionSettings.TC_MASKS}
    else:
        # Base colour, sphere/matcap (.spa/.sph) and generic images are colour.
        desired = {"srgb": True}
    changed = False
    for property_name, value in desired.items():
        try:
            current = texture.get_editor_property(property_name)
        except Exception:
            current = None
        if current != value:
            changed = safe_set(texture, property_name, value) or changed
    if changed:
        unreal.EditorAssetLibrary.save_loaded_asset(texture)


class BuildContext:
    """Resolves config, manifest, normalized material map and imported assets."""

    def __init__(self, config_path: str | os.PathLike | None = None, variant: str = "", strict: bool = True, require_map: bool = True):
        self.root = project_root()
        raw_config = config_path or os.environ.get("MMD2UE_CHARACTER_CONFIG")
        if not raw_config:
            raise BuildError("MMD2UE_CHARACTER_CONFIG or --config is required")
        self.config_path = resolve_path(self.root, str(raw_config))
        self.config = read_json(self.config_path)
        self.variant = (variant or os.environ.get("MMD2UE_ASSET_VARIANT", "")).strip().lstrip("_")
        self.suffix = f"_{self.variant}" if self.variant else ""
        self.names = build_character_asset_names(self.config, self.root)
        if self.suffix:
            for key in (
                "mesh_asset", "master_asset", "eye_add_asset", "eye_multiply_asset",
                "glass_asset", "invisible_asset", "bang_shadow_asset", "bang_overlay_asset",
                "outline_asset", "cloth_asset", "stocking_asset", "rim_asset", "instance_prefix",
            ):
                self.names[key] = self.names[key] + self.suffix
        self.manifest = self._load_optional(self.names["manifest"])
        material_map = self._load_optional(self.names["material_map"])
        if material_map is None:
            if require_map:
                raise BuildError(f"material map not found: {self.names['material_map']}")
            material_map = {"schema": "mmd2ue.material-map.v3", "profiles": {}, "slots": []}
        presets = self._load_optional(str(self.root / PROFILE_PRESETS_PATH)) or {"profiles": {}}
        self.material_map = normalize_material_map(self.config, material_map, presets)
        self.map_issues = validate_material_map(self.material_map)
        if strict and any(issue["level"] == "error" for issue in self.map_issues):
            raise BuildError(f"material map is not approved: {self.map_issues}")
        self.texture_map: dict[str, object] = {}
        self.imported = False
        self.input_audit = []
        self.material_debt = []
        self._neutrals = {}

    # -- paths ---------------------------------------------------------------
    def artifact(self) -> Path:
        return Path(self.names["artifact_dir"])

    def report_path(self, name: str) -> Path:
        return self.artifact() / name

    def _load_optional(self, path: str | None):
        if not path:
            return None
        candidate = Path(path)
        return read_json(candidate) if candidate.is_file() else None

    # -- slots ---------------------------------------------------------------
    def slot_entries(self) -> list[dict]:
        return self.material_map.get("slots", [])

    def slot_names(self) -> list[str]:
        return [entry["slot"] for entry in self.slot_entries()]

    def manifest_slot_names(self) -> list[str]:
        if not self.manifest:
            return []
        return [name for record in self.manifest.get("meshes", []) for name in record.get("materials", [])]

    def require_manifest(self) -> dict:
        if not self.manifest:
            raise BuildError(f"blender manifest not found: {self.names['manifest']}")
        return self.manifest

    def check_coverage(self) -> None:
        manifest_slots = self.manifest_slot_names()
        mapped = self.slot_names()
        if len(mapped) != len(set(mapped)):
            raise BuildError("material map contains duplicate slot assignments")
        if manifest_slots and set(manifest_slots) != set(mapped):
            missing = sorted(set(manifest_slots) - set(mapped))
            extra = sorted(set(mapped) - set(manifest_slots))
            raise BuildError(f"material map coverage mismatch: missing={missing} extra={extra}")

    # -- textures ------------------------------------------------------------
    def import_textures(self, read_only=False) -> dict[str, object]:
        if not read_only:
            mkdir(self.names["texture_root"])
        texture_map: dict[str, object] = {}
        reused = self.config.get("pmx4ue", {}).get("material_texture_assets", {})
        for key, path in reused.items():
            if not isinstance(key, str) or key.lower() in texture_map:
                raise BuildError(f"Invalid/duplicate reused texture key: {key}")
            texture = load(path)
            if not isinstance(texture, unreal.Texture2D):
                raise BuildError(f"Missing explicitly reused texture: {key} = {path}")
            texture_map[key.lower()] = texture  # Never reconfigure shared assets.
        declared_roles: dict[str, str] = {}
        for entry in self.slot_entries():
            for role, key in entry.get("textures", {}).items():
                if not key:
                    continue
                texture_key = str(key).lower()
                old = declared_roles.get(texture_key)
                if old is None or role == "base_color":
                    declared_roles[texture_key] = role
        texture_dir = self.artifact() / "textures"
        seen = set()
        for filename in sorted((p for p in texture_dir.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            key = filename.stem.lower()
            if key in seen:
                continue
            seen.add(key)
            if key in texture_map:
                continue
            asset_path = f"{self.names['texture_root']}/{filename.stem}"
            texture = load(asset_path) if asset_exists(asset_path) else None
            if texture is None and not read_only:
                imported = import_one(filename, self.names["texture_root"], destination_name=filename.stem)
                texture = imported[0] if imported else load(asset_path)
            if texture:
                if not read_only:
                    configure_texture(texture, filename, declared_roles.get(key))
                texture_map[key] = texture
        face_sdf = Path(self.names["face_sdf"])
        if face_sdf.is_file() and face_sdf.stem.lower() not in texture_map:
            sdf_asset_path = f"{self.names['texture_root']}/{face_sdf.stem}"
            texture = load(sdf_asset_path) if asset_exists(sdf_asset_path) else None
            if texture is None and not read_only:
                imported = import_one(face_sdf, self.names["texture_root"], destination_name=face_sdf.stem)
                texture = imported[0] if imported else load(sdf_asset_path)
            if texture:
                if not read_only:
                    configure_texture(texture, face_sdf, "face_sdf")
                texture_map[face_sdf.stem.lower()] = texture
        self.texture_map = texture_map
        self.imported = True
        return texture_map

    def texture_for(self, key: str | None):
        if not key:
            return None
        return self.texture_map.get(str(key).lower())

    def default_texture(self, role: str):
        return self.neutral_texture(role)

    def neutral_texture(self, role, create=True):
        if role in self._neutrals:
            return self._neutrals[role]
        name = "T_PMX4UE_Neutral_" + role
        path = f"{self.names['texture_root']}/Defaults/{name}"
        texture = load(path) if asset_exists(path) else None
        if texture is None and create:
            source = self.artifact() / "material_defaults" / (name + ".png")
            source.parent.mkdir(parents=True, exist_ok=True)
            data = neutral_png(role)
            if source.exists() and source.read_bytes() != data:
                raise BuildError(f"Neutral input changed unexpectedly: {source}")
            if not source.exists():
                source.write_bytes(data)
            imported = import_one(source, f"{self.names['texture_root']}/Defaults", destination_name=name)
            texture = imported[0] if imported else load(path)
            if texture:
                configure_texture(texture, source, role)
        if not isinstance(texture, unreal.Texture2D):
            raise BuildError(f"Typed neutral texture missing: {path}")
        self._neutrals[role] = texture
        return texture

    def engine_default_texture(self):
        for engine_path in ("/Engine/EngineResources/WhiteSquareTexture", "/Engine/EngineResources/DefaultTexture"):
            fallback = load(engine_path)
            if fallback is not None:
                return fallback
        return None

    # -- special parents -----------------------------------------------------
    def special_kind_for_slot(self, slot_name: str) -> str | None:
        specials = self.material_map.get("specials", {}) or {}
        for kind, slots in specials.items():
            if isinstance(slots, (list, tuple)) and slot_name in slots:
                return kind
        for entry in self.slot_entries():
            if entry["slot"] == slot_name and entry.get("parent"):
                return entry["parent"]
        # Infer a special parent from the approved profile and the slot identity
        # so layered eyes/effects work without hand-written specials.
        entry = next((item for item in self.slot_entries() if item["slot"] == slot_name), None)
        profile = (entry or {}).get("profile")
        name = slot_name.casefold()
        if profile == "glass":
            return "glass"
        if profile == "hidden":
            return "invisible"
        if profile in ("effect", "additive"):
            return "additive"
        if profile == "eye_overlay":
            return "eye_multiply" if ("shadow" in name or "multiply" in name) else "eye_add"
        return None

    # -- mesh import ---------------------------------------------------------
    def fbx_options(self):
        options = unreal.FbxImportUI()
        for name, value in (
            ("automated_import_should_detect_type", False),
            ("import_mesh", True),
            ("import_as_skeletal", True),
            ("import_morph_targets", True),
            ("import_animations", False),
            ("import_materials", False),
            ("import_textures", False),
        ):
            safe_set(options, name, value)
        safe_set(options, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
        skeletal = getattr(options, "skeletal_mesh_import_data", None)
        if skeletal:
            for name, value in (("import_uniform_scale", 1.0), ("convert_scene_unit", False)):
                if not safe_set(skeletal, name, value):
                    raise BuildError(f"Cannot enforce centimeter import contract: {name}")
            for name, value in (
                ("import_morph_targets", True),
                ("preserve_smoothing_groups", True),
                ("import_meshes_in_bone_hierarchy", True),
                ("update_skeleton_reference_pose", True),
            ):
                safe_set(skeletal, name, value)
        return options

    def import_skeletal_mesh(self):
        mkdir(self.names["mesh_root"])
        fbx = Path(self.names["fbx"])
        if not fbx.is_file():
            raise BuildError(f"FBX not found: {fbx}")
        asset_path = f"{self.names['mesh_root']}/{self.names['mesh_asset']}"
        assets = import_one(fbx, self.names["mesh_root"], self.fbx_options(), self.names["mesh_asset"])
        mesh = next((asset for asset in assets if isinstance(asset, unreal.SkeletalMesh)), None)
        if mesh is None:
            mesh = load(asset_path)
        if not isinstance(mesh, unreal.SkeletalMesh):
            raise BuildError(f"FBX import produced no SkeletalMesh at {asset_path}")
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        return mesh
