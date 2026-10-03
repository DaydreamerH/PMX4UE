"""Portable reference transfer: math, explicit inputs, topology and workflow routing."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from hair_reference_algorithms import (
    band_envelope, eye_aperture, eye_composite, interpolate_field, validate_band, source_coverage,
    BAND_INPUTS, PEEK_INPUTS, FRINGE_INPUTS,
)
from fringe_distance_fields import signed_field
from head_hair_profile import validate_profile


def band_config():
    return dict(reviewed=True,review_evidence='actual UV0 strand coverage and fit',
                mask='/Game/Example/Strands',uv_channel=0,height_cm=0,width_cm=2,
                view_shift_cm=3,spec_normal_blend=.5)


class MathTests(unittest.TestCase):
    def test_band_moves_with_head_up_view_not_world_y(self):
        self.assertEqual(band_envelope(-3,1,0,2,3),1)
        self.assertEqual(band_envelope(3,-1,0,2,3),1)
        self.assertLess(band_envelope(0,1,0,2,3),.02)

    def test_distances_are_blended_before_threshold(self):
        self.assertAlmostEqual(interpolate_field([0,.4,.8,1,1],-22.5),.6)
        self.assertEqual(interpolate_field([0,.4,.8,1,1],-100),0)
        self.assertEqual(interpolate_field([0,.4,.8,1,1],100),1)
        with self.assertRaises(ValueError): interpolate_field([0,1],0)

    def test_shared_uv_eyes_are_not_min_or_union(self):
        self.assertEqual(eye_aperture([1,0],1),1)
        self.assertEqual(eye_aperture([1,0],-1),0)
        self.assertEqual(eye_aperture([1,0],-1,False),1)

    def test_hidden_white_is_not_blended_twice(self):
        self.assertEqual(eye_composite(.2,1,.8,.5,True),.5)
        self.assertNotEqual(eye_composite(.2,1,.8,.5,False),.5)

    def test_masked_source_edges_remain_binary(self):
        self.assertEqual(source_coverage(.05, 2, .12, True), 0)
        self.assertEqual(source_coverage(.06, 2, .12, True), 1)
        self.assertEqual(source_coverage(.5, 1, .12, True), 1)

    def test_continuous_source_alpha_is_not_forced_to_masked(self):
        self.assertEqual(source_coverage(.05, 2, .12, False), .1)
        self.assertEqual(source_coverage(.8, 2, .12, False), 1)
        self.assertEqual(source_coverage(-.1, 1, .12, False), 0)

    def test_invalid_source_coverage_is_not_guessed(self):
        for args in ((.5,1,.12,None), (.5,-1,.12,True), (.5,1,2,True),
                     (.5,1,float('nan'),True), (True,1,.12,True)):
            with self.assertRaises(ValueError): source_coverage(*args)

    def test_distance_sign_empty_full_and_symmetry(self):
        self.assertEqual(signed_field([[0,0],[0,0]]),[[0,0],[0,0]])
        self.assertEqual(signed_field([[1,1],[1,1]]),[[1,1],[1,1]])
        f=signed_field([[0,0,0],[0,1,0],[0,0,0]])
        self.assertGreater(f[1][1],.5)
        self.assertLess(f[0][1],.5)
        self.assertEqual(f[0][0],f[2][2])

    def test_bad_distance_mask_or_radius_rejected(self):
        for mask,radius in (([],16),([[0],[0,1]],16),([[1]],0),([[1]],float('nan')),([[float('nan')]],16)):
            with self.assertRaises(ValueError): signed_field(mask,radius)

    def test_band_fit_is_opt_in_not_unreviewed_default(self):
        self.assertEqual(validate_band(band_config())['uv_channel'],0)
        for key,value in (('reviewed',False),('width_cm',0),('mask','white'),
                          ('uv_channel',True),('spec_normal_blend',2),('height_cm',float('inf'))):
            config=band_config(); config[key]=value
            with self.assertRaises(ValueError): validate_band(config)
        profile=dict(version=1,reviewed=True,review_evidence='actual head fit',
            mesh='/Game/Example/Mesh',destination='/Game/Example/v1/Hair',provider='pmx4ue',
            head_bone='Head',hair_slots=['Bangs'],reference_up=[0,0,1],sphere_center_reference_cs=[0,0,1],
            highlight_mode='head_band',band=band_config())
        self.assertEqual(validate_profile(profile,'/Game/Example/v1')['band'],band_config())


class Node:
    def __init__(self): self.props,self.inputs={},{}
    def get_editor_property(self,key): return self.props[key]
    def set_editor_property(self,key,value): self.props[key]=value


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.ue=types.ModuleType('unreal'); self.nodes=[]
        for name in ('ScalarParameter','VectorParameter','Multiply','SkyAtmosphereLightDirection',
                     'WorldPosition','PixelNormalWS','CameraVectorWS','TextureCoordinate',
                     'TextureSampleParameter2D','Custom','LinearInterpolate'):
            setattr(self.ue,'MaterialExpression'+name,type(name,(Node,),{}))
        self.ue.Texture=type('Texture',(Node,),{})
        self.ue.CustomInput=Node
        self.ue.CustomMaterialOutputType=types.SimpleNamespace(CMOT_FLOAT1='float',CMOT_FLOAT3='rgb')
        self.ue.MaterialSamplerType=types.SimpleNamespace(SAMPLERTYPE_MASKS='mask')
        self.ue.TextureCompressionSettings=types.SimpleNamespace(TC_MASKS='masks')
        self.texture=self.ue.Texture(); self.texture.props['srgb']=False
        self.texture.props['compression_settings']='masks'
        self.ue.load_asset=lambda p:self.texture
        def create(m,cls,x,y):
            n=cls();self.nodes.append(n);return n
        def connect(a,pin,b,key): b.inputs[key]=(a,pin);return True
        self.ue.MaterialEditingLibrary=types.SimpleNamespace(
            get_material_expressions=lambda m:list(self.nodes),
            get_inputs_for_material_expression=lambda m,n:[v[0] for v in n.inputs.values()],
            create_material_expression=create,connect_material_expressions=connect,recompile_material=lambda m:None)
        def node(kind,**props):
            n=create(None,getattr(self.ue,'MaterialExpression'+kind),0,0); n.props.update(props);return n
        for name in ('HairSpecPower','HairSpecMinIntensity','HairBasisRuntimeValid'):
            node('ScalarParameter',parameter_name=name)
        for name in ('HeadSphereCenterWS','HairUpRuntimeWS'):
            node('VectorParameter',parameter_name=name)
        node('SkyAtmosphereLightDirection',light_index=0)
        for name in ('WorldPosition','PixelNormalWS','CameraVectorWS'): node(name)
        self.gate=node('Multiply');self.old=node('Multiply')
        connect(self.old,'',self.gate,'A')
        connect(node('ScalarParameter',parameter_name='HairHighlightStrength'),'',self.gate,'B')
        spec=importlib.util.spec_from_file_location('reference_nodes_test',ROOT/'tools/ue_hair_reference_nodes.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'unreal':self.ue}): spec.loader.exec_module(self.module)

    def test_band_preserves_fallback_and_downstream_gates(self):
        result=self.module.add_head_band(object(),band_config())
        self.assertTrue(result['downstream_gates_preserved'])
        choice=self.gate.inputs['A'][0]
        self.assertIs(choice.inputs['A'][0],self.old)
        self.assertEqual(choice.inputs['Alpha'][0].props['parameter_name'],'HairBasisRuntimeValid')
        code=choice.inputs['B'][0]
        self.assertEqual(set(code.inputs),set(BAND_INPUTS))
        self.assertEqual(code.inputs['Mask'][0].inputs['UVs'][0].props['coordinate_index'],0)

    def test_srgb_mask_fails_before_any_mutation(self):
        self.texture.props['srgb']=True; count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'linear'): self.module.add_head_band(object(),band_config())
        self.assertEqual(len(self.nodes),count)

    def test_normal_map_is_not_reinterpreted_as_mask(self):
        self.texture.props['compression_settings']='normal'; count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'linear'): self.module.add_head_band(object(),band_config())
        self.assertEqual(len(self.nodes),count)

    def test_wrong_gate_order_fails_before_any_mutation(self):
        self.gate.inputs['A'],self.gate.inputs['B']=self.gate.inputs['B'],self.gate.inputs['A']
        count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'order'): self.module.add_head_band(object(),band_config())
        self.assertEqual(len(self.nodes),count)

    def test_all_pass_inputs_explicit_and_no_guessed_stencil(self):
        for recipe,names in (('fringe_distance',FRINGE_INPUTS),('eye_peek',PEEK_INPUTS)):
            count=len(self.nodes)
            with self.assertRaises(ValueError): self.module.custom_node(object(),recipe,{})
            self.assertEqual(len(self.nodes),count)
            result=self.module.custom_node(object(),recipe,{n:(Node(),'') for n in names})
            self.assertEqual(set(result.inputs),set(names))
        self.assertIn('StencilID',result.props['code'])
        self.assertNotIn('140',result.props['code'])

    def test_eye_recipe_requires_actual_source_coverage_inputs(self):
        bindings = {n:(Node(),'') for n in PEEK_INPUTS}
        for missing in ('AlphaScale', 'SourceClip', 'CoverageMode'):
            count = len(self.nodes)
            with self.assertRaises(ValueError):
                self.module.custom_node(object(), 'eye_peek',
                                        {k:v for k,v in bindings.items() if k != missing})
            self.assertEqual(len(self.nodes), count)
        result = self.module.custom_node(object(), 'eye_peek', bindings)
        self.assertIn('step(SourceClip,sourceAlpha)', result.props['code'])
        self.assertIn('saturate(sourceAlpha)', result.props['code'])

    def test_double_band_patch_refused(self):
        self.module.add_head_band(object(),band_config()); count=len(self.nodes)
        with self.assertRaisesRegex(ValueError,'already'): self.module.add_head_band(object(),band_config())
        self.assertEqual(len(self.nodes),count)


class ConverterTests(unittest.TestCase):
    def test_png_cli_preserves_data_alpha_receiver_and_inputs(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Optional PNG CLI requires Pillow')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); a=root/'a.png'; b=root/'b.png'
            first=Image.new('RGBA',(3,3),(0,0,0,0))
            first.putpixel((1,1),(255,255,255,255)); first.save(a)
            second=Image.new('RGBA',(3,3),(0,0,0,255)); second.save(b)
            hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b)]
            cmd=[sys.executable,str(ROOT/'tools/fringe_distance_fields.py'),
                 '--angles-a',str(a),'--angles-b',str(b),'--output',str(root/'result')]
            completed=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            report=json.loads((root/'result/fringe_distance.json').read_text())
            self.assertTrue(report['source_unchanged'])
            self.assertEqual(report['status'],'generated_visual_pending')
            self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b)])
            im=Image.open(root/'result/fringe_distance_A.png')
            self.assertGreater(im.getpixel((1,1))[3],127)  # A.alpha is +45 DATA.
            coverage=Image.open(root/'result/fringe_distance_B.png')
            self.assertEqual(coverage.getpixel((0,0))[3],255)
            retry=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(retry.returncode,0)  # Never overwrite a previous version.


if __name__=='__main__': unittest.main()
