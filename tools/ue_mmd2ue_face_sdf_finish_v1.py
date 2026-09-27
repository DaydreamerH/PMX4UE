"""Resume only the recorded SDFHead_v1 experiment, preserving its first failure report."""
import hashlib
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
folder = project / "Saved/PMX4UE/SDFHead_v1"
report = json.loads((folder / "build.json").read_text(encoding="utf-8"))
out = folder / os.environ.get("SDF_TEST_REPORT", "runtime_v2.json")
assert not out.exists()
dest = "/Game/Characters/TololoSchool1001/PhysicsSandbox/Materials/SDFHead_v1"

def digest(path):
    return hashlib.sha256((project/'Content'/(path.split('.')[0].removeprefix('/Game/')+'.uasset')).read_bytes()).hexdigest()

assert all(digest(p)==h for p,h in report["input_hashes"].items())
face = unreal.load_asset(dest+"/MI_Face_HeadDriven")
lib = unreal.MaterialEditingLibrary
f = lib.get_material_instance_vector_parameter_value(face,"FaceForwardWS")
l = lib.get_material_instance_vector_parameter_value(face,"FaceLeftWS")
fv,lv = unreal.Vector(f.r,f.g,f.b),unreal.Vector(l.r,l.g,l.b)
report["status"] = "running"
try:
    report["runtime_tests"] = json.loads(unreal.MMD2UEFaceSDFTools.test_face_sdf(
        report["mesh"],report["animation"],face.get_path_name(),"Head",fv,lv))
    assert report["runtime_tests"]["passed"], report["runtime_tests"]
    bp_path=dest+"/BP_Tololo_HeadSDF"
    assert not unreal.EditorAssetLibrary.does_asset_exist(bp_path)
    factory=unreal.BlueprintFactory()
    factory.set_editor_property("parent_class",unreal.MMDFaceSDFPreviewActor)
    bp=unreal.AssetToolsHelpers.get_asset_tools().create_asset("BP_Tololo_HeadSDF",dest,unreal.Blueprint,factory)
    assert bp
    cdo=unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("preview_mesh",unreal.load_asset(report["mesh"]))
    cdo.set_editor_property("preview_anim_class",unreal.load_asset(report["physics_abp"]).generated_class())
    cdo.set_editor_property("face_material",face)
    driver=cdo.get_editor_property("face_sdf")
    driver.set_editor_property("head_bone","Head")
    driver.set_editor_property("reference_forward",fv)
    driver.set_editor_property("reference_left",lv)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    assert unreal.EditorAssetLibrary.save_loaded_asset(bp)
    report.update(status="runtime_pass_visual_pending",actor=bp_path,face=face.get_path_name(),head_bone="Head",
                  reference_forward=[fv.x,fv.y,fv.z],reference_left=[lv.x,lv.y,lv.z])
    report["input_assets_unchanged"]=all(digest(p)==h for p,h in report["input_hashes"].items())
    assert report["input_assets_unchanged"]
except Exception as e:
    report.update(status="failed", error=str(e))
    raise
finally:
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
