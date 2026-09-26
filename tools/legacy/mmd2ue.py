"""Command-line entry point for the reusable MMD2UE control plane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mmd2ue_core import (
    MATERIAL_MAP_SCHEMA,
    PROFILE_PRESETS_PATH,
    build_character_asset_names,
    build_execution_plan,
    build_material_map_draft,
    build_source_audit,
    make_character_config,
    normalize_material_map,
    project_root_from,
    read_json,
    resolve_path,
    validate_config,
    validate_material_map,
    write_json,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare and audit configurable MMD to UE character conversions")
    result.add_argument("--project-root", type=Path, help="Defaults to the nearest directory containing a .uproject")
    sub = result.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a character config and run a non-destructive source audit")
    init.add_argument("--character-id", required=True)
    init.add_argument("--display-name")
    init.add_argument("--pmx", type=Path, required=True)
    init.add_argument("--source-root", type=Path, required=True)
    init.add_argument("--scale", type=float, default=0.08)
    init.add_argument("--force", action="store_true")

    for name in ("validate", "audit", "plan", "check-map"):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path, required=True)

    draft = sub.add_parser("draft-map", help="Create an unbound material-map draft from blender_manifest.json")
    draft.add_argument("--config", type=Path, required=True)
    draft.add_argument("--force", action="store_true")

    names = sub.add_parser("names", help="Print the derived UE asset names for a config")
    names.add_argument("--config", type=Path, required=True)
    return result


def root_for(args: argparse.Namespace) -> Path:
    return args.project_root.resolve() if args.project_root else project_root_from(Path(__file__))


def load_config(path: Path, root: Path) -> tuple[Path, dict]:
    actual = path.resolve() if path.is_absolute() else (root / path).resolve()
    return actual, read_json(actual)


def load_presets(root: Path) -> dict:
    path = root / PROFILE_PRESETS_PATH
    return read_json(path) if path.is_file() else {"profiles": {}}


def print_result(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    args = parser().parse_args()
    root = root_for(args)
    if args.command == "init":
        config_path = root / "Tools" / "MMDPipeline" / "characters" / f"{args.character_id}.json"
        if config_path.exists() and not args.force:
            raise FileExistsError(f"config already exists: {config_path}; pass --force to replace it")
        config = make_character_config(
            root,
            args.character_id,
            args.display_name or args.character_id,
            args.pmx,
            args.source_root,
            args.scale,
        )
        write_json(config_path, config)
        audit = build_source_audit(config, root)
        audit_path = resolve_path(root, config["paths"]["artifact_dir"]) / "source_audit.json"
        write_json(audit_path, audit)
        print_result({"ok": True, "config": str(config_path), "audit": str(audit_path), "summary": audit["summary"]})
        return 0

    config_path, config = load_config(args.config, root)
    if args.command == "validate":
        issues = validate_config(config, root)
        print_result({"ok": not any(item["level"] == "error" for item in issues), "config": str(config_path), "issues": issues})
        return 1 if any(item["level"] == "error" for item in issues) else 0
    if args.command == "audit":
        issues = validate_config(config, root)
        if any(item["level"] == "error" for item in issues):
            print_result({"ok": False, "issues": issues})
            return 1
        audit = build_source_audit(config, root)
        output = resolve_path(root, config["paths"]["artifact_dir"]) / "source_audit.json"
        write_json(output, audit)
        print_result({"ok": True, "output": str(output), "summary": audit["summary"]})
        return 0
    if args.command == "plan":
        plan = build_execution_plan(config, root)
        output = resolve_path(root, config["paths"]["artifact_dir"]) / "execution_plan.json"
        write_json(output, plan)
        print_result({"ok": not any(item["level"] == "error" for item in plan["config_issues"]), "output": str(output), "stages": plan["stages"]})
        return 0
    if args.command == "draft-map":
        artifact = resolve_path(root, config["paths"]["artifact_dir"])
        blender_manifest_path = artifact / "blender_manifest.json"
        output = resolve_path(root, config["paths"]["material_map"])
        if output.exists() and not args.force:
            raise FileExistsError(f"material map already exists: {output}; pass --force only when replacement is intended")
        draft = build_material_map_draft(config, read_json(blender_manifest_path))
        write_json(output, draft)
        print_result({"ok": True, "output": str(output), "slot_count": len(draft["slots"]), "status": draft["status"]})
        return 0
    if args.command == "check-map":
        map_path = resolve_path(root, config["paths"]["material_map"])
        material_map = read_json(map_path)
        normalized = normalize_material_map(config, material_map, load_presets(root))
        issues = validate_material_map(normalized)
        manifest_path = resolve_path(root, config["paths"]["artifact_dir"]) / "blender_manifest.json"
        if manifest_path.is_file():
            manifest = read_json(manifest_path)
            manifest_slots = [
                name for record in manifest.get("meshes", []) for name in record.get("materials", [])
            ]
            mapped = [slot["slot"] for slot in normalized["slots"]]
            missing = sorted(set(manifest_slots) - set(mapped))
            extra = sorted(set(mapped) - set(manifest_slots))
            if missing:
                issues.append({"level": "error", "code": "missing_slots", "message": f"not mapped: {missing}"})
            if extra:
                issues.append({"level": "error", "code": "extra_slots", "message": f"not in manifest: {extra}"})
        print_result(
            {
                "ok": not any(item["level"] == "error" for item in issues),
                "config": str(config_path),
                "map": str(map_path),
                "slot_count": len(normalized["slots"]),
                "issues": issues,
            }
        )
        return 1 if any(item["level"] == "error" for item in issues) else 0
    if args.command == "names":
        print_result(build_character_asset_names(config, root))
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
