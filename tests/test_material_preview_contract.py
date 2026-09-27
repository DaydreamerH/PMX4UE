import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from types import SimpleNamespace

from tools.material_preview_contract import validate, png_evidence, verify_report
from tools.fbx_property_types import encoder_methods


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
        with self.assertRaisesRegex(ValueError, "namespace"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_modified_baseline_and_clamped_camera_rejected(self):
        p = copy.deepcopy(self.profile)
        p["cases"][0]["outline"] = "/Game/Outline"
        with self.assertRaises(ValueError):
            validate(p, "/Game/PMX4UE/Character/v1")
        self.profile["cameras"][0]["distance"] = 10
        with self.assertRaisesRegex(ValueError, "clamped"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

    def test_retained_mesh_requires_exact_explicit_selection(self):
        self.profile["mesh"] = "/Game/PMX4UE/Character/base/Mesh/SK_Character"
        with self.assertRaisesRegex(ValueError, "retained mesh"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")
        validate(self.profile, "/Game/PMX4UE/Character/v1", self.profile["mesh"])
        with self.assertRaises(ValueError):
            validate(self.profile, "/Game/PMX4UE/Character/v1", "/Game/OtherMesh")

    def test_missing_visual_modes_rejected(self):
        self.profile["modes"] = ["Lit"]
        with self.assertRaisesRegex(ValueError, "WorldNormal"):
            validate(self.profile, "/Game/PMX4UE/Character/v1")

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
