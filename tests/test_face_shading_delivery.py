import hashlib
import json
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.delivery_contract import review_delivery
from tools.face_shading_delivery import review_face_shading
from tools.face_sdf_texture_contract import summarize_pixels, verify_texture_report


def png_header(width, height):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" +
            struct.pack(">II", width, height))


class FaceShadingTests(unittest.TestCase):
    def fixture(self):
        entry = dict(slots=["Face"], method="sdf", status="reviewed", reason="UV-reviewed face shadow",
                     evidence=["design"], effect="face_shadow", texture_audit="sdf_audit",
                     texture_asset="/Game/Character/Textures/SDF", runtime_status="pending_animation",
                     light_response="linear_azimuth_v1",
                     light_tests=dict(front="a", left="b", right="c"))
        entry["sweep_review"] = dict(images_opened=True, reviewer="fixture",
            observations={k: "Reviewed fixture" for k in
                ("nose_cheeks", "mouth", "uv_seams", "transition", "nonmonotonicity")},
            samples=[dict(angle_degrees=a, image_sha256=h) for a, h in
                     zip((-90, -60, -30, 0, 30, 60, 90), "bdeafgc")])
        profile = dict(face_shading=[entry], effects=[dict(id="face_shadow", slots=["Face"], status="reviewed",
                                                        image_sha256=list("abcdefg"))])
        slots = {"Face": dict(declared_route="master", face_sdf_response="linear_azimuth_v1", effective_scalars={"FaceMode": 1.0},
                             input_audit=[dict(role="face_sdf", source="declared",
                                              import_source_sha256="hash",
                                              actual="/Game/Character/Textures/SDF.SDF")])}
        reports = {"design": ("review", None), "sdf_audit": ("face_sdf_texture", {"encoding": "linear_azimuth_v1", "width": 1024, "height": 1024})}
        cases = {h: {("capture", "Candidate", "FaceClose", light, "Lit")}
                 for h, light in zip("abcdefg", ("Front", "Left", "Right", "Left60", "Left30", "Right30", "Right60"))}
        return profile, slots, reports, cases

    def review(self, profile, slots, reports, cases, debts=None):
        issues = []
        with patch("tools.face_shading_delivery.verify_texture_report", return_value=("texture.png", "hash")), \
                patch("tools.face_shading_delivery.png_dimensions", return_value=(1024, 1024)):
            review_face_shading(profile, slots, debts or {}, reports, cases, issues.append, {})
        return issues

    def test_white_placeholder_and_variation_outside_mask_rejected(self):
        self.assertEqual(summarize_pixels([(1, 1, 1, 1)] * 16)["status"], "invalid")
        self.assertEqual(summarize_pixels([(1, 0, 0, 1), (0, 0, 0, 0)])["status"], "invalid")
        self.assertEqual(summarize_pixels([(0, 0, 0, 0)])["status"], "invalid")

    def test_valid_shadow_does_not_require_highlights_or_partial_alpha(self):
        result = summarize_pixels([(0.1, 0, 0, 1), (0.9, 0, 0, 1)])
        self.assertEqual(result["status"], "data_valid_visual_pending")
        self.assertEqual(result["lit_fraction_by_threshold"]["0.5"], 0.5)

    def test_texture_source_change_invalidates_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sdf.png"
            path.write_bytes(b"fixture")
            report = dict(summarize_pixels([(0, 0, 0, 1), (1, 0, 0, 1)]),
                          schema="pmx4ue.face-sdf-texture.v1", texture=str(path.resolve()),
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            verify_texture_report(report)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_texture_report(report)

    def test_missing_face_decision_and_indefinite_pending_fail(self):
        p, s, r, c = self.fixture()
        del p["face_shading"]
        self.assertTrue(any("Declare face_shading" in x for x in self.review(p, s, r, c)))
        p, s, r, c = self.fixture()
        p["face_shading"][0].update(status="pending", next_action="later")
        self.assertTrue(any("unfinished" in x for x in self.review(p, s, r, c)))

    def test_static_sdf_can_finish_without_animation(self):
        p, s, r, c = self.fixture()
        self.assertEqual(self.review(p, s, r, c), [])

    def test_sdf_requires_intermediate_angle_and_regional_review(self):
        p, s, r, c = self.fixture()
        p["face_shading"][0]["sweep_review"]["samples"] = []
        self.assertTrue(any("ordered sweep" in x for x in self.review(p, s, r, c)))
        p, s, r, c = self.fixture()
        p["face_shading"][0]["sweep_review"]["observations"]["mouth"] = ""
        self.assertTrue(any("regional observations" in x for x in self.review(p, s, r, c)))

    def test_sweep_cannot_mix_cameras(self):
        p, s, r, c = self.fixture()
        c["d"] = {("capture", "Candidate", "DifferentView", "Left60", "Lit")}
        self.assertTrue(any("sweep must use one" in x for x in self.review(p, s, r, c)))

    def test_sweep_cannot_reuse_one_light_with_extra_unrelated_variants(self):
        p, s, r, c = self.fixture()
        c["d"] = c["a"].copy()
        c["e"].add(("capture", "Candidate", "FaceClose", "ExtraUnused", "Lit"))
        self.assertTrue(any("sweep must use one" in x for x in self.review(p, s, r, c)))

    def test_encoding_manifest_is_bound_to_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            texture, manifest = Path(folder)/"sdf.png", Path(folder)/"manifest.json"
            texture.write_bytes(b"fixture")
            sha = hashlib.sha256(texture.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(dict(schema="pmx4ue.face-sdf-bake.v2",
                texture_sha256=sha, encoding="linear_azimuth_v1")))
            audit = dict(summarize_pixels([(0, 0, 0, 1), (1, 0, 0, 1)]),
                schema="pmx4ue.face-sdf-texture.v1", texture=str(texture), sha256=sha,
                encoding="linear_azimuth_v1", encoding_provenance=dict(manifest=str(manifest),
                    manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()))
            verify_texture_report(audit)
            audit["encoding"] = "cosine_half_v1"
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_texture_report(audit)
            audit["encoding"] = "linear_azimuth_v1"
            manifest.write_text("{}")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_texture_report(audit)

    def test_old_unknown_or_mismatched_decoder_is_not_accepted(self):
        p, s, r, c = self.fixture()
        s["Face"]["face_sdf_response"] = "cosine_half_art"
        self.assertTrue(any("response mismatch" in x for x in self.review(p, s, r, c)))
        p["face_shading"][0]["light_response"] = "cosine_half_art"
        self.assertEqual(self.review(p, s, r, c), [])
        s["Face"]["face_sdf_response"] = None
        self.assertTrue(any("missing graph readback" in x for x in self.review(p, s, r, c)))
        r["sdf_audit"][1]["encoding"] = "unspecified"
        self.assertTrue(any("encoding is unknown" in x for x in self.review(p, s, r, c)))
        del r["sdf_audit"]
        self.assertTrue(any("texture invalid" in x for x in self.review(p, s, r, c)))

    def test_delivery_rejects_wrong_source_resolution(self):
        p, s, r, c = self.fixture()
        r["sdf_audit"][1]["width"] = 512
        self.assertTrue(any("1024x1024" in x for x in self.review(p, s, r, c)))
        p, s, r, c = self.fixture()
        issues = []
        with patch("tools.face_shading_delivery.verify_texture_report", return_value=("texture.png", "hash")), \
                patch("tools.face_shading_delivery.png_dimensions", return_value=(512, 512)):
            review_face_shading(p, s, {}, r, c, issues.append, {})
        self.assertTrue(any("1024x1024" in x for x in issues))

    def test_neutral_input_and_disabled_branch_cannot_be_reviewed_sdf(self):
        p, s, r, c = self.fixture()
        s["Face"]["input_audit"][0]["source"] = "generated_neutral"
        s["Face"]["effective_scalars"]["FaceMode"] = 0.0
        issues = self.review(p, s, r, c)
        self.assertTrue(any("real texture is not bound" in x for x in issues))
        self.assertTrue(any("branch is disabled" in x for x in issues))

    def test_omitted_degraded_face_cannot_be_no_face(self):
        p, s, r, c = self.fixture()
        p["face_shading"][0].update(method="not_applicable", slots=[])
        s["Face"]["effective_scalars"]["FaceMode"] = 0.0
        issues = self.review(p, s, r, c, {"Face:FaceMode": {"slot": "Face", "missing_role": "face_sdf"}})
        self.assertTrue(any("omits" in x for x in issues))

    def test_another_texture_audit_cannot_justify_the_bound_texture(self):
        p, s, r, c = self.fixture()
        s["Face"]["input_audit"][0]["import_source_sha256"] = "other_image"
        self.assertTrue(any("import source" in x for x in self.review(p, s, r, c)))

    def test_alternative_requires_its_actual_light_review(self):
        p, s, r, c = self.fixture()
        p["face_shading"][0].update(method="alternative", reason="Reviewed custom face shadow instead")
        s["Face"]["effective_scalars"]["FaceMode"] = 0.0
        self.assertEqual(self.review(p, s, r, c), [])
        c["b"] = {("capture", "Candidate", "SideClose", "Left", "Lit")}
        self.assertTrue(any("one Lit view" in x for x in self.review(p, s, r, c)))

    def test_delivery_v1_requires_explicit_migration(self):
        result = review_delivery({"schema": "pmx4ue.delivery.v1", "project": "x.uproject",
                                  "scope": ["materials"]}, "x.uproject")
        self.assertTrue(any("migrate v1" in x for x in result["unresolved"]))

    def test_delivery_checks_face_closure_even_when_debt_list_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "validation.json"
            path.write_text(json.dumps(dict(schema="mmd2ue.ue-validation.v1", passed=True,
                material_debt=[], slot_audit=[dict(slot="Face", input_audit=[],
                                                  effective_scalars={"FaceMode": 0.0})])))
            p = dict(schema="pmx4ue.delivery.v2", project="x.uproject", scope=["materials"],
                     evidence=[dict(id="validation", kind="material_validation", path=str(path.resolve()),
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
            result = review_delivery(p, "x.uproject")
            self.assertTrue(any("Declare face_shading" in x for x in result["unresolved"]))

    def test_complete_material_delivery_then_disabled_sdf_regression(self):
        # Exercise the whole delivery checker; PNG decoding is tested separately.
        with tempfile.TemporaryDirectory() as folder, patch("tools.delivery_contract.verify_report"):
            root = Path(folder)
            project = root / "Test.uproject"
            p, slots, _, cases = self.fixture()
            p.update(schema="pmx4ue.delivery.v2", project=str(project), scope=["materials"],
                     assets=[], evidence=[])
            p.update(material_review_contract=1, material_acceptance="static_lookdev",
                material_features={name: dict(status="not_applicable", slots=[], reason="Face-only regression fixture",
                    evidence=["design"]) for name in ("eye_layers", "hair_clumps", "stocking_edge")})
            p["scene_effects"] = {name: dict(status="not_selected", reason="Isolated face-shading regression fixture",
                evidence=["design"]) for name in ("outline", "rim")}
            fingerprints = {}
            for role in ("mesh", "material"):
                path = root / "Content" / (role + ".uasset")
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(role.encode())
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                fingerprints[str(path.resolve())] = sha
                p["assets"].append(dict(id=role, role=role, path="/Game/" + role,
                    sha256=sha, evidence=["build"], compatibility_note="Fixture slot mapping"))
            effect = p["effects"][0]
            effect.update(images_opened=True, reviewer="agent", observation="Three lighting angles reviewed",
                          implementation="SDF candidate", comparison_required=False,
                          comparison_reason="Lighting sweep test fixture")
            texture = root / "sdf.png"
            texture.write_bytes(png_header(1024, 1024))
            sha = hashlib.sha256(texture.read_bytes()).hexdigest()
            slots["Face"]["slot"] = "Face"
            slots["Face"]["input_audit"][0].update(expected="/Game/Character/Textures/SDF.SDF",
                                                     import_source_sha256=sha)
            audit = dict(summarize_pixels([(0, 0, 0, 1), (1, 0, 0, 1)]),
                         schema="pmx4ue.face-sdf-texture.v1", texture=str(texture), sha256=sha,
                         encoding="linear_azimuth_v1", width=1024, height=1024)
            capture = dict(captures=[dict(case="Candidate", camera={"name": "FaceClose"},
                light={"name": next(iter(rows))[3]}, mode="Lit", image={"path": h + ".png", "sha256": h})
                for h, rows in cases.items()], input_assets={"game_package_sha256": fingerprints})
            validation = dict(schema="mmd2ue.ue-validation.v1", passed=True,
                              material_debt=[], slot_audit=list(slots.values()))
            items = {"build": ("run", dict(stage="material-build", status="executed_needs_review")),
                     "design": ("review", {}), "sdf_audit": ("face_sdf_texture", audit),
                     "validation": ("material_validation", validation), "capture": ("capture", capture)}
            for ident, (kind, value) in items.items():
                path = root / (ident + ".json")
                path.write_text(json.dumps(value))
                p["evidence"].append(dict(id=ident, kind=kind, path=str(path),
                                         sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            result = review_delivery(p, project)
            self.assertEqual(result["unresolved"], [])
            self.assertEqual(result["status"], "evidence_complete_needs_human_judgment")
            slots["Face"]["effective_scalars"]["FaceMode"] = 0.0
            path = root / "validation.json"
            path.write_text(json.dumps(validation))
            next(e for e in p["evidence"] if e["id"] == "validation")["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            result = review_delivery(p, project)
            self.assertEqual(result["status"], "incomplete")
            self.assertTrue(any("branch is disabled" in x for x in result["unresolved"]))


if __name__ == "__main__":
    unittest.main()
