import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools.outline_contract import outline_spec, outline_assets, outline_args, verify_outline_receipt, face_regions
from tools.material_preview_contract import validate


class OutlineTests(unittest.TestCase):
    def setUp(self):
        self.spec = dict(material='/Game/General', face_material='/Game/Face', face_slots=[0],
                         hair_material='/Game/Hair', hair_slots=[2], excluded_slots=[1])

    def receipt(self, clear=False):
        return dict(ok=True, saved=False, overlay_material='/Game/General.General',
                    face_overlay_material='/Game/Face.Face', hair_overlay_material='/Game/Hair.Hair',
                    applied_slots=[] if clear else [0, 2, 3], excluded_slots=[0, 1, 2, 3] if clear else [1])

    def test_routing_and_legacy(self):
        self.assertEqual(outline_assets(self.spec), ['/Game/General', '/Game/Face', '/Game/Hair'])
        self.assertEqual(outline_args(self.spec, 4), ('/Game/General', '/Game/Face', '/Game/Hair', '1', '0', '2', 6000., False))
        self.assertEqual(outline_args(self.spec, 4, True)[3], '0,1,2,3')
        self.assertEqual(outline_assets('/Game/General'), ['/Game/General'])

    def test_invalid_routing(self):
        for update in (dict(face_slots=[4]), dict(face_slots=[0, 0]), dict(face_slots=[True]),
                       dict(hair_slots=[0]), dict(excluded_slots=[0]), dict(face_material=''),
                       dict(face_slots=[]), dict(typo=True)):
            with self.subTest(update=update), self.assertRaises(ValueError):
                outline_spec({**self.spec, **update}, 4)

    def test_profile_accepts_specialized_outline(self):
        root = Path(__file__).resolve().parents[1]
        p = json.loads((root/'templates/material_preview.example.json').read_text())
        p['reviewed'] = True
        p['cases'].append(dict(name='Controlled', slots=[], outline=self.spec))
        validate(p, '/Game/PMX4UE/Character/v1')

    def test_actual_preview_method_passes_and_clears_routing(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root/'tools/ue_material_preview.py').read_text(encoding='utf-8-sig'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'outline')
        env = dict(native=lambda r: r, outline_args=outline_args, outline_spec=outline_spec,
                   verify_outline_receipt=verify_outline_receipt)
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<actual preview method>', 'exec'), env)
        for clear in (False, True):
            calls = []
            def attach(*args):
                calls.append(args)
                return self.receipt(clear)
            runtime = SimpleNamespace(materials=[None]*4, actor=SimpleNamespace(get_actor_label=lambda: 'Preview'),
                                      api=SimpleNamespace(set_character_outline_overlay=attach))
            result = env['outline'](runtime, self.spec, clear)
            self.assertEqual(calls[0], ('Preview', *outline_args(self.spec, 4, clear)))
            self.assertEqual(result['requested_routing']['face_slots'], [0])

    def test_wrong_receipt_rejected(self):
        verify_outline_receipt(self.spec, self.receipt(), 4)
        for update in (dict(saved=True), dict(face_overlay_material='None'), dict(excluded_slots=[]),
                       dict(applied_slots=[0, 1, 2, 3])):
            with self.assertRaises(ValueError):
                verify_outline_receipt(self.spec, {**self.receipt(), **update}, 4)

    def test_face_mask_requires_real_calibration_not_defaults(self):
        self.assertEqual(face_regions({}), [])
        self.assertEqual(face_regions({'face_internal': []}), [])
        good = dict(face_internal=[dict(name='Mouth', center=[.5, .7], radius=[.1, .05])],
                    face_internal_reviewed=True, face_internal_evidence='fixture UV audit', face_uv_channel=0)
        self.assertEqual(len(face_regions(good)), 1)
        for change in (dict(face_internal_reviewed=False), dict(face_internal_evidence=''), dict(face_uv_channel=-1)):
            with self.assertRaises(ValueError):
                face_regions({**good, **change})
        for radius in ([0, .1], [-.1, .1], [float('nan'), .1]):
            bad = copy.deepcopy(good)
            bad['face_internal'][0]['radius'] = radius
            with self.assertRaises(ValueError):
                face_regions(bad)


if __name__ == '__main__':
    unittest.main()
