import unittest
from mmd2ue_core import normalize_material_map, validate_material_map


class MaterialParentRoutes(unittest.TestCase):
    def make(self, parent=None, parents=None, specials=None):
        return normalize_material_map({"character": {"id": "Example"}}, {
            "profiles": {"reviewed_graph": {"scalars": {}, "vectors": {}}},
            "parent_assets": parents or {}, "specials": specials or {},
            "slots": [{"slot": "Surface", "profile": "reviewed_graph", "parent": parent,
                       "textures": {"base_color": "source", "normal": "neutral_n", "rmo": "neutral_rmo"}}]})

    def errors(self, material_map):
        return {e["code"] for e in validate_material_map(material_map) if e["level"] == "error"}

    def test_custom_parent_survives_normalization(self):
        path = "/Game/PMX4UE/Example/v1/Materials/Parents/M_Hair"
        value = self.make("hair_custom", {"hair_custom": path})
        self.assertEqual(value["parent_assets"]["hair_custom"], path)
        self.assertEqual(self.errors(value), set())

    def test_unknown_parent_does_not_fall_back(self):
        self.assertIn("unknown_parent", self.errors(self.make("hair_typo")))

    def test_reserved_alias_rejected(self):
        self.assertIn("invalid_parent_alias", self.errors(self.make("master", {"master": "/Game/Other"})))

    def test_non_string_parent_is_reported(self):
        self.assertIn("invalid_parent", self.errors(self.make(["stocking"])))

    def test_conflicting_special_and_slot_parent_rejected(self):
        self.assertIn("conflicting_parents", self.errors(self.make("stocking", specials={"cloth": ["Surface"]})))

    def test_family_and_legacy_routes(self):
        for route in (None, "master", "eye_add", "eye_multiply", "stocking", "cloth"):
            self.assertEqual(self.errors(self.make(route)), set())

    def test_family_cannot_inherit_other_slots_normal(self):
        value = self.make("stocking")
        value["slots"][0]["textures"]["normal"] = None
        self.assertIn("missing_family_texture", self.errors(value))


if __name__ == "__main__":
    unittest.main()
