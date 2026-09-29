"""Require decisions for scene-dependent effects, not merely built materials."""


def review_scene_effects(profile, reports, issue):
    choices = profile.get("scene_effects", {})
    effects = {e.get("id"): e for e in profile.get("effects", [])}
    for name in ("outline", "rim"):
        row = choices.get(name, {})
        refs = row.get("evidence", [])
        if not row.get("reason") or not refs or any(ref not in reports for ref in refs):
            issue(f"Scene effect {name}: explicit model-specific decision and evidence required")
        if row.get("status") == "not_selected":
            continue
        if row.get("status") != "reviewed":
            issue(f"Scene effect unfinished: {name}; next={row.get('next_action')}")
            continue
        effect = effects.get(row.get("effect"), {})
        if effect.get("status") != "reviewed" or not row.get("runtime_binding"):
            issue(f"Scene effect {name}: reviewed effect and reusable actor/component binding instructions required")
        method = row.get("method")
        if method == "alternative":
            # Its graph and actual A/B appearance are covered by the referenced effect review.
            if not row.get("implementation"):
                issue(f"Scene effect {name}: describe alternative algorithm and scene dependencies")
            continue
        expected = "outline" if name == "outline" else "depth_rim"
        if method != expected:
            issue(f"Scene effect {name}: choose {expected} or evidenced alternative")
            continue
        found = False
        images = effect.get("image_sha256", [])
        for kind, report in reports.values():
            if kind != "capture" or not isinstance(report, dict):
                continue
            cases = {c["name"]: c for c in report.get("profile", {}).get("cases", [])}
            captures = [c for c in report.get("captures", [])
                        if c.get("mode") == "Lit" and c.get("image", {}).get("sha256") in images]
            baseline = {(c["camera"]["name"], c["light"]["name"]) for c in captures if c["case"] == "Baseline"}
            for capture in captures:
                case = cases.get(capture["case"], {})
                if (case.get(expected) and capture.get("scene_effects", {}).get(expected, {}).get("ok") is True
                        and (capture["camera"]["name"], capture["light"]["name"]) in baseline):
                    found = True
        if not found:
            issue(f"Scene effect {name}: need Lit Baseline/candidate with actual preview attachment, not only built assets")
