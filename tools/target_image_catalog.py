"""Discover source-folder reference candidates and retrieve agent-reviewed regions.

Standard library only. Discovery never claims to have seen an image or classified
its material. Source images are read-only; annotations belong in the output JSON.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

SCHEMA = "pmx4ue.target-image-catalog.v1"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".tif", ".tiff", ".exr", ".dds"}
TARGET_FOLDERS = {"target", "targets", "reference", "references", "refs", "目标图", "参考图", "参考"}
KINDS = {"candidate", "target", "source_texture", "diagnostic", "algorithm_reference", "irrelevant"}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _checked_catalog(catalog):
    if not isinstance(catalog, dict) or catalog.get("schema") != SCHEMA:
        raise ValueError("Expected a target-image catalog v1")
    images = catalog.get("images")
    if not isinstance(images, list):
        raise ValueError("Catalog images must be a list")
    seen = set()
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("Each catalog image must be an object")
        image_id, sha = image.get("id"), image.get("sha256")
        if (not isinstance(sha, str) or len(sha) != 64 or
                any(char not in "0123456789abcdef" for char in sha) or
                image_id != "image_" + sha[:16] or image_id in seen):
            raise ValueError("Invalid or duplicate catalog image identity")
        seen.add(image_id)
        if image.get("kind") not in KINDS or not isinstance(image.get("locations"), list) or not image["locations"]:
            raise ValueError(f"Invalid kind/locations: {image_id}")
        for location in image["locations"]:
            if not isinstance(location, dict) or not isinstance(location.get("path"), str):
                raise ValueError(f"Invalid image location: {image_id}")
        review = image.get("review")
        if not isinstance(review, dict) or not isinstance(review.get("images_opened"), bool):
            raise ValueError(f"Invalid review record: {image_id}")
        regions = image.get("regions")
        if not isinstance(regions, list):
            raise ValueError(f"Regions must be a list: {image_id}")
        region_ids = set()
        for region in regions:
            if not isinstance(region, dict):
                raise ValueError(f"Each region must be an object: {image_id}")
            region_id = region.get("id")
            if not isinstance(region_id, str) or not region_id.strip() or region_id in region_ids:
                raise ValueError(f"Invalid/duplicate region id: {image_id}")
            region_ids.add(region_id)
            for key in ("tags", "features", "material_slots"):
                values = region.get(key)
                if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ValueError(f"Invalid {key}: {image_id}/{region_id}")
            if not region["tags"] or not isinstance(region.get("observation"), str) or not region["observation"].strip():
                raise ValueError(f"A region needs tags and actual observations: {image_id}/{region_id}")
            if region.get("priority") not in {"high", "medium", "low"}:
                raise ValueError(f"Invalid priority: {image_id}/{region_id}")
            bbox = region.get("bbox_normalized")
            if bbox is not None and (not isinstance(bbox, list) or len(bbox) != 4 or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or
                        not 0 <= v <= 1 for v in bbox) or not bbox[0] < bbox[2] or not bbox[1] < bbox[3]):
                raise ValueError(f"Invalid normalized [left, top, right, bottom] box: {image_id}/{region_id}")
        if image["kind"] == "target" and (review["images_opened"] is not True or
                not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip() or
                not isinstance(review.get("selection_reason"), str) or not review["selection_reason"].strip() or not regions):
            raise ValueError(f"Target requires actual image review and regions: {image_id}")
    return catalog


def discover(pmx, source_root=None, *, manifest=None, extra_images=(), previous=None):
    pmx = Path(pmx).resolve()
    if pmx.suffix.lower() != ".pmx" or not pmx.is_file():
        raise ValueError("Provide an existing PMX")
    root = Path(source_root).resolve() if source_root else pmx.parent
    if not root.is_dir() or not pmx.is_relative_to(root):
        raise ValueError("PMX must be inside the source root")
    references = set()
    manifest_record = None
    if manifest:
        manifest = Path(manifest).resolve()
        data = read(manifest)
        manifest_record = {"path": str(manifest), "sha256": digest(manifest)}
        for value in data.get("textures", []):
            references.add((pmx.parent / value.replace("\\", "/")).resolve())
            references.add((root / value.replace("\\", "/")).resolve())
        for material in data.get("materials", []):
            for image in material.get("images", []):
                value = image.get("path")
                if value:
                    references.add((pmx.parent / value.replace("\\", "/")).resolve())
                    references.add((root / value.replace("\\", "/")).resolve())
    previous_by_hash = {}
    if previous:
        old = _checked_catalog(read(previous))
        if old.get("source", {}).get("pmx_sha256") != digest(pmx):
            raise ValueError("Previous catalog belongs to a changed/different PMX; create a fresh model catalog")
        previous_by_hash = {image["sha256"]: image for image in old["images"]}
    candidates = set()
    for item in root.rglob("*"):
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
            resolved = item.resolve()
            if resolved.is_relative_to(root):
                candidates.add(resolved)
    explicit = set()
    for value in extra_images:
        path = Path(value).resolve()
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Explicit image missing/unsupported: {path}")
        candidates.add(path)
        explicit.add(path)
    images = {}
    for path in sorted(candidates, key=lambda p: p.as_posix().casefold()):
        sha = digest(path)
        hints = []
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        if relative and any(part.casefold() in TARGET_FOLDERS for part in Path(relative).parts[:-1]):
            hints.append("target_directory_candidate")
        if path in explicit:
            hints.append("explicit_image_candidate")
        if path in references:
            hints.append("referenced_texture_in_manifest")
        location = {"path": str(path), "relative_to_source_root": relative,
                    "bytes": path.stat().st_size, "discovery_hints": hints}
        if sha not in images:
            image = {"id": "image_" + sha[:16], "sha256": sha, "locations": [],
                     "kind": "candidate", "review": {"images_opened": False, "reviewer": "", "selection_reason": ""},
                     "regions": []}
            if sha in previous_by_hash:
                old = previous_by_hash[sha]
                for key in ("kind", "review", "regions"):
                    image[key] = copy.deepcopy(old[key])
            images[sha] = image
        images[sha]["locations"].append(location)
    ordered = sorted(images.values(), key=lambda image: (
        not any("target_directory_candidate" in loc["discovery_hints"] or
                "explicit_image_candidate" in loc["discovery_hints"] for loc in image["locations"]), image["id"]))
    missing_previous = [image["id"] for sha, image in previous_by_hash.items() if sha not in images]
    return {"schema": SCHEMA, "status": "candidates_need_image_review" if ordered else "no_candidates",
            "source": {"pmx": str(pmx), "pmx_sha256": digest(pmx), "root": str(root)},
            "manifest": manifest_record, "texture_reference_status": "manifest_checked" if manifest else "unknown",
            "previous_catalog": {"path": str(Path(previous).resolve()), "sha256": digest(previous)} if previous else None,
            "removed_or_changed_image_ids": missing_previous,
            "images": ordered, "note": "Hints are discovery aids, never target selection or visual acceptance."}


def lookup(catalog, tags=(), text=""):
    catalog = _checked_catalog(catalog)
    source = catalog.get("source", {})
    pmx = Path(source.get("pmx", ""))
    if not pmx.is_absolute() or not pmx.is_file() or digest(pmx) != source.get("pmx_sha256"):
        raise ValueError("PMX missing/changed; rediscover the catalog for the current source")
    wanted = {value.casefold() for value in tags}
    hits, unavailable, candidates = [], [], 0
    for image in catalog["images"]:
        if image["kind"] == "candidate":
            candidates += 1
        if image["kind"] != "target":
            continue
        valid_paths = [loc["path"] for loc in image["locations"] if Path(loc["path"]).is_absolute() and
                       Path(loc["path"]).is_file() and digest(loc["path"]) == image["sha256"]]
        if not valid_paths:
            unavailable.append(image["id"])
            continue
        for region in image["regions"]:
            if wanted and not wanted.issubset({tag.casefold() for tag in region["tags"]}):
                continue
            searchable = " ".join([region["id"], region["observation"], *region["tags"], *region["features"]])
            if text and text.casefold() not in searchable.casefold():
                continue
            hits.append({"image_id": image["id"], "source_sha256": image["sha256"], "path": valid_paths[0],
                         "alternate_paths": valid_paths[1:], "region": copy.deepcopy(region)})
    priorities = {"high": 0, "medium": 1, "low": 2}
    hits.sort(key=lambda hit: (priorities[hit["region"]["priority"]], hit["image_id"], hit["region"]["id"]))
    return {"schema": "pmx4ue.target-image-query.v1", "matches": hits,
            "unavailable_target_image_ids": unavailable, "unreviewed_candidate_count": candidates,
            "note": "No match does not prove the source folder has no suitable target images."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("discover")
    scan.add_argument("--pmx", required=True)
    scan.add_argument("--source-root")
    scan.add_argument("--manifest")
    scan.add_argument("--image", action="append", default=[])
    scan.add_argument("--previous")
    scan.add_argument("--output", required=True)
    query = commands.add_parser("query")
    query.add_argument("--catalog", required=True)
    query.add_argument("--tag", action="append", default=[])
    query.add_argument("--text", default="")
    args = parser.parse_args()
    if args.command == "discover":
        output = Path(args.output).resolve()
        pmx = Path(args.pmx).resolve()
        source_root = Path(args.source_root).resolve() if args.source_root else pmx.parent
        if output.is_relative_to(source_root) or output.exists():
            raise ValueError("Write a new catalog outside the read-only source root; do not overwrite")
        result = discover(pmx, source_root, manifest=args.manifest, extra_images=args.image, previous=args.previous)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"catalog": str(output), "image_count": len(result["images"]), "status": result["status"]}, ensure_ascii=False))
    else:
        print(json.dumps(lookup(read(args.catalog), args.tag, args.text), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
