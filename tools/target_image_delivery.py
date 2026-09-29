"""Validate optional target-image provenance and comparison evidence, not appearance."""
import hashlib
from pathlib import Path


def review_target_images(profile, capture_cases, issue, evidence_hashes):
    review = profile.get("target_image_review")
    if review is None:
        return  # No user-supplied target image is a valid workflow path.
    if not isinstance(review, dict) or review.get("status") != "reviewed" or \
            review.get("images_opened") is not True or not review.get("reviewer"):
        issue("Target-image review needs an actual reviewer and opened images")
        return
    sources = review.get("sources")
    comparisons = review.get("comparisons")
    if not isinstance(sources, list) or not sources or not isinstance(comparisons, list) or not comparisons:
        issue("Target-image review needs sources and region comparisons")
        return
    valid_sources = set()
    for source in sources:
        if not isinstance(source, dict):
            issue("Invalid target-image source")
            continue
        path, expected = Path(source.get("path", "")), source.get("sha256")
        if not path.is_absolute() or not path.is_file() or not isinstance(expected, str) or \
                hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            issue(f"Missing/stale target image: {path}")
            continue
        valid_sources.add(expected)
        evidence_hashes[str(path.resolve())] = expected
    covered = set()
    for row in comparisons:
        if not isinstance(row, dict):
            issue("Invalid target-image comparison")
            continue
        source_hash = row.get("source_sha256")
        result_hash = row.get("result_image_sha256")
        if source_hash not in valid_sources or result_hash not in capture_cases or \
                not all(isinstance(row.get(k), str) and row[k].strip()
                        for k in ("region", "feature", "conditions", "observation")):
            issue("Target-image comparison needs a source, Lit capture and region observations")
            continue
        if not any(mode == "Lit" for _, _, _, _, mode in capture_cases[result_hash]):
            issue("Target-image comparison must use a Lit result capture")
            continue
        covered.add(source_hash)
        disposition = row.get("disposition")
        if disposition == "iterate":
            issue(f"Target-image comparison still needs iteration: {row['region']}; next={row.get('next_action')}")
        elif disposition == "accepted_limitation":
            if not row.get("limitation_reason") or not row.get("scope_approval"):
                issue(f"Target-image limitation needs reason and user scope approval: {row['region']}")
        elif disposition != "matched":
            issue(f"Invalid target-image disposition: {row['region']}")
    if valid_sources - covered:
        issue("Every valid target image needs at least one region comparison")
