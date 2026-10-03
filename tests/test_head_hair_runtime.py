"""Topology/profile regressions; engine/runtime/visual checks remain separate."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from head_hair_profile import validate_profile


class Node:
    def __init__(self):
        self.props, self.inputs = {}, {}
    def get_editor_property(self, key):
        return self.props[key]
    def set_editor_property(self, key, value):
        self.props[key] = value


class HeadHairGraphTests(unittest.TestCase):
    def setUp(self):
        self.ue = types.ModuleType('unreal')
        for name in ('VectorParameter', 'ScalarParameter', 'Add', 'Subtract', 'ObjectPositionWS',
                     'WorldPosition', 'Multiply', 'CameraVectorWS', 'ComponentMask', 'Normalize',
                     'DotProduct', 'LinearInterpolate'):
            setattr(self.ue, 'MaterialExpression'+name, type(name, (Node,), {}))
        self.ue.LinearColor = lambda *v: v
        self.nodes = []
        def create(m, cls, x, y):
            node = cls()
            self.nodes.append(node)
            return node
        def connect(a, output, b, pin):
            b.inputs[pin] = (a, output)
            return True
        self.ue.MaterialEditingLibrary = types.SimpleNamespace(
            get_material_expressions=lambda m:list(self.nodes),
            get_inputs_for_material_expression=lambda m,n:[v[0] for v in n.inputs.values()],
            create_material_expression=create, connect_material_expressions=connect,
            recompile_material=lambda m:None)
        def node(kind, **props):
            n = create(None, getattr(self.ue,'MaterialExpression'+kind),0,0)
            n.props.update(props)
            return n
        offset = node('VectorParameter',parameter_name='NormalSphereOffset')
        self.center = node('Add')
        connect(node('ObjectPositionWS'),'',self.center,'A')
        connect(offset,'RGB',self.center,'B')
        self.sub = node('Subtract')
        connect(node('WorldPosition'),'',self.sub,'A')
        connect(self.center,'',self.sub,'B')
        self.mask = node('ComponentMask',g=True,r=False,b=False,a=False)
        connect(node('CameraVectorWS'),'',self.mask,'Input')
        self.mul = node('Multiply')
        connect(self.mask,'',self.mul,'A')
        connect(node('ScalarParameter',parameter_name='HairSpecOffsetSpeed'),'',self.mul,'B')
        spec=importlib.util.spec_from_file_location('hair_runtime_under_test',ROOT/'tools/ue_head_hair_runtime.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'unreal':self.ue}): spec.loader.exec_module(self.module)

    def test_patch_keeps_old_graph_and_world_runtime_branch(self):
        report = self.module.add_head_hair_runtime(object())
        self.assertTrue(report['uv_texture_spec_gate_unchanged'])
        for endpoint, pin, old in ((self.sub,'B',self.center),(self.mul,'A',self.mask)):
            blend=endpoint.inputs[pin][0]
            self.assertIs(blend.inputs['A'][0],old)
            self.assertEqual(blend.inputs['Alpha'][0].props['default_value'],0.)
        self.assertEqual(self.sub.inputs['B'][0].inputs['B'][0].props['parameter_name'],'HeadSphereCenterWS')

    def test_unsupported_axis_fails_before_mutation(self):
        self.mask.props['r']=True
        count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'world-Y'):
            self.module.add_head_hair_runtime(object())
        self.assertEqual(len(self.nodes),count)

    def test_wrong_subtraction_fails_before_mutation(self):
        self.sub.inputs['A'],self.sub.inputs['B']=self.sub.inputs['B'],self.sub.inputs['A']
        count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'subtraction order'):
            self.module.add_head_hair_runtime(object())
        self.assertEqual(len(self.nodes),count)

    def test_double_patch_refused(self):
        self.module.add_head_hair_runtime(object())
        count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'already present'):
            self.module.add_head_hair_runtime(object())
        self.assertEqual(len(self.nodes),count)


class HeadHairProfileTests(unittest.TestCase):
    def profile(self):
        return dict(version=1, reviewed=True,review_evidence='bind-space fit reviewed',
                    mesh='/Game/Input/SK_Example',destination='/Game/PMX4UE/Example/v1/Hair',
                    provider='pmx4ue',head_bone='ActualHead',hair_slots=['Bangs','Hair'],
                    reference_up=[0,0,4],sphere_center_reference_cs=[0,1,100])
    def test_normalized_up_and_center_untouched(self):
        result=validate_profile(self.profile(),'/Game/PMX4UE/Example/v1')
        self.assertEqual(result['reference_up'],[0,0,1])
        self.assertEqual(result['sphere_center_reference_cs'],[0,1,100])
    def test_incomplete_or_unsafe_profile_rejected(self):
        for key,value in (('reviewed',False),('review_evidence',''),('hair_slots',['Hair','Hair']),
                          ('reference_up',[0,0,0]),('sphere_center_reference_cs',[0,float('nan'),1]),
                          ('destination','/Game/Production/Hair'),('head_bone','None')):
            with self.subTest(key=key):
                profile=self.profile(); profile[key]=value
                with self.assertRaises(ValueError): validate_profile(profile,'/Game/PMX4UE/Example/v1')


if __name__=='__main__': unittest.main()
