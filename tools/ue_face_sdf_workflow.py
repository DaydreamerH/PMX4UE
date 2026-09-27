"""Versioned face SDF stage; copies assets, never changes a source mesh or level."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_sdf_profile import validate_profile
from ue_face_sdf_runtime import add_runtime_basis


def run():
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8-sig"))
    profile = validate_profile(json.loads(Path(os.environ["PMX4UE_FACE_SDF_PROFILE"]).read_text(
        encoding="utf-8-sig")), config["paths"]["ue_root"])
    project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    if project != Path(config["pmx4ue"]["project"]).resolve().parent:
        raise RuntimeError("Wrong project")
    output = Path(os.environ["PMX4UE_OUTPUT"])
    if output.exists():
        raise RuntimeError("Report already exists; choose a new run/version")
    lib, assets = unreal.MaterialEditingLibrary, unreal.EditorAssetLibrary
    dest = profile["destination"]
    if assets.does_directory_exist(dest) or assets.does_asset_exist(dest):
        raise RuntimeError("Destination is occupied; preserve it and use a new version")
    native = ("MMDFaceSDFPreviewActor", "MMD2UEAgentMCPTools") if profile["provider"] == "mmd2ue" else (
        "PMX4UEFaceSDFPreviewActor", "PMX4UEAgentMCPTools")
    actor_class, compile_tools = (getattr(unreal, n, None) for n in native)
    if actor_class is None or compile_tools is None or not hasattr(compile_tools, "inspect_material_compile"):
        raise RuntimeError("Compile/reload the selected native SDF provider first; materials alone are insufficient")
    mesh = unreal.load_asset(profile["mesh"])
    if not isinstance(mesh, unreal.SkeletalMesh):
        raise ValueError("mesh is not a SkeletalMesh")
    # A transient component provides bone lookup without touching a level or the mesh asset.
    probe = unreal.new_object(unreal.SkeletalMeshComponent)
    probe.set_skeletal_mesh_asset(mesh)
    if probe.get_bone_index(profile["head_bone"]) < 0:
        raise ValueError("Reviewed head bone does not exist in this mesh")
    faces = [m.material_interface for m in mesh.get_editor_property("materials")
             if str(m.material_slot_name) == profile["face_slot"]]
    if len(faces) != 1 or not isinstance(faces[0], unreal.MaterialInstanceConstant):
        raise ValueError("Expected exactly one face slot with a constant material instance")
    source_face = faces[0]
    chain, master = [], source_face
    while isinstance(master, unreal.MaterialInstanceConstant):
        if master in chain:
            raise ValueError("Cyclic material parent chain")
        chain.append(master)
        master = master.get_editor_property("parent")
    if not isinstance(master, unreal.Material):
        raise ValueError("Unsupported parent chain; adapt explicitly before building")
    abp = unreal.load_asset(profile["animation_blueprint"]) if profile.get("animation_blueprint") else None
    if profile.get("animation_blueprint") and (not isinstance(abp, unreal.AnimBlueprint) or
            abp.get_editor_property("target_skeleton") != mesh.get_editor_property("skeleton")):
        raise ValueError("Animation blueprint must use this mesh's skeleton")

    def digest(obj):
        package = obj.get_path_name().split(".")[0]
        if not package.startswith("/Game/"):
            raise ValueError("This adapter requires saved /Game input assets")
        return hashlib.sha256((project / "Content" / (package[6:] + ".uasset")).read_bytes()).hexdigest()

    sources = [mesh, master, *chain] + ([abp] if abp else [])
    hashes = {o.get_path_name(): digest(o) for o in sources}
    report = dict(status="building", profile=profile, input_hashes=hashes, created=[])
    output.parent.mkdir(parents=True, exist_ok=True)

    def duplicate(obj, name):
        copied = assets.duplicate_asset(obj.get_path_name(), dest + "/" + name)
        if not copied:
            raise RuntimeError(f"Could not duplicate {name}")
        report["created"].append(copied.get_path_name())
        return copied

    def save(obj):
        if not assets.save_loaded_asset(obj):
            raise RuntimeError(f"Could not save {obj.get_path_name()}")

    try:
        copied_master = duplicate(master, "M_Face_HeadDriven")
        report["contract"] = add_runtime_basis(copied_master)
        report["compile"] = json.loads(compile_tools.inspect_material_compile(copied_master.get_path_name()))
        if not report["compile"].get("ok"):
            raise RuntimeError("Shader compile failed; see report")
        save(copied_master)
        parent = copied_master
        # Preserve every inherited parameter/static switch, not just the leaf overrides.
        for index, original in enumerate(reversed(chain)):
            name = "MI_Face_HeadDriven" if original == source_face else f"MI_Face_Parent_{index}"
            copied = duplicate(original, name)
            lib.set_material_instance_parent(copied, parent)
            save(copied)
            parent = copied
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", actor_class)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset("BP_FaceSDF_Preview", dest, unreal.Blueprint, factory)
        if not bp:
            raise RuntimeError("Could not create preview blueprint")
        report["created"].append(bp.get_path_name())
        cdo = unreal.get_default_object(bp.generated_class())
        cdo.set_editor_property("preview_mesh", mesh)
        if abp:
            cdo.set_editor_property("preview_anim_class", abp.generated_class())
        cdo.set_editor_property("face_slot", profile["face_slot"])
        cdo.set_editor_property("face_material", parent)
        driver = cdo.get_editor_property("face_sdf")
        driver.set_editor_property("head_bone", profile["head_bone"])
        for key in ("reference_forward", "reference_left"):
            driver.set_editor_property(key, unreal.Vector(*profile[key]))
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        save(bp)
        report.update(status="built_needs_runtime_visual_review", actor=bp.get_path_name(),
                      runtime_accepted=False, visual_accepted=False,
                      pending=["actual animation/head turns", "actor rotation and multiple instances",
                               "missing bone/fallback", "LOD and visibility recovery", "packaged game"])
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["input_assets_unchanged"] = all(digest(o) == hashes[o.get_path_name()] for o in sources)
        if not report["input_assets_unchanged"]:
            report.update(status="failed", error="Protected source fingerprint changed")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if not report["input_assets_unchanged"]:
        raise RuntimeError("Protected source fingerprint changed")


if __name__ == "__main__":
    run()
