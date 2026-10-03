"""Actual graph-helper/disabled-entry regressions, without Unreal."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'tools/legacy/ue_master_material.py').read_text(encoding='utf-8-sig'))


def function(name, env):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual hair builder>', 'exec'), env)
    return env[name]


class HairBangsTests(unittest.TestCase):
    def make_graph(self):
        self.params = {}

        def vector(material, name, value, x, y):
            node = {'kind': 'parameter', 'value': value[:3], 'inputs': {}}
            self.params[name] = node
            return node

        def expression(material, kind, x, y):
            return {'kind': kind, 'inputs': {}}

        def scalar(material, name, value, x, y):
            node = {'kind': 'parameter', 'value': value, 'inputs': {}}
            self.params[name] = node
            return node

        def connect(source, source_pin, target, target_pin):
            target['inputs'][target_pin] = source

        env = dict(vector=vector, scalar=scalar, expression=expression, connect=connect,
                   unreal=SimpleNamespace(MaterialExpressionNormalize='normalize',
                                          MaterialExpressionDotProduct='dot',
                                          MaterialExpressionLinearInterpolate='lerp'))
        function('head_hair_inputs', env)
        self.view = {'kind': 'parameter', 'value': (0, 0, 1), 'inputs': {}}
        return function('hair_view_vertical', env)(object(), self.view, 0, 0)

    def evaluate(self, node):
        if node['kind'] == 'parameter':
            return node['value']
        if node['kind'] == 'normalize':
            v = self.evaluate(node['inputs']['VectorInput'])
            length = math.sqrt(sum(x*x for x in v))
            return tuple(x / length for x in v)
        if node['kind'] == 'lerp':
            a = self.evaluate(node['inputs']['A'])
            b = self.evaluate(node['inputs']['B'])
            t = self.evaluate(node['inputs']['Alpha'])
            return tuple(x*(1-t)+y*t for x, y in zip(a, b))
        return sum(a*b for a, b in zip(self.evaluate(node['inputs']['A']),
                                       self.evaluate(node['inputs']['B'])))

    def test_static_default_is_ue_up_not_world_y(self):
        graph = self.make_graph()
        self.assertEqual(self.params['HairUpWS']['value'], (0, 0, 1))
        self.assertAlmostEqual(self.evaluate(graph), 1)
        self.view['value'] = (0, 1, 0)
        self.assertAlmostEqual(self.evaluate(graph), 0)

    def test_calibrated_rotated_axis_is_normalized(self):
        graph = self.make_graph()
        self.params['HairUpWS']['value'] = (0, 2, 0)
        self.view['value'] = (0, 1, 0)
        self.assertAlmostEqual(self.evaluate(graph), 1)
        self.view['value'] = (0, -1, 0)
        self.assertAlmostEqual(self.evaluate(graph), -1)

    def test_graph_builders_use_helper_not_camera_y(self):
        for name in ('create_master', '_create_legacy_bang_candidates'):
            node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == 'hair_view_vertical']
            self.assertEqual(len(calls), 1, name)
            self.assertNotIn('camera_y', {n.id for n in ast.walk(node) if isinstance(n, ast.Name)})

    def test_runtime_axis_is_opt_in_and_falls_back_when_invalid(self):
        graph = self.make_graph()
        self.params['HairUpRuntimeWS']['value'] = (0, 4, 0)
        self.view['value'] = (0, 1, 0)
        self.assertEqual(self.evaluate(graph), 0)
        self.params['HairBasisRuntimeValid']['value'] = 1
        self.assertEqual(self.evaluate(graph), 1)
        self.params['HairBasisRuntimeValid']['value'] = 0
        self.assertEqual(self.evaluate(graph), 0)

    def test_old_public_bang_entry_fails_before_any_asset_operations(self):
        class BuildError(RuntimeError):
            pass

        disabled = function('create_bang_passes', {'BuildError': BuildError})
        # No Unreal or graph helper is supplied: any asset operation would fail.
        with self.assertRaisesRegex(BuildError, 'Legacy bang translucency is disabled'):
            disabled(object(), object(), object())


if __name__ == '__main__':
    unittest.main()
