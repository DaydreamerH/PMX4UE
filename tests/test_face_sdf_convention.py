import ast
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
from face_sdf_convention import analyze_monotonicity, light_threshold
from mmd2ue_core import validate_material_map

ROOT = Path(__file__).resolve().parents[1]


class FaceConventionTests(unittest.TestCase):
    def test_linear_bake_angles_match_decoder_in_both_hemispheres_and_elevations(self):
        for elevation in (0, 35, 80):
            horizontal = math.cos(math.radians(elevation))
            for degrees in range(-180, 181, 5):
                a = math.radians(degrees)
                actual = light_threshold(horizontal * math.cos(a), horizontal * math.sin(a))
                self.assertAlmostEqual(actual, abs(degrees)/180, places=5)
        self.assertEqual(light_threshold(0, 0), .5)

    def test_old_half_cosine_is_not_the_bakers_encoding(self):
        self.assertAlmostEqual(light_threshold(math.cos(math.pi/4), math.sin(math.pi/4)), .25)
        self.assertGreater(abs(.25 - (1-math.cos(math.pi/4))/2), .1)

    def test_response_policy_rejects_unknown_mode(self):
        mapping = {"slots": [], "profiles": {}, "policies": {"face_sdf_light_response": "guess"}}
        self.assertIn("invalid_face_sdf_light_response", {i["code"] for i in validate_material_map(mapping)})
        mapping["policies"]["face_sdf_light_response"] = "cosine_half_art"
        self.assertNotIn("invalid_face_sdf_light_response", {i["code"] for i in validate_material_map(mapping)})

    def test_actual_material_helper_evaluates_same_math(self):
        # Execute the actual node-construction function with arithmetic nodes;
        # catches swapped atan2 X/Y, missing abs, wrong scale and pole handling.
        class Node:
            def __init__(self, kind):
                self.kind, self.inputs, self.values = kind, {}, {}
        def evaluate(node):
            if isinstance(node, (int, float)):
                return node
            inputs = {k: evaluate(v) for k, v in node.inputs.items()}
            if node.kind == "Abs": return abs(inputs[""])
            if node.kind == "Max": return max(inputs["A"], node.values["const_b"])
            if node.kind == "Atan2": return math.atan2(inputs["Y"], inputs["X"])
            if node.kind == "Multiply": return inputs["A"] * node.values["const_b"]
            raise AssertionError(node.kind)
        fake = SimpleNamespace(MaterialExpressionAbs="Abs", MaterialExpressionMax="Max",
                               MaterialExpressionArctangent2="Atan2", MaterialExpressionMultiply="Multiply")
        ctx = SimpleNamespace(expression=lambda mat, kind, x, y: Node(kind),
            connect=lambda a, out, b, pin: b.inputs.update({pin: a}),
            safe_set=lambda node, key, value: node.values.update({key: value}))
        scope = {}
        with patch.dict("sys.modules", unreal=fake, ue_context=ctx):
            exec(compile((ROOT/"tools/legacy/ue_face_sdf_nodes.py").read_text(), "actual-helper", "exec"), scope)
            for forward, left in ((1, 0), (0, 1), (0, -1), (-1, 0), (.3, -.8), (0, 0)):
                self.assertAlmostEqual(evaluate(scope["angular_threshold"](None, forward, left)),
                                       light_threshold(forward, left))

    def test_selected_response_graph_readback_requires_connected_thresholds(self):
        class Node:
            def __init__(self):
                self.inputs, self.values = {}, {}
            def get_editor_property(self, key):
                return self.values.get(key, "")
        class Multiply(Node): pass
        class Add(Node): pass
        class OneMinus(Node): pass
        class Subtract(Node): pass
        class Dot(Node): pass
        class Abs(Node): pass
        class Max(Node): pass
        class Atan2(Node): pass
        nodes = []
        def expression(material, kind, x, y):
            node = kind()
            nodes.append(node)
            return node
        fake = SimpleNamespace(MaterialExpressionMultiply=Multiply, MaterialExpressionAdd=Add,
            MaterialExpressionOneMinus=OneMinus, MaterialExpressionSubtract=Subtract,
            MaterialExpressionDotProduct=Dot, MaterialExpressionAbs=Abs,
            MaterialExpressionMax=Max, MaterialExpressionArctangent2=Atan2,
            MaterialEditingLibrary=SimpleNamespace(get_material_expressions=lambda material: nodes,
                get_inputs_for_material_expression=lambda material, node: list(node.inputs.values())))
        ctx = SimpleNamespace(expression=expression,
            connect=lambda source, out, target, pin: target.inputs.update({pin: source}),
            safe_set=lambda node, key, value: node.values.update({key: value}))
        scope = {}
        with patch.dict("sys.modules", unreal=fake, ue_context=ctx):
            exec(compile((ROOT/"tools/legacy/ue_face_sdf_nodes.py").read_text(), "helper", "exec"), scope)
            def cosine_value(node):
                if isinstance(node, Dot): return 0.3
                if isinstance(node, Multiply): return cosine_value(node.inputs["A"]) * node.values["const_b"]
                if isinstance(node, Add): return cosine_value(node.inputs["A"]) + node.values["const_b"]
                if isinstance(node, OneMinus): return 1 - cosine_value(node.inputs[""])
                raise AssertionError(type(node))
            forward, left = Dot(), Dot()
            for expected in ("linear_azimuth_v1", "cosine_half_art"):
                nodes.clear()
                selected = (scope["angular_threshold"](None, forward, left) if expected == "linear_azimuth_v1"
                            else scope["cosine_half_threshold"](None, forward))
                if expected == "cosine_half_art":
                    self.assertAlmostEqual(cosine_value(selected), (1 - 0.3) / 2)
                uses = []
                for label, cls in (("shadow", Subtract), ("specular", Subtract), ("inverse", OneMinus)):
                    node = expression(None, cls, 0, 0)
                    node.values["desc"] = "Face SDF threshold use: " + label
                    node.inputs["A"] = selected
                    uses.append(node)
                specular_inverse = expression(None, Subtract, 0, 0)
                specular_inverse.values["desc"] = "Face SDF threshold use: specular inverse"
                specular_inverse.inputs["A"] = uses[-1]
                self.assertEqual(scope["response_readback"](object()), expected)
                specular_inverse.inputs["A"] = Dot()
                self.assertIsNone(scope["response_readback"](object()))
                specular_inverse.inputs["A"] = uses[-1]
                uses[1].inputs["A"] = Dot()
                self.assertIsNone(scope["response_readback"](object()))
                uses[1].inputs["A"] = selected
                selected.values["desc"] = "wrong marker"
                self.assertIsNone(scope["response_readback"](object()))

    def test_nonmonotonic_masks_are_measured_not_silently_accepted(self):
        stack = np.array([[[1, 1]], [[0, 1]], [[1, 0]]], dtype=bool)
        report, lost, dark = analyze_monotonicity(stack, np.ones((1, 2), dtype=bool))
        self.assertTrue(report["requires_review"])
        self.assertEqual(report["discarded_lit_fraction_by_frame"], [0, 0, .5])
        self.assertEqual(lost.tolist(), [[True, False]])
        self.assertFalse(dark.any())
        # Relighting outside the chosen face mask must not block its bake.
        report, _, _ = analyze_monotonicity(stack, np.array([[0, 1]], dtype=bool))
        self.assertFalse(report["requires_review"])

    def test_monotonic_masks_pass_and_empty_coverage_fails(self):
        report, _, _ = analyze_monotonicity([[[1, 1]], [[0, 1]], [[0, 0]]], [[1, 1]])
        self.assertFalse(report["requires_review"])
        with self.assertRaises(ValueError):
            analyze_monotonicity([[[1]], [[0]], [[1]]], [[0]])

    def test_baker_emits_linear_phase_and_highlights_are_opt_in(self):
        tree = ast.parse((ROOT/"tools/legacy/blender_face_sdf.py").read_text())
        defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
                {"edt_1d", "distance_to", "signed_distance", "shadow_threshold_from_masks"}]
        scope = {"np": np}
        exec(compile(ast.Module(body=defs, type_ignores=[]), "actual-baker", "exec"), scope)
        # At a symmetric crossing half way between frames 0 and 1 of 3,
        # threshold must be .25 (not the cosine-domain .1464).
        result = scope["shadow_threshold_from_masks"]([np.ones((1, 1), bool),
                                                      np.zeros((1, 1), bool), np.zeros((1, 1), bool)])
        self.assertAlmostEqual(float(result[0, 0]), .25)
        parser = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
        highlight = next(n for n in ast.walk(parser) if isinstance(n, ast.Call) and n.args and
                         isinstance(n.args[0], ast.Constant) and n.args[0].value == "--highlight-mode")
        self.assertEqual(next(k.value.value for k in highlight.keywords if k.arg == "default"), "disabled")
        resolution = next(n for n in ast.walk(parser) if isinstance(n, ast.Call) and n.args and
                          isinstance(n.args[0], ast.Constant) and n.args[0].value == "--resolution")
        self.assertEqual(next(k.value.value for k in resolution.keywords if k.arg == "default"), 1024)
        self.assertTrue(any(isinstance(n, ast.Compare) and isinstance(n.left, ast.Attribute) and
                            n.left.attr == "resolution" and any(isinstance(c, ast.Constant) and c.value == 1024
                                                                for c in n.comparators)
                            for n in ast.walk(parser)))
