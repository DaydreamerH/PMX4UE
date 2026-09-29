"""Check delivery evidence and outstanding work, never grade appearance.

Paths and SHA256 values are explicit; no latest-folder heuristics. This checker
cannot establish that the reviewer actually looked or chose a good algorithm.
"""
import hashlib
import json
from pathlib import Path
import re
from tools.material_preview_contract import verify_report
from tools.face_shading_delivery import review_face_shading
from tools.scene_effect_delivery import review_scene_effects
from tools.material_feature_delivery import review_material_features, review_scene_gameplay


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_delivery(profile, project):
    issues, evidence_hashes, reports = [], {}, {}
    def issue(message):
        issues.append(message)
    if profile.get("schema") != "pmx4ue.delivery.v2":
        issue("Delivery v2 required: migrate v1 by adding an explicit face_shading decision")
    if Path(profile.get("project", "")).resolve() != Path(project).resolve():
        issue("Delivery project mismatch")
    if not profile.get("scope"):
        issue("Explicit delivery scope required")
    evidence = profile.get("evidence", [])
    for item in evidence:
        ident, path = item.get("id"), Path(item.get("path", ""))
        if not ident or ident in reports:
            issue("Missing/duplicate evidence id")
            continue
        if not path.is_absolute() or not path.is_file() or digest(path) != item.get("sha256"):
            issue(f"Missing/stale evidence: {ident}")
            continue
        evidence_hashes[str(path.resolve())] = item["sha256"]
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig")) if path.suffix.lower() == ".json" else None
            reports[ident] = (item.get("kind"), value)
        except (ValueError, OSError) as error:
            issue(f"Cannot read evidence {ident}: {error}")
    assets = profile.get("assets", [])
    if not assets:
        issue("No selected asset combination")
    asset_ids = set()
    asset_roles = set()
    material_packages = set()
    for asset in assets:
        if not asset.get("id") or asset["id"] in asset_ids:
            issue("Missing/duplicate asset id")
        asset_ids.add(asset.get("id"))
        asset_roles.add(asset.get("role"))
        path = asset.get("path", "")
        if not re.fullmatch(r"/Game/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)?", path):
            issue(f"Invalid asset path: {path}")
            continue
        filename = Path(project).parent / "Content" / (path.split('.')[0][6:] + ".uasset")
        if not filename.is_file() or digest(filename) != asset.get("sha256"):
            issue(f"Missing/stale selected asset: {path}")
        else:
            evidence_hashes[str(filename.resolve())] = asset["sha256"]
        if not asset.get("evidence") or any(e not in reports for e in asset["evidence"]):
            issue(f"Asset lacks build/compatibility evidence: {path}")
        if not asset.get("compatibility_note"):
            issue(f"Explain compatibility of selected combination: {path}")
        if asset.get("role") in {"mesh", "material"}:
            material_packages.add(str(filename.resolve()))

    capture_hashes, capture_cases, debts, risks, slots = {}, {}, {}, set(), set()
    material_validation = False
    build_records = False
    slot_rows = {}
    for ident, (kind, report) in reports.items():
        if kind in {"capture", "material_validation", "run"} and not isinstance(report, dict):
            issue(f"Expected JSON object evidence: {ident}")
            continue
        if kind == "capture":
            try:
                verify_report(report)
                for row in report["captures"]:
                    image = row["image"]
                    capture_cases.setdefault(image["sha256"], set()).add(
                        (ident, row["case"], row["camera"]["name"], row["light"]["name"], row["mode"]))
                    evidence_hashes[image["path"]] = image["sha256"]
                capture_hashes.update(report["input_assets"]["game_package_sha256"])
                evidence_hashes.update(report["input_assets"]["game_package_sha256"])
            except (ValueError, OSError, KeyError, TypeError) as error:
                issue(f"Invalid capture {ident}: {error}")
        elif kind == "material_validation":
            material_validation = report.get("passed") is True and report.get("schema") == "mmd2ue.ue-validation.v1"
            if not material_validation:
                issue(f"Failed material validation: {ident}")
            slots.update(r["slot"] for r in report.get("slot_audit", []))
            for row in report.get("slot_audit", []):
                slot_rows[row["slot"]] = row
                # An empty audit is valid for an untextured graph only when the
                # validator explicitly enumerated its zero supported inputs.
                inputs = row.get("input_audit")
                if not isinstance(inputs, list) or any(
                        not r.get("actual") or r.get("actual") != r.get("expected") for r in inputs):
                    issue(f"Missing/mismatched effective input audit: {ident}:{row['slot']}")
            debts.update({r["id"]: r for r in report.get("material_debt", [])})
        elif kind == "run":
            if report.get("stage") in {"ue-build", "material-build"} and report.get("status") in {
                    "executed_needs_review", "executed_with_import_risks"}:
                build_records = True
            risks.update(f"{ident}:{risk}" for risk in report.get("import_risks", []))
            # Preserve source dependency evidence, not just the latest successful stage.
            for field in ("input_sha256", "output_sha256", "asset_sha256"):
                for path, expected in report.get(field, {}).items():
                    if not Path(path).is_file() or digest(path) != expected:
                        issue(f"Stale run evidence: {ident}: {path}")
                    else:
                        evidence_hashes[path] = expected

    effects = profile.get("effects", [])
    if "materials" in profile.get("scope", []):
        if not {"mesh", "material"} <= asset_roles:
            issue("Materials delivery must select both mesh and material assets")
        if not material_validation or not build_records:
            issue("Materials need current validation and upstream build run evidence")
        if not material_packages or not material_packages <= set(capture_hashes):
            issue("Selected mesh/materials not all covered by current capture fingerprints")
        covered = {s for effect in effects for s in effect.get("slots", [])}
        if not slots or not slots <= covered:
            issue("Effects must account for every actual material slot")
        if not effects:
            issue("No material effect review")
    ids = [e.get("id") for e in effects]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        issue("Missing/duplicate effect id")
    for effect in effects:
        ident, state = effect.get("id"), effect.get("status")
        if state == "not_applicable":
            if not effect.get("reason") or not effect.get("evidence") or any(e not in reports for e in effect["evidence"]):
                issue(f"N/A needs evidence and reason: {ident}")
        elif state == "reviewed":
            images = effect.get("image_sha256", [])
            if effect.get("comparison_required") is False and not effect.get("comparison_reason"):
                issue(f"Explain why comparison is not required: {ident}")
            if (effect.get("images_opened") is not True or not effect.get("reviewer")
                    or not effect.get("observation") or not effect.get("implementation")
                    or not images or any(h not in capture_cases for h in images)):
                issue(f"Effect lacks implementation/actual visual review evidence: {ident}")
            if effect.get("comparison_required", True):
                views = {}
                for h in images:
                    for report_id, case, camera, light, mode in capture_cases.get(h, set()):
                        views.setdefault((report_id, camera, light, mode), set()).add(case)
                if not any("Baseline" in cases and len(cases) > 1 for cases in views.values()):
                    issue(f"Effect needs same-report/view/light/mode Baseline and candidate: {ident}")
        else:
            issue(f"Effect unfinished: {ident}: {state}; next={effect.get('next_action')}")
    resolutions = profile.get("dispositions", {})
    if "materials" in profile.get("scope", []):
        review_face_shading(profile, slot_rows, debts, reports, capture_cases, issue, evidence_hashes)
        review_scene_effects(profile, reports, issue)
        review_material_features(profile, slots, reports, capture_cases, issue)
        review_scene_gameplay(profile, reports, issue)
    for ident in sorted(set(debts) | risks):
        row = resolutions.get(ident, {})
        # Never silently mark a still-disabled feature 'fixed'. It can only be
        # a documented scope limitation, or an evidenced alternative effect.
        refs = row.get("evidence", [])
        valid_refs = refs and all(e in reports for e in refs)
        if row.get("status") == "accepted_limitation":
            valid = valid_refs and row.get("reason") and row.get("scope_approval")
        elif row.get("status") == "alternative_verified":
            target = next((e for e in effects if e.get("id") == row.get("effect")), {})
            valid = valid_refs and row.get("reason") and target.get("status") == "reviewed"
        else:
            valid = False
        if not valid:
            issue(f"Unresolved degradation/import risk: {ident}; supply next experiment or explicit disposition")
    return dict(schema="pmx4ue.delivery-check.v2",
                status="incomplete" if issues else "evidence_complete_needs_human_judgment",
                visual_accepted=False, scope=profile.get("scope"), selected_assets=assets,
                unresolved=issues, material_debt=debts, import_risks=sorted(risks),
                dispositions=resolutions,
                face_shading=profile.get("face_shading"),
                scene_effects=profile.get("scene_effects"),
                material_acceptance=profile.get("material_acceptance"),
                material_features=profile.get("material_features"),
                evidence_sha256=evidence_hashes,
                note="Checks evidence consistency, not beauty, actual UE compatibility, or completeness of human-declared scope")
