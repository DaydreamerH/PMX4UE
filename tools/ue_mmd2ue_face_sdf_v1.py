"""Build an isolated Tololo face-material + animated actor variant; never save user levels."""
import hashlib
import json
import sys
from pathlib import Path
import unreal
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_face_sdf_runtime import add_runtime_basis

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert (project / "MMD2UE.uproject").is_file()
root = "/Game/Characters/TololoSchool1001/PhysicsSandbox/"
dest = root + "Materials/SDFHead_v1"
output = project / "Saved/PMX4UE/SDFHead_v1/build.json"
assert not output.exists() and not unreal.EditorAssetLibrary.does_directory_exist(dest), "Use a new version"
mesh_path = root + "SK_TololoSchool1001_UpperOnlyCm_v1"
abp_path = root + "Performance/ChestFollow_v1/ABP_ChestFollow_Travel"
clip_path = root + "Animations/M_Neutral_Walk_Loop_F"
mesh = unreal.load_asset(mesh_path)
abp = unreal.load_asset(abp_path)
assert mesh and abp
slots = list(mesh.get_editor_property("materials"))
faces = [m.material_interface for m in slots if str(m.material_slot_name) == "Face"]
assert len(faces) == 1
source_face = faces[0]
source_master = source_face
while isinstance(source_master, unreal.MaterialInstance):
    source_master = source_master.get_editor_property("parent")
assert isinstance(source_master, unreal.Material)

def digest(path):
    path = str(path).split('.')[0].removeprefix('/Game/')
    return hashlib.sha256((project / 'Content' / (path+'.uasset')).read_bytes()).hexdigest()

sources = [mesh_path, abp_path, clip_path, source_face.get_path_name(), source_master.get_path_name()]
hashes = {p:digest(p) for p in sources}
lib = unreal.MaterialEditingLibrary
forward = lib.get_material_instance_vector_parameter_value(source_face, "FaceForwardWS")
left = lib.get_material_instance_vector_parameter_value(source_face, "FaceLeftWS")
fv = unreal.Vector(forward.r,forward.g,forward.b)
lv = unreal.Vector(left.r,left.g,left.b)
report = dict(status="building", input_hashes=hashes, mesh=mesh_path, animation=clip_path, physics_abp=abp_path)
output.parent.mkdir(parents=True, exist_ok=True)
try:
    master = unreal.EditorAssetLibrary.duplicate_asset(source_master.get_path_name(), dest+"/M_Face_HeadDriven")
    assert master
    report["contract"] = add_runtime_basis(master)
    assert unreal.EditorAssetLibrary.save_loaded_asset(master)
    face = unreal.EditorAssetLibrary.duplicate_asset(source_face.get_path_name(), dest+"/MI_Face_HeadDriven")
    assert face
    lib.set_material_instance_parent(face, master)
    assert unreal.EditorAssetLibrary.save_loaded_asset(face)
    report["compile"] = json.loads(unreal.MMD2UEAgentMCPTools.inspect_material_compile(master.get_path_name()))
    assert report["compile"]["ok"], report["compile"]
    report["runtime_tests"] = json.loads(unreal.MMD2UEFaceSDFTools.test_face_sdf(
        mesh_path,clip_path,face.get_path_name(),"Head",fv,lv))
    assert report["runtime_tests"]["passed"], report["runtime_tests"]
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class",unreal.MMDFaceSDFPreviewActor)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset("BP_Tololo_HeadSDF",dest,unreal.Blueprint,factory)
    assert bp
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("preview_mesh",mesh)
    cdo.set_editor_property("preview_anim_class",abp.generated_class())
    cdo.set_editor_property("face_material",face)
    driver = cdo.get_editor_property("face_sdf")
    driver.set_editor_property("head_bone","Head")
    driver.set_editor_property("reference_forward",fv)
    driver.set_editor_property("reference_left",lv)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)
    report.update(status="runtime_pass_visual_pending", master=master.get_path_name(), face=face.get_path_name(),
                  actor=bp.get_path_name(), head_bone="Head", reference_forward=[fv.x,fv.y,fv.z],reference_left=[lv.x,lv.y,lv.z])
    report["input_assets_unchanged"] = all(digest(p)==h for p,h in hashes.items())
    assert report["input_assets_unchanged"]
finally:
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
