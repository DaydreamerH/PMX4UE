import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.material_preview_contract import png_evidence, CapturePixelsError, verify_environment_review
from test_preview_framing import receipt


def chunk(kind, value):
    return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)


def png(rows, channels=4, filters=None, compressed=None):
    width, height = len(rows[0]) // channels, len(rows)
    raw, previous = bytearray(), bytes(len(rows[0]))
    for n, row in enumerate(rows):
        kind = (filters or [0] * height)[n]
        raw.append(kind)
        for i, value in enumerate(row):
            a = row[i-channels] if i >= channels else 0
            b = previous[i]
            c = previous[i-channels] if i >= channels else 0
            p = a + b - c
            # Independent nearest-candidate Paeth encoder, tie order a,b,c.
            paeth = min((a, b, c), key=lambda candidate: abs(p - candidate))
            predictor = (0, a, b, (a+b)//2, paeth)[kind]
            raw.append((value - predictor) & 255)
        previous = row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8,
            6 if channels == 4 else 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw) if compressed is None else compressed) + chunk(b"IEND", b""))


class PixelEvidenceTests(unittest.TestCase):
    def test_all_png_filters_rgb_rgba(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "filters.png"
            for channels in (3, 4):
                rows = [bytes([30+y, 60-y, 90, *([255] if channels == 4 else []),
                               100, 120+y, 150-y, *([255] if channels == 4 else [])]) for y in range(5)]
                path.write_bytes(png(rows, channels, list(range(5))))
                pixels = png_evidence(path, 2, 5)["pixels"]
                self.assertEqual(pixels["rgb_mean"], [66, 90, 119])
                self.assertEqual(pixels["alpha_min"], 255)
                self.assertEqual(pixels["warnings"], [])

    def test_transparent_bright_rgb_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bright.png"
            for alpha in (0, 128, 254):
                path.write_bytes(png([bytes([240, 180, 120, alpha])]))
                with self.assertRaisesRegex(CapturePixelsError, "Rebuild.*restart.*recapture"):
                    png_evidence(path, 1, 1)

    def test_black_is_warning_not_automatic_material_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "black.png"
            path.write_bytes(png([bytes([0, 0, 0, 255])]))
            result = png_evidence(path, 1, 1)
            self.assertEqual(result["pixels"]["near_black_fraction"], 1)
            self.assertTrue(result["pixels"]["warnings"])

    def test_crc_valid_but_invalid_pixel_stream_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.png"
            for compressed in (b"not-deflate", zlib.compress(b""), zlib.compress(b"\0" * 6),
                               zlib.compress(b"\0" * 5) + b"trailing", zlib.compress(b"\5" + b"\0" * 4)):
                path.write_bytes(png([bytes([0, 0, 0, 255])], compressed=compressed))
                with self.assertRaises(CapturePixelsError):
                    png_evidence(path, 1, 1)

    def test_native_opaque_policy_precedes_compression(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "unreal/PMX4UE/Source/PMX4UEEditor/Private/PMX4UEAgentMCPTools.cpp").read_text()
        capture = source.split("::CaptureVisibleEditorViewport(", 1)[1].split("::CheckPreviewTextureResidency(", 1)[0]
        self.assertLess(capture.index("Pixel.A = 255"), capture.index("PNGCompressImageArray"))


class EnvironmentReviewTests(unittest.TestCase):
    def fixture(self, tmp):
        image = Path(tmp) / "daylight.png"
        image.write_bytes(png([bytes([100, 120, 140, 255])]))
        evidence = png_evidence(image, 1, 1)
        root = Path(__file__).resolve().parents[1]
        profile = json.loads((root / "templates/material_preview.example.json").read_text())
        profile.update(exposure_ev100=0, cameras=profile["cameras"][:1], lights=profile["lights"][:1])
        rows = [{"case": "Baseline", "camera": profile["cameras"][0], "light": profile["lights"][0],
                 "mode": mode, "image": evidence, "capture_source": "visible_viewport_backbuffer",
                 "viewport_width": 1, "viewport_height": 1, "r_screen_percentage_setting": 100,
                 "actual_sun": dict(pitch=-30, yaw=0, roll=0, intensity=6),
                 "framing": receipt(profile["cameras"][0], profile["mesh"]),
                 "texture_residency": {"ready": True, "checked": 1, "pending": 0, "textures": [
                     {"ready": True, "available_mips": 1, "resident_mips": 1}]}} for mode in profile["modes"]]
        report = {"status": "captured_visual_pending", "profile": profile, "captures": rows, "expected_captures": len(rows),
                  "daylight_map": dict(path=profile["environment"]["template"], source_unchanged=True, saved_by_preview=False),
                  "input_assets_unchanged": True, "input_assets": {"game_package_sha256": {}}}
        path = Path(tmp) / "baseline.json"
        path.write_text(json.dumps(report))
        candidate = copy.deepcopy(profile)
        candidate["cases"].append({"name": "Candidate", "slots": []})
        candidate["environment_review"] = dict(report=str(path), report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              images_opened=True, reviewer="test fixture", lit_image_sha256=[evidence["sha256"]],
              exposure_reason="Synthetic regression, not actual visual approval",
              observations=dict(sky="visible", ground="visible", character="visible"))
        return candidate, path, image

    def test_reviewed_calibration_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, path, _ = self.fixture(tmp)
            self.assertIn(str(path), verify_environment_review(profile))

    def test_unreviewed_or_wrong_settings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, _, _ = self.fixture(tmp)
            for field, value in (("exposure_ev100", 12), ("mesh", "/Game/Other"), ("lights", [{"name": "Other"}])):
                changed = copy.deepcopy(profile)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, "calibration differs"):
                    verify_environment_review(changed)
            profile["environment_review"]["images_opened"] = False
            with self.assertRaisesRegex(ValueError, "Open and review"):
                verify_environment_review(profile)

    def test_changed_evidence_and_recursive_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, path, image = self.fixture(tmp)
            original = image.read_bytes()
            image.write_bytes(png([bytes([200, 120, 140, 255])]))
            with self.assertRaisesRegex(ValueError, "Screenshot changed"):
                verify_environment_review(profile)
            image.write_bytes(original)
            report = json.loads(path.read_text())
            report["profile"]["cases"] = profile["cases"]
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "report changed"):
                verify_environment_review(profile)
            profile["environment_review"]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "Baseline-only"):
                verify_environment_review(profile)

    def test_diagnostic_baseline_does_not_require_prior_review(self):
        self.assertEqual(verify_environment_review({"schema": "pmx4ue.material-preview.v3",
                                                  "cases": [{"name": "Baseline", "slots": []}]}), [])

    def test_multicase_default_exposure_without_prior_review(self):
        self.assertEqual(verify_environment_review({"schema": "pmx4ue.material-preview.v3",
            "exposure_ev100": None, "cases": [{"name": "Baseline", "slots": []},
                                              {"name": "Candidate", "slots": []}]}), [])

    def test_optional_default_exposure_reference_and_no_chains(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, path, _ = self.fixture(tmp)
            baseline = json.loads(path.read_text())
            baseline["profile"]["exposure_ev100"] = profile["exposure_ev100"] = None
            path.write_text(json.dumps(baseline))
            profile["environment_review"]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(str(path), verify_environment_review(profile))
            baseline["profile"]["environment_review"] = {}
            path.write_text(json.dumps(baseline))
            profile["environment_review"]["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "must not chain"):
                verify_environment_review(profile)
