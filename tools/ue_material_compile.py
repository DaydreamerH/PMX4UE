"""Read/compile materials from the validation report, no asset save or level edits."""
import json
import os
from pathlib import Path
import unreal
from ue_bridge import resolve, checked

def compile_parents(paths, output):
    output = Path(output)
    if output.exists() or not paths:
        raise ValueError("Need material parents and a new output")
    masters = {}
    for path in paths:
        material = unreal.load_asset(path)
        visited = set()
        while isinstance(material, unreal.MaterialInstance):
            if material.get_path_name() in visited:
                raise ValueError('Material parent cycle')
            visited.add(material.get_path_name())
            material = material.get_editor_property('parent')
        if not isinstance(material, unreal.Material):
            raise ValueError('Missing material master: '+path)
        masters[material.get_path_name()] = material
    api = resolve("materials")
    results = {p: checked(api.inspect_material_compile(p)) for p in masters}
    report = dict(status="compiled_visual_pending" if all(r.get("ok") is True for r in results.values()) else "failed", results=results)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    if report["status"] == "failed":
        raise RuntimeError("Material shader compile failed")
    return report


if __name__ == '__main__':
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8"))
    validation = json.loads((Path(config["paths"]["artifact_dir"])/"ue_validation.json").read_text(encoding="utf-8"))
    if validation.get('schema') != 'mmd2ue.ue-validation.v1' or validation.get('passed') is not True:
        raise ValueError('Need a passed current ue-validate report; legacy reports are not interchangeable')
    compile_parents(validation['compile_check_required'], os.environ['PMX4UE_OUTPUT'])
