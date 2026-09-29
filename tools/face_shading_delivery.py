"""Face shading closure for delivery v2; data/traceability, never beauty scoring."""
import math
from itertools import product
from tools.face_sdf_texture_contract import verify_texture_report


def review_sweep(entry, effect, capture_cases, issue, label):
    """Require intermediate-angle observations, not just three endpoint images."""
    review = entry.get("sweep_review", {})
    observations = review.get("observations", {})
    if (review.get("images_opened") is not True or not review.get("reviewer") or
            any(not isinstance(observations.get(k), str) or not observations[k].strip()
                for k in ("nose_cheeks", "mouth", "uv_seams", "transition", "nonmonotonicity"))):
        issue(f"Face SDF needs opened sweep images and regional observations: {label}")
    samples = review.get("samples", [])
    angles = [s.get("angle_degrees") for s in samples]
    hashes = [s.get("image_sha256") for s in samples]
    if (len(samples) < 7 or any(type(a) not in (float, int) or not math.isfinite(a) or abs(a) > 180 for a in angles)
            or len(set(angles)) != len(angles) or angles != sorted(angles) or
            not angles[0] <= -90 or not angles[-1] >= 90 or not any(abs(a) < .1 for a in angles) or
            any(b-a > 45.001 for a, b in zip(angles, angles[1:])) or len(set(hashes)) != len(hashes)):
        issue(f"Face SDF needs an ordered sweep of >=7 distinct angles/images, front and both sides, gaps <=45 degrees: {label}")
        return
    shared, rows_by_sample = None, []
    for h in hashes:
        rows = {r for r in capture_cases.get(h, set()) if r[4] == "Lit"}
        keys = {(r[0], r[1], r[2]) for r in rows}
        shared = keys if shared is None else shared & keys
        rows_by_sample.append(rows)
        if h not in effect.get("image_sha256", []):
            issue(f"Sweep image is not part of reviewed face effect: {label}")
    # One report/case/camera must contain one unique lighting setup per sample.
    def distinct_lights(key):
        choices = [{r[3] for r in rows if (r[0], r[1], r[2]) == key} for rows in rows_by_sample]
        owners = {}
        def assign(index, seen):
            for light in choices[index] - seen:
                seen.add(light)
                if light not in owners or assign(owners[light], seen):
                    owners[light] = index
                    return True
            return False
        return all(assign(i, set()) for i in range(len(choices)))
    if not any(distinct_lights(key) for key in shared or ()):
        issue(f"Face SDF sweep must use one Lit view/case/report with distinct lights: {label}")


def review_face_shading(profile, slot_rows, debts, reports, capture_cases, issue, evidence_hashes):
    entries = profile.get("face_shading")
    if not isinstance(entries, list) or not entries:
        issue("Declare face_shading: implement SDF, verify an alternative, or evidence no applicable face")
        return
    required_slots = {d["slot"] for d in debts.values() if d.get("missing_role") == "face_sdf"}
    required_slots.update(s for s, r in slot_rows.items() if
                          isinstance(r.get("effective_scalars", {}).get("FaceMode"), (float, int)) and
                          r["effective_scalars"]["FaceMode"] > 0)
    covered = set()
    for entry in entries:
        slots = entry.get("slots", [])
        label = ",".join(slots) or "no face"
        if len(slots) != len(set(slots)) or covered.intersection(slots) or any(s not in slot_rows for s in slots):
            issue(f"Invalid/duplicate face shading slots: {label}")
        covered.update(slots)
        refs = entry.get("evidence", [])
        if not entry.get("reason") or not refs or any(r not in reports for r in refs):
            issue(f"Face shading decision needs evidence and reason: {label}")
        if entry.get("status") != "reviewed":
            issue(f"Face shading unfinished: {label}; next={entry.get('next_action')}; resume={entry.get('resume_when')}")
            continue
        method = entry.get("method")
        if method == "not_applicable":
            if slots:
                issue("Use an alternative for an existing face; not_applicable is only for no applicable face")
            continue
        if method not in {"sdf", "alternative"} or not slots:
            issue(f"Select sdf or alternative for actual face slots: {label}")
            continue
        effect = next((e for e in profile.get("effects", []) if e.get("id") == entry.get("effect")), {})
        if effect.get("status") != "reviewed" or not set(slots) <= set(effect.get("slots", [])):
            issue(f"Face shading needs a reviewed effect covering its slots: {label}")
        # Match three angle observations to one current Lit camera/case/report.
        tests = entry.get("light_tests", {})
        shared, observations = None, []
        if set(tests) != {"front", "left", "right"} or len(set(tests.values())) != 3:
            issue(f"Face shading needs front/left/right lighting evidence: {label}")
        else:
            for h in tests.values():
                rows = {r for r in capture_cases.get(h, set()) if r[4] == "Lit"}
                keys = {(r[0], r[1], r[2]) for r in rows}
                shared = keys if shared is None else shared & keys
                observations.append(rows)
                if h not in effect.get("image_sha256", []):
                    issue(f"Face light test is not part of the reviewed effect: {label}")
            matched = any(any(len(set(lights)) == 3 for lights in product(*[
                {r[3] for r in rows if (r[0], r[1], r[2]) == key} for rows in observations]))
                for key in shared or ())
            if not matched:
                issue(f"Face lighting tests must use one Lit view/case/report and three light settings: {label}")
        if entry.get("runtime_status") not in {"pending_animation", "pending", "blocked", "reviewed", "not_required"}:
            issue(f"Record face runtime status separately from static review: {label}")
        if method == "alternative":
            continue
        review_sweep(entry, effect, capture_cases, issue, label)
        kind, audit = reports.get(entry.get("texture_audit"), (None, None))
        source_sha = None
        try:
            if kind != "face_sdf_texture" or not isinstance(audit, dict):
                raise ValueError("Reference a face_sdf_texture audit")
            path, sha = verify_texture_report(audit)
            source_sha = sha
            evidence_hashes[path] = sha
            if audit.get("encoding") not in {"linear_azimuth_v1", "cosine_half_v1"}:
                issue(f"Face SDF encoding is unknown; audit the bake convention instead of guessing: {label}")
        except (ValueError, OSError, TypeError) as error:
            issue(f"Face SDF texture invalid: {label}: {error}")
        texture = entry.get("texture_asset", "").split('.')[0]
        if not texture.startswith("/Game/"):
            issue(f"Face SDF needs a real texture asset path: {label}")
        for slot in slots:
            row = slot_rows.get(slot, {})
            bound = next((r for r in row.get("input_audit", []) if r.get("role") == "face_sdf"), {})
            if (bound.get("source") != "declared" or not bound.get("actual") or
                    bound["actual"].split('.')[0] != texture):
                issue(f"Face SDF real texture is not bound in current input audit: {slot}")
            if not source_sha or bound.get("import_source_sha256") != source_sha:
                issue(f"Face SDF texture audit does not match the bound texture import source: {slot}")
            if row.get("declared_route") == "master":
                if (not isinstance(audit, dict) or not row.get("face_sdf_encoding") or
                        row.get("face_sdf_encoding") != audit.get("encoding")):
                    issue(f"Face SDF bake/decoder encoding mismatch or missing readback; build and validate a new master: {slot}")
                active = row.get("effective_scalars", {}).get("FaceMode")
                if not isinstance(active, (int, float)) or not math.isfinite(active) or active <= 0:
                    issue(f"Face SDF branch is disabled or lacks scalar readback: {slot}")
    if not required_slots <= covered:
        issue("Face shading omits SDF-enabled/degraded slots: " + ", ".join(sorted(required_slots - covered)))
