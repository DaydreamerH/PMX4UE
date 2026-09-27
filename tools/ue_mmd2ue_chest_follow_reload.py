"""Fresh-process, read-only reload of ChestFollow_v1. No simulation/rendering."""
import hashlib
import json
from pathlib import Path
import unreal

def main():
    project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    folder = project / "Saved/PMX4UE/ChestFollow_v1"
    output = folder / "reload.json"
    assert not output.exists()
    build = json.loads((folder / "build.json").read_text(encoding="utf-8"))
    for path, expected in {**build["source_hashes"], **build["output_hashes"]}.items():
        filename = project / "Content" / (path.split('.')[0].removeprefix('/Game/') + '.uasset')
        assert hashlib.sha256(filename.read_bytes()).hexdigest() == expected
    source = unreal.load_asset(build["source_physics"])
    candidate = unreal.load_asset(build["physics_asset"])
    assert source and candidate
    a = json.loads(unreal.MMD2UEPhysicsTools.inspect_body_physics_asset(build["source_physics"]))
    b = json.loads(unreal.MMD2UEPhysicsTools.inspect_body_physics_asset(build["physics_asset"]))
    assert a.pop("asset") and b.pop("asset")
    assert a == b
    assert source.get_editor_property("solver_settings").export_text() == candidate.get_editor_property("solver_settings").export_text()
    assert unreal.EditorAssetLibrary.load_blueprint_class(build["asset"])
    result = dict(status="fresh_reload_static_checks_passed_visual_pending", asset=build["asset"],
                  source_and_output_hashes_unchanged=True, geometry_and_constraint_counts_equal=True,
                  solver_equal=True, blueprint_class_loaded=True, simulation_tested=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log("CHEST_FOLLOW_RELOAD_OK")

main()
