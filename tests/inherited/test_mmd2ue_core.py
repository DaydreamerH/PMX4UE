from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK))

from mmd2ue_core import (
    build_character_asset_names,
    build_source_audit,
    classify_texture,
    make_character_config,
    normalize_material_map,
    suggest_profile,
    validate_config,
    validate_material_map,
)


class TextureClassificationTests(unittest.TestCase):
    def test_explicit_normal_suffix_is_candidate_not_binding(self):
        result = classify_texture(Path("cloth_body_n.png"))
        self.assertEqual(result[0].role, "normal")
        self.assertIn(result[0].confidence, {"high", "medium"})

    def test_unknown_texture_stays_unclassified(self):
        result = classify_texture(Path("花纹甲.png"))
        self.assertEqual(result[0].role, "unclassified")

    def test_sphere_map_is_not_base_color(self):
        result = classify_texture(Path("hair-a.spa"))
        self.assertEqual(result[0].role, "sphere_map")


class ProfileSuggestionTests(unittest.TestCase):
    def test_slot_tokens_suggest_stocking_and_hair(self):
        self.assertEqual(suggest_profile("Cth3-Socks"), "stocking")
        self.assertEqual(suggest_profile("HairA"), "hair")
        self.assertEqual(suggest_profile("Eyes"), "iris")

    def test_fallback_is_cloth(self):
        self.assertEqual(suggest_profile("Cth2-Apron"), "cloth")


class ConfigAndAuditTests(unittest.TestCase):
    def test_init_and_audit_are_non_destructive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Test.uproject").write_text("{}", encoding="utf-8")
            source = root / "input"
            source.mkdir()
            pmx = source / "hero.pmx"
            pmx.write_bytes(b"PMX ")
            texture = source / "body_d.png"
            texture.write_bytes(b"not-a-real-png")
            config = make_character_config(root, "Hero01", "Hero", pmx, source, 0.08)
            self.assertFalse([item for item in validate_config(config, root) if item["level"] == "error"])
            audit = build_source_audit(config, root)
            self.assertEqual(audit["summary"]["texture_count"], 1)
            self.assertEqual(audit["summary"]["automatic_bindings"], 0)
            self.assertEqual(texture.read_bytes(), b"not-a-real-png")

    def test_invalid_character_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                make_character_config(root, "角色 1", "Hero", root / "a.pmx", root, 0.08)


def _make_config(root: Path) -> dict:
    source = root / "input"
    source.mkdir(exist_ok=True)
    pmx = source / "hero.pmx"
    pmx.write_bytes(b"PMX ")
    return make_character_config(root, "Hero01", "Hero", pmx, source, 0.08)


class NormalizationTests(unittest.TestCase):
    def test_v2_and_v3_collapse_to_same_slot_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = _make_config(root)
            v2 = {
                "schema": "mmd2ue.material-map.v2",
                "profiles": {"face_skin": {"scalars": {}, "vectors": {}}},
                "slot_groups": [
                    {"slots": ["Face"], "profile": "face_skin", "base": "face_d"},
                    {"slots": ["HairA", "HairB"], "profile": "hair", "base": "hair_d"},
                ],
            }
            v3 = {
                "schema": "mmd2ue.material-map.v3",
                "profiles": {"face_skin": {"scalars": {}, "vectors": {}}, "hair": {"scalars": {}, "vectors": {}}},
                "slots": [
                    {"slot": "Face", "profile": "face_skin", "textures": {"base_color": "face_d"}},
                    {"slot": "HairA", "profile": "hair", "textures": {"base_color": "hair_d"}},
                    {"slot": "HairB", "profile": "hair", "textures": {"base_color": "hair_d"}},
                ],
            }
            n2 = normalize_material_map(config, v2)
            n3 = normalize_material_map(config, v3)
            self.assertEqual([s["slot"] for s in n2["slots"]], ["Face", "HairA", "HairB"])
            self.assertEqual(len(n3["slots"]), 3)
            self.assertEqual(n2["defaults"]["base_color"], "face_d")
            self.assertFalse([i for i in validate_material_map(n3) if i["level"] == "error"])

    def test_unassigned_profile_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = _make_config(root)
            v3 = {"schema": "mmd2ue.material-map.v3", "slots": [{"slot": "Face", "profile": "unassigned"}]}
            issues = validate_material_map(normalize_material_map(config, v3))
            self.assertTrue(any(i["level"] == "error" for i in issues))


class AssetNameTests(unittest.TestCase):
    def test_names_follow_character_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = _make_config(root)
            names = build_character_asset_names(config, root)
            self.assertEqual(names["mesh_asset"], "SK_Hero01")
            self.assertEqual(names["master_asset"], "M_MMD_Hero01_Master")
            self.assertTrue(names["ue_root"].endswith("/Hero01"))


if __name__ == "__main__":
    unittest.main()
