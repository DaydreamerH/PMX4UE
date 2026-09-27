"""Small engine/sampler probe before a full character build. No user level edits.

Not a character shader or visual acceptance test. Retain this result only for
the same engine/tool sources; runner records contain code hashes.
"""
import json
import os
from pathlib import Path
import unreal
from ue_context import (BuildContext, BuildError, load_or_create_material,
                        texture_parameter, sampler_type, connect, connect_property, expression)
from ue_bridge import resolve, checked
from material_input_policy import NEUTRALS


def main():
    config = json.loads(Path(os.environ["PMX4UE_CONFIG"]).read_text(encoding="utf-8"))
    output = Path(os.environ["PMX4UE_OUTPUT"])
    if output.exists():
        raise BuildError("Preflight output exists; review its fingerprint or choose a new variant")
    ctx = BuildContext(os.environ["PMX4UE_CONFIG"], strict=False, require_map=False)
    root = config["paths"]["ue_root"] + "/Preflight"
    if unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False):
        raise BuildError("Preflight namespace occupied; retain failed evidence and use a new variant")
    ctx.names["texture_root"] = root + "/Textures"
    material = load_or_create_material("M_InputProbe", root)
    nodes = []
    report = dict(schema="pmx4ue.material-preflight.v1", status="failed",
                  engine=unreal.SystemLibrary.get_engine_version(), inputs={},
                  scope="Typed neutral samplers and unary connections only; not final shaders, FBX or visual acceptance")
    try:
        for i, role in enumerate(NEUTRALS):
            texture = ctx.neutral_texture(role)
            kind = "SAMPLERTYPE_NORMAL" if role == "normal" else (
                "SAMPLERTYPE_COLOR" if role in {"base_color", "toon_ramp", "sphere_map"} else "SAMPLERTYPE_MASKS")
            node = texture_parameter(material, "Probe_" + role, texture, -800, i * 180, sampler_type(kind))
            report["inputs"][role] = texture.get_path_name()
            nodes.append(node)
        # Every sampler is connected so compiler pruning cannot hide a mismatch.
        accum = nodes[0]
        for node in nodes[1:]:
            add = expression(material, unreal.MaterialExpressionAdd, -300, 0)
            connect(accum, "RGB" if accum in nodes else "", add, "A")
            connect(node, "RGB", add, "B")
            accum = add
        saturated = expression(material, unreal.MaterialExpressionSaturate, 0, 0)
        connect(accum, "", saturated, "")
        connect_property(saturated, "", unreal.MaterialProperty.MP_BASE_COLOR)
        unreal.MaterialEditingLibrary.recompile_material(material)
        unreal.EditorAssetLibrary.save_loaded_asset(material)
        report["compile"] = checked(resolve("materials").inspect_material_compile(material.get_path_name()))
        if report["compile"].get("ok") is not True:
            raise BuildError("Material input probe did not compile")
        report["status"] = "probe_passed_character_pending"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
