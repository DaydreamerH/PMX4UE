"""Offline agent pose workflow: draft contracts, then compile reviewed decisions."""
import argparse
import json
from pathlib import Path

try:
    from .retarget_workflow import draft_model, draft_pair, compile_pair
except ImportError:
    from retarget_workflow import draft_model, draft_pair, compile_pair


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_bundle(directory, files):
    directory = Path(directory)
    # Serialize everything before creating any output; never overwrite old runs.
    encoded = {name: json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) for name, value in files.items()}
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in encoded.items():
        with (directory / name).open("x", encoding="utf-8") as handle:
            handle.write(data + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft")
    draft.add_argument("--source-id", required=True)
    draft.add_argument("--target-id", required=True)
    build = sub.add_parser("plan")
    for name in ("source-model", "target-model", "pair"):
        build.add_argument("--"+name, required=True)
    for cmd in (draft, build):
        cmd.add_argument("--inventory", required=True)
        cmd.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    inv = read(args.inventory)
    if args.command == "draft":
        files = {"source.model.json": draft_model(inv, "source", args.source_id),
                 "target.model.json": draft_model(inv, "target", args.target_id), "pair.json": draft_pair(inv)}
    else:
        result = compile_pair(inv, {"source": read(args.source_model), "target": read(args.target_model)}, read(args.pair))
        files = {"pose_profile.json": result["profile"], "plan.json": result, "acceptance.json": result["acceptance"]}
    write_bundle(args.output_dir, files)
    print(json.dumps(dict(status="draft_needs_agent_review" if args.command == "draft" else result["status"],
                          output_dir=str(Path(args.output_dir).resolve())), ensure_ascii=False))


if __name__ == "__main__":
    main()
