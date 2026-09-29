"""Read a completed texture as linear data in a fresh Blender background process.

blender --background --factory-startup --python-exit-code 1 --python
  tools/blender_face_sdf_audit.py -- --texture <RGBA.png> --output <audit.json>
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from face_sdf_texture_contract import summarize_pixels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--texture", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", help="Matching bake manifest; defaults to the texture's sibling manifest")
    parser.add_argument("--encoding", choices=("linear_azimuth_v1", "cosine_half_v1"))
    parser.add_argument("--encoding-evidence", default="", help="Reviewed convention for legacy/hand-authored textures")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, output = Path(args.texture).resolve(), Path(args.output).resolve()
    if output.exists():
        raise ValueError("Audit already exists; use a new output path")
    manifest_path = Path(args.manifest).resolve() if args.manifest else source.parent / "face_sdf_manifest.json"
    encoding, provenance = "unspecified", {}
    if args.manifest or manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if manifest.get("schema") == "pmx4ue.face-sdf-bake.v2":
            if manifest.get("texture_sha256") != hashlib.sha256(source.read_bytes()).hexdigest():
                raise ValueError("Bake manifest does not match the audited texture")
            encoding = manifest["encoding"]
            provenance = {"manifest": str(manifest_path),
                          "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                          "sweep_quality": manifest.get("sweep_quality")}
    if args.encoding:
        if not args.encoding_evidence.strip():
            raise ValueError("Explicit encoding requires --encoding-evidence; do not guess from grayscale")
        if encoding != "unspecified" and encoding != args.encoding:
            raise ValueError("Explicit encoding conflicts with bake manifest")
        encoding = args.encoding
        provenance["review_evidence"] = args.encoding_evidence
    image = bpy.data.images.load(str(source), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        report = summarize_pixels(pixels.reshape(-1, 4))
        report.update(schema="pmx4ue.face-sdf-texture.v1", texture=str(source),
                      sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      width=width, height=height, blender_version=bpy.app.version_string,
                      convention="R shadow-onset threshold; A application mask; G/B optional highlight windows",
                      encoding=encoding, encoding_provenance=provenance,
                      visual_accepted=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        if report["status"] != "data_valid_visual_pending":
            raise ValueError("Invalid SDF texture: " + "; ".join(report["errors"]))
    finally:
        bpy.data.images.remove(image)


if __name__ == "__main__":
    main()
