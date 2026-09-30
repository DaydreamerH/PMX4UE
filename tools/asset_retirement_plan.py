"""Build a read-only, exact-path candidate plan. This module never deletes assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PACKAGE = re.compile(r"/Game/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)?\Z")


def _package(path):
    if not isinstance(path, str) or not PACKAGE.fullmatch(path):
        raise ValueError(f"Expected an exact /Game package path: {path!r}")
    return path.split(".", 1)[0]


def _file(project, package):
    return project.parent / "Content" / (package[len("/Game/"):] + ".uasset")


def make_plan(delivery_path, candidates_path):
    delivery_path, candidates_path = Path(delivery_path).resolve(), Path(candidates_path).resolve()
    delivery = json.loads(delivery_path.read_text(encoding="utf-8-sig"))
    candidates = json.loads(candidates_path.read_text(encoding="utf-8-sig"))
    if delivery.get("schema") != "pmx4ue.delivery.v2" or candidates.get("schema") != "pmx4ue.retirement-candidates.v1":
        raise ValueError("Expected current delivery and retirement-candidates schemas")
    project = Path(delivery.get("project", "")).resolve()
    if (project.suffix.lower() != ".uproject" or not project.is_file() or
            Path(candidates.get("project", "")).resolve() != project):
        raise ValueError("Candidate project must match an existing delivery .uproject")
    namespace = _package(candidates.get("candidate_namespace"))
    if len(namespace.split("/")) < 5:
        raise ValueError("Candidate namespace must be character/version-specific, not a broad Content root")
    protected = {_package(path) for path in candidates.get("protected_assets", [])}
    selected = set()
    for row in delivery.get("assets", []):
        package = _package(row.get("path"))
        selected.add(package)
        filename = _file(project, package)
        if not filename.is_file() or hashlib.sha256(filename.read_bytes()).hexdigest() != row.get("sha256"):
            raise ValueError(f"Selected asset is missing or changed: {package}")
    if not selected:
        raise ValueError("Delivery has no selected assets")
    rows = candidates.get("candidates", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("Name each obsolete candidate explicitly; empty/glob lists are not a plan")
    output, seen = [], set()
    for row in rows:
        package = _package(row.get("path"))
        if package in seen or not package.startswith(namespace + "/"):
            raise ValueError(f"Duplicate or out-of-namespace candidate: {package}")
        if package in selected or package in protected:
            raise ValueError(f"Selected/protected asset cannot be retired: {package}")
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Candidate requires a model-specific reason: {package}")
        filename = _file(project, package)
        if not filename.is_file():
            raise ValueError(f"Candidate package does not exist: {package}")
        output.append({"path": package, "file": str(filename.resolve()),
                       "sha256": hashlib.sha256(filename.read_bytes()).hexdigest(),
                       "reason": reason.strip(), "ue_referencers": "pending_read_only_audit"})
        seen.add(package)
    return {"schema": "pmx4ue.retirement-plan.v1", "status": "review_required_no_deletion",
            "project": str(project), "delivery": str(delivery_path),
            "delivery_sha256": hashlib.sha256(delivery_path.read_bytes()).hexdigest(),
            "selected_assets": sorted(selected), "protected_assets": sorted(protected),
            "candidate_namespace": namespace, "candidates": output,
            "next_gate": "Audit UE hard/soft/management referencers and dependencies; ask the user to approve this exact list before any UE asset deletion"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", required=True)
    parser.add_argument("--candidates", required=True)
    args = parser.parse_args()
    print(json.dumps(make_plan(args.delivery, args.candidates), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
