import unittest
import struct
from material_input_policy import neutral_png, effective_scalars
from mmd2ue_core import normalize_material_map, validate_material_map


class MaterialInputPolicyTests(unittest.TestCase):
    def test_typed_neutral_has_deterministic_size_and_distinct_data(self):
        normal = neutral_png("normal")
        self.assertEqual(normal[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack_from(">II", normal, 16), (4, 4))
        self.assertNotEqual(normal, neutral_png("rmo"))
        self.assertEqual(normal, neutral_png("normal"))

    def test_missing_input_creates_debt_even_for_explicit_override(self):
        entry = dict(slot="Hair", textures={}, overrides={"scalars": {"HairHighlightStrength": 1}})
        scalars, debt = effective_scalars(entry, {}, "master")
        self.assertEqual(scalars["HairHighlightStrength"], 0)
        self.assertEqual(debt[0]["id"], "Hair:HairHighlightStrength")

    def test_authored_inputs_and_custom_contract_not_disabled(self):
        entry = dict(slot="Hair", textures={"spec_mask": "hair_mask"})
        for route in ("master", "hair_custom"):
            values, debt = effective_scalars(entry, {"scalars": {"HairHighlightStrength": 1}}, route)
            self.assertEqual(values["HairHighlightStrength"], 1)
            self.assertEqual(debt, [])

    def test_normal_color_alias_rejected_before_import(self):
        value = normalize_material_map({}, {"profiles": {"a": {}}, "slots": [
            {"slot": "A", "profile": "a", "textures": {"base_color": "shared", "normal": "shared"}}]})
        self.assertIn("conflicting_texture_types", {i["code"] for i in validate_material_map(value)})
