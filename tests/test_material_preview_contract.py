import ast
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from types import SimpleNamespace

from tools.material_preview_contract import validate, capture_jobs, png_evidence, verify_report
from tools.fbx_property_types import encoder_methods
from pmx4ue import recipe
from test_preview_framing import receipt


def chunk(kind, value):
    return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)


class PreviewContractTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "templates/material_preview.example.json"
        self.profile = json.loads(path.read_text())
        self.profile["reviewed"] = True

    def test_profile_and_isolation(self):
        validate(self.profile, "/Game/PMX4UE/Character/v1")
        self.profile["level"] = "/Game/MyProductionLevel"
        with self.assertRaisesRegex(ValueError, "do not create a custom"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_visible_capture_required(self):
        self.assertEqual(self.profile["schema"], "pmx4ue.material-preview.v3")
        self.assertEqual(self.profile["capture"]["mode"], "visible_viewport_backbuffer")
        p = copy.deepcopy(self.profile)
        p["capture"]["minimum_width"] = 400
        with self.assertRaisesRegex(ValueError, "without a size threshold"):
            validate(p, "/Game/PMX4UE/Character/v1")
        p = copy.deepcopy(self.profile)
        p["capture"]["mode"] = "offscreen"
        with self.assertRaisesRegex(ValueError, "visible"):
            validate(p, "/Game/PMX4UE/Character/v1")
        p = copy.deepcopy(self.profile)
        p["width"] = 1920
        with self.assertRaisesRegex(ValueError, "remove legacy requested dimensions"):
            validate(p, "/Game/PMX4UE/Character/v1")

    def test_material_preview_launches_visible_editor(self):
        c = {"pmx4ue": {"engine": "D:/Engine", "physics_profile": "physics.json",
                         "material_preview_profile": "preview.json", "material_preview_run": "v1"},
             "character": {"id": "Character"}, "paths": {"ue_root": "/Game/PMX4UE/Character/v1"}}
        spec = recipe(c, Path("D:/Project/Character.uproject"), Path("D:/Project/Saved/PMX4UE/Character/v1"),
                      "material-preview")
        self.assertIn("UnrealEditor.exe", spec["argv"][0])
        self.assertNotIn("-RenderOffscreen", spec["argv"])

    def test_modified_baseline_and_clamped_camera_rejected(self):
        p = copy.deepcopy(self.profile)
        p["cases"][0]["outline"] = "/Game/Outline"
        with self.assertRaises(ValueError):
            validate(p, "/Game/PMX4UE/Character/v1")
        self.profile["cameras"][0]["distance"] = 10
        with self.assertRaisesRegex(ValueError, "Migrate"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_retained_mesh_requires_exact_explicit_selection(self):
        self.profile["mesh"] = "/Game/PMX4UE/Character/base/Mesh/SK_Character"
        with self.assertRaisesRegex(ValueError, "retained mesh"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")
        validate(self.profile, "/Game/PMX4UE/Character/v1", self.profile["mesh"])
        with self.assertRaises(ValueError):
            validate(self.profile, "/Game/PMX4UE/Character/v1", "/Game/OtherMesh")

    def test_lit_default_and_optional_diagnostics(self):
        self.assertEqual(self.profile["modes"], ["Lit"])
        validate(self.profile, "/Game/PMX4UE/Character/v1")
        self.assertEqual(len(capture_jobs(self.profile)), 2)
        del self.profile["modes"]
        self.assertEqual(len(capture_jobs(self.profile)), 2)

    def test_light_sweep_template_is_small_and_requires_model_review(self):
        path = Path(__file__).resolve().parents[1] / "templates/material_light_sweep.example.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(profile["reviewed"])
        profile["reviewed"] = True
        with self.assertRaisesRegex(ValueError, "Invalid daylight override"):
            validate(profile, "/Game/PMX4UE/Character/v1")
        profile["lights"][1]["yaw_offset"] = 37
        validate(profile, "/Game/PMX4UE/Character/v1")
        self.assertEqual(len(capture_jobs(profile)), 2)
        self.assertEqual(capture_jobs(profile)[0][2]["name"], profile["primary_light"])
        self.assertEqual(profile["lights"][0], {"name": "DefaultDaylight"})
        profile["lights"].append({"name": "AlternateAngle", "yaw_offset": -52})
        validate(profile, "/Game/PMX4UE/Character/v1")
        self.assertEqual(len(capture_jobs(profile)), 3)
        profile["primary_light"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "primary_light"):
            validate(profile, "/Game/PMX4UE/Character/v1")

    def test_invalid_modes_rejected(self):
        for modes in ([], ["Unlit"], ["Lit", "Lit"], ["Lit", "Invalid"], "Lit", ["Lit", {}]):
            self.profile["modes"] = modes
            with self.assertRaisesRegex(ValueError, "Capture modes"):
                validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_diagnostics_do_not_expand_ab_light_matrix(self):
        self.profile["cases"].append({"name": "Candidate", "slots": []})
        self.profile["lights"].append({"name": "SideLight", "yaw_offset": 90})
        self.profile["diagnostic_captures"] = [dict(case="Baseline", camera="Front",
            light="DefaultDaylight", mode="WorldNormal", reason="Investigate a face normal seam")]
        validate(self.profile, "/Game/PMX4UE/Character/v1")
        jobs = capture_jobs(self.profile)
        self.assertEqual(len(jobs), 9)  # 2 cases x 2 cameras x 2 lights + ONE diagnostic
        self.assertEqual(sum(m == "WorldNormal" for _, _, _, m in jobs), 1)
        self.profile["diagnostic_captures"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate diagnostic"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_diagnostic_references_and_reason_required(self):
        d = dict(case="Baseline", camera="Front", light="DefaultDaylight", mode="Unlit", reason="Check atlas color")
        for field, value in (("case", "Missing"), ("camera", "Missing"), ("light", "Missing"),
                             ("mode", "Lit"), ("reason", "")):
            self.profile["diagnostic_captures"] = [{**d, field: value}]
            with self.assertRaises(ValueError):
                validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_legacy_explicit_modes_keep_their_capture_matrix(self):
        self.profile["modes"] = ["Lit", "Unlit", "WorldNormal"]
        validate(self.profile, "/Game/PMX4UE/Character/v1")
        self.assertEqual(len(capture_jobs(self.profile)), 6)
        self.profile["diagnostic_captures"] = [dict(case="Baseline", camera="Front",
            light="DefaultDaylight", mode="Unlit", reason="Already in main matrix")]
        with self.assertRaisesRegex(ValueError, "Duplicate diagnostic"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_daylight_baseline_inherits_template(self):
        p = self.profile
        self.assertEqual(p["environment"]["template"], "/Engine/Maps/Templates/OpenWorld")
        self.assertIsNone(p["exposure_ev100"])
        self.assertEqual(set(p["lights"][0]), {"name"})
        self.assertEqual(len(p["lights"]), 1)
        validate(p, "/Game/PMX4UE/Character/v1")
        p["environment"]["template"] = "/Game/Production"
        with self.assertRaisesRegex(ValueError, "Open World"):
            validate(p, "/Game/PMX4UE/Character/v1")

    def test_daylight_ab_allows_default_or_explicit_exposure_without_review(self):
        self.profile["cases"].append({"name": "Candidate", "slots": []})
        validate(self.profile, "/Game/PMX4UE/Character/v1")
        self.profile["exposure_ev100"] = 12.0
        validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_runtime_default_does_not_create_exposure_override(self):
        source = Path(__file__).resolve().parents[1] / "tools/ue_material_preview.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If) and
                      any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and
                          call.func.attr == "setup_fixed_exposure" for call in ast.walk(node)))
        code = compile(ast.Module(body=[branch], type_ignores=[]), str(source), "exec")
        calls = []
        for exposure in (None, 0.0, 12.0):
            runtime = SimpleNamespace(p={"exposure_ev100": exposure},
                                      setup_fixed_exposure=lambda: calls.append("override"))
            before = len(calls)
            exec(code, {"self": runtime})
            self.assertEqual(len(calls) - before, int(exposure is not None))

    def test_optional_environment_review_still_requires_valid_shape(self):
        for invalid in (None, {}, {"images_opened": False}):
            self.profile["environment_review"] = invalid
            with self.assertRaisesRegex(ValueError, "environment_review"):
                validate(self.profile, "/Game/PMX4UE/Character/v1")
        self.profile["environment_review"] = {
            "images_opened": True, "reviewer": "test", "report": "calibration.json",
            "report_sha256": "placeholder", "lit_image_sha256": ["placeholder"],
            "exposure_reason": "test shape only; execution checks real evidence",
            "observations": {"sky": "visible", "ground": "visible", "character": "visible"}}
        validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_daylight_rejects_legacy_lights_and_bad_position(self):
        p = copy.deepcopy(self.profile)
        p["lights"][0]["intensity"] = 6
        with self.assertRaisesRegex(ValueError, "retain template"):
            validate(p, "/Game/PMX4UE/Character/v1")
        p = copy.deepcopy(self.profile)
        p["lights"].append({"name": "SideDaylight", "yaw": 90})
        with self.assertRaisesRegex(ValueError, "Unknown daylight"):
            validate(p, "/Game/PMX4UE/Character/v1")
        self.profile["environment"]["model_location"] = [0, 0, float("nan")]
        with self.assertRaisesRegex(ValueError, "model_location"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_legacy_preview_keeps_old_semantics(self):
        p = copy.deepcopy(self.profile)
        p["schema"] = "pmx4ue.material-preview.v1"
        p["cameras"] = [dict(name="Front", azimuth=90, distance=260, height=8, fov=38)]
        del p["environment"]
        p["level"] = "/Game/PMX4UE/Character/v1/Preview/Legacy_v1"
        p["width"], p["height"] = 1200, 1200
        p["exposure_ev100"] = 3
        p["lights"] = [{"name": "Key", "pitch": -35, "yaw": -45, "intensity": 6}]
        validate(p, "/Game/PMX4UE/Character/v1")

    def test_legacy_daylight_schema_remains_readable(self):
        p = copy.deepcopy(self.profile)
        p["schema"] = "pmx4ue.material-preview.v2"
        p["cameras"] = [dict(name="Front", azimuth=90, distance=260, height=8, fov=38)]
        p["level"] = "/Game/PMX4UE/Character/v1/Preview/Legacy_v2"
        p["width"], p["height"] = 1200, 1200
        validate(p, "/Game/PMX4UE/Character/v1")

    def test_png_complete_partial_crc_and_size(self):
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(data)
            self.assertEqual(png_evidence(path, 1, 1)["bytes"], len(data))
            with self.assertRaisesRegex(ValueError, "size"):
                png_evidence(path, 2, 2)
            path.write_bytes(data[:-4])
            with self.assertRaises(ValueError):
                png_evidence(path, 1, 1)
            path.write_bytes(data[:20] + bytes([data[20] ^ 1]) + data[21:])
            with self.assertRaisesRegex(ValueError, "CRC"):
                png_evidence(path, 1, 1)

    def test_compiled_is_not_captured(self):
        with self.assertRaises(ValueError):
            verify_report({"status": "compiled_visual_pending"})

    def test_legacy_capture_cannot_be_accepted(self):
        with self.assertRaisesRegex(ValueError, "Legacy screenshot"):
            verify_report({"status": "captured_visual_pending",
                           "profile": {"schema": "pmx4ue.material-preview.v2"}})

    def test_offscreen_png_cannot_pass_v3_gate(self):
        pixels = b"\x89PNG\r\n\x1a\n" + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ) + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.png"
            path.write_bytes(pixels)
            image = png_evidence(path, 1, 1)
            p = copy.deepcopy(self.profile)
            p["cameras"], p["lights"], p["modes"] = p["cameras"][:1], p["lights"][:1], ["Lit"]
            row = {"case": "Baseline", "camera": p["cameras"][0], "light": p["lights"][0],
                   "mode": "Lit", "image": image, "capture_source": "offscreen",
                   "viewport_width": 1, "viewport_height": 1, "r_screen_percentage_setting": 100}
            report = {"status": "captured_visual_pending", "profile": p, "captures": [row],
                      "expected_captures": 1}
            with self.assertRaisesRegex(ValueError, "Offscreen"):
                verify_report(report)
            row["capture_source"] = "visible_viewport_backbuffer"
            report["daylight_map"] = {"path": p["environment"]["template"],
                                      "source_unchanged": True, "saved_by_preview": False}
            report["input_assets_unchanged"] = True
            report["input_assets"] = {"game_package_sha256": {}}
            with self.assertRaisesRegex(ValueError, "textures"):
                verify_report(report)
            row["texture_residency"] = {"ready": True, "checked": 1, "pending": 0,
                                        "textures": [{"path": "/Game/T", "ready": True,
                                                      "available_mips": 4, "resident_mips": 4}]}
            with self.assertRaisesRegex(ValueError, "receipt"):
                verify_report(report)
            row["framing"] = receipt(p["cameras"][0], p["mesh"])
            verify_report(report)  # Geometry checks impose no pixel minimum; visual review is separate.

            # A requested one-off diagnostic must be present, without requiring
            # additional diagnostic modes across the full capture matrix.
            p["diagnostic_captures"] = [dict(case="Baseline", camera=p["cameras"][0]["name"],
                light=p["lights"][0]["name"], mode="WorldNormal", reason="Synthetic normal seam check")]
            with self.assertRaisesRegex(ValueError, "Missing or duplicated"):
                verify_report(report)
            diagnostic = copy.deepcopy(row)
            diagnostic["mode"] = "WorldNormal"
            report["captures"].append(diagnostic)
            report["expected_captures"] = 2
            verify_report(report)
            report["captures"].append(copy.deepcopy(diagnostic))
            report["expected_captures"] = 3
            with self.assertRaisesRegex(ValueError, "Missing or duplicated"):
                verify_report(report)

    def test_both_fbx_codec_contracts(self):
        codec = SimpleNamespace(add_bool=lambda v: v, add_char=lambda v: v, add_int8=lambda v: v)
        old = encoder_methods(SimpleNamespace(BOOL=ord('C'), INT8=ord('Z')), codec)
        new = encoder_methods(SimpleNamespace(BOOL=ord('B'), CHAR=ord('C'), INT8=ord('Z')), codec)
        self.assertEqual(old[ord('C')], "add_bool")
        self.assertEqual(new[ord('C')], "add_char")
        self.assertEqual(new[ord('B')], "add_bool")
        with self.assertRaises(ValueError):
            encoder_methods(SimpleNamespace(BOOL=ord('B')), SimpleNamespace())


if __name__ == "__main__":
    unittest.main()
