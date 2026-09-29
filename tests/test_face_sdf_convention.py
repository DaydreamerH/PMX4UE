import ast
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
from face_sdf_convention import analyze_monotonicity, light_threshold

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
