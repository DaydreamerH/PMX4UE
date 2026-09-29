import copy
import ast
import json
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.preview_framing import camera_spec, verify_framing, require


def receipt(camera, mesh, width=1, height=1):
    """Synthetic geometry receipt, not visual evidence."""
    f = camera_spec(camera)
    return dict(schema="pmx4ue.subject-frame.v1", ok=True, actor="/Temp/Test.Subject", mesh=mesh,
                kind=f["kind"], target=f.get("bone", "bounds_fraction") if f["kind"] == "detail" else "mesh_bounds",
                subject_visible=True, in_front=True, margin=f["margin"], fov=f["fov"],
                viewport_width=width, viewport_height=height, rect=[.2, .1, .8, .9])


class FramingTests(unittest.TestCase):
    def test_runtime_retry_is_bounded_and_hidden_is_not_retried(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "tools/ue_material_preview.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Preview")
        tick = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "tick")
        scope = dict(json=json, require=require, native=lambda value: json.loads(value),
                     time=SimpleNamespace(monotonic=lambda: 10.), traceback=traceback)
        exec(compile(ast.Module(body=[tick], type_ignores=[]), "actual_preview_tick", "exec"), scope)
        for case in ("geometry", "hidden", "exhausted"):
            fit_calls, errors = [], []
            response = dict(ok=False, error="subject is hidden") if case == "hidden" else dict(
                ok=False, schema="pmx4ue.subject-frame.v1", error="framing clipped")
            api = SimpleNamespace(
                check_preview_texture_residency=lambda *a: json.dumps(dict(ok=True, ready=True, pending=0)),
                capture_visible_editor_viewport=lambda *a: json.dumps(response),
                frame_preview_subject=lambda *a: fit_calls.append(a) or json.dumps(dict(ok=True)))
            preview = SimpleNamespace(phase="warmup", deadline=100., since=0.,
                p=dict(warmup_seconds=2), api=api, actor=SimpleNamespace(get_actor_label=lambda: "Subject"),
                token="test", index=0, camera_json="{}", row={}, finish=errors.append)
            if case == "exhausted":
                preview.row["framing_retries"] = [response, response]
            scope["tick"](preview, 0.)
            if case == "geometry":
                self.assertEqual(len(fit_calls), 1)
                self.assertEqual(len(preview.row["framing_retries"]), 1)
                self.assertEqual(preview.since, 10.)
                self.assertFalse(errors)
            else:
                self.assertFalse(fit_calls)
                self.assertEqual(len(errors), 1)

    def test_capture_rechecks_subject_before_png_write(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "unreal/PMX4UE/Source/PMX4UEEditor/Private/PMX4UEAgentMCPTools.cpp").read_text()
        capture = source.split("::CaptureVisibleEditorViewport(", 1)[1].split("::CheckPreviewTextureResidency(", 1)[0]
        self.assertLess(capture.index("Viewport->Draw()"), capture.index("FramePreviewSubject(ActorLabel, CameraJson, false)"))
        self.assertLess(capture.index("FramePreviewSubject(ActorLabel, CameraJson, false)"), capture.index("ReadPixels"))

    def setUp(self):
        self.camera = dict(name="Front", azimuth=90, elevation=0, fov=38,
                           framing=dict(kind="full_body", margin=.08))
        self.row = dict(camera=self.camera, viewport_width=1, viewport_height=1,
                        framing=receipt(self.camera, "/Game/Mesh"))

    def test_valid_no_pixel_minimum(self):
        verify_framing(self.row, "/Game/Mesh")

    def test_old_or_ambiguous_camera_rejected(self):
        with self.assertRaisesRegex(ValueError, "Migrate"):
            camera_spec(dict(name="Detail", azimuth=90, distance=120, height=30, fov=35))
        self.camera["framing"] = dict(kind="detail", margin=.08, extent_cm=[12,12,18], offset_cm=[0,0,0])
        with self.assertRaisesRegex(ValueError, "one actual bone"):
            camera_spec(self.camera)
        self.camera["framing"]["bone"] = "ActualHead"
        self.assertEqual(camera_spec(self.camera)["bone"], "ActualHead")

    def test_detail_wrong_part_rejected(self):
        self.camera["framing"] = dict(kind="detail", margin=.08, bone="ActualHead", extent_cm=[12,12,18], offset_cm=[0,0,0])
        self.row["framing"] = receipt(self.camera, "/Game/Mesh")
        verify_framing(self.row, "/Game/Mesh")
        self.row["framing"]["target"] = "mesh_bounds"
        with self.assertRaisesRegex(ValueError, "wrong body part"):
            verify_framing(self.row, "/Game/Mesh")

    def test_hidden_clipped_tiny_wrong_mesh_or_viewport(self):
        for key, value in (("subject_visible", False), ("in_front", False), ("mesh", "/Game/Other"),
                           ("viewport_width", 2), ("rect", [-.1, .1, .8, .9]),
                           ("rect", [.45, .45, .55, .55]), ("rect", [float('nan'),.1,.8,.9]),
                           ("ok", False)):
            row = copy.deepcopy(self.row)
            row["framing"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_framing(row, "/Game/Mesh")
        del self.row["framing"]
        with self.assertRaisesRegex(ValueError, "receipt"):
            verify_framing(self.row, "/Game/Mesh")
