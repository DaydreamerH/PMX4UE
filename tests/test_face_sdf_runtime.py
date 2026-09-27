"""Graph-topology regressions with a small material API fake; UE tests remain authoritative."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch


class Node:
    def __init__(self):
        self.props = {}
        self.inputs = {}

    def get_editor_property(self, key):
        return self.props[key]

    def set_editor_property(self, key, value):
        self.props[key] = value


class FaceRuntimeGraphTests(unittest.TestCase):
    def setUp(self):
        self.ue = types.ModuleType("unreal")
        for name in ("VectorParameter", "ScalarParameter", "Transform", "Normalize", "LinearInterpolate"):
            setattr(self.ue, "MaterialExpression"+name, type(name, (Node,), {}))
        self.ue.MaterialVectorCoordTransformSource = types.SimpleNamespace(TRANSFORMSOURCE_LOCAL=0)
        self.ue.MaterialVectorCoordTransform = types.SimpleNamespace(TRANSFORM_WORLD=1)
        self.nodes = []
        def create(material, cls, x, y):
            node = cls()
            self.nodes.append(node)
            return node
        def connect(source, output, target, pin):
            target.inputs[pin] = (source,output)
            return True
        self.ue.MaterialEditingLibrary = types.SimpleNamespace(
            get_material_expressions=lambda m:list(self.nodes),
            get_inputs_for_material_expression=lambda m,n:[i[0] for i in n.inputs.values()],
            create_material_expression=create,connect_material_expressions=connect,
            recompile_material=lambda m:None)
        self.legacy = []
        for name in ("FaceForwardWS","FaceLeftWS"):
            p=create(None,self.ue.MaterialExpressionVectorParameter,0,0)
            p.props.update(parameter_name=name,default_value=(0,1,0))
            t=create(None,self.ue.MaterialExpressionTransform,0,0)
            t.props.update(transform_source_type=0,transform_type=1)
            connect(p,"RGB",t,"")
            n=create(None,self.ue.MaterialExpressionNormalize,0,0)
            connect(t,"",n,"VectorInput")
            self.legacy.append((p,t,n))
        spec=importlib.util.spec_from_file_location("sdf_runtime_under_test",Path(__file__).resolve().parents[1]/"tools/ue_face_sdf_runtime.py")
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules",{"unreal":self.ue}): spec.loader.exec_module(self.module)

    def test_world_branch_bypasses_transform_and_keeps_fallback(self):
        contract=self.module.add_runtime_basis(object())
        self.assertEqual(contract["space"],"world")
        self.assertEqual(sum(isinstance(n,self.ue.MaterialExpressionTransform) for n in self.nodes),2)
        for p,t,n in self.legacy:
            blend=n.inputs["VectorInput"][0]
            self.assertIs(blend.inputs["A"][0],t)
            runtime=blend.inputs["B"][0]
            self.assertIsInstance(runtime,self.ue.MaterialExpressionVectorParameter)
            self.assertEqual(runtime.props["parameter_name"],p.props["parameter_name"].replace("WS","RuntimeWS"))
            self.assertEqual(blend.inputs["Alpha"][0].props["default_value"],0.)

    def test_wrong_space_fails_before_mutation(self):
        self.legacy[1][1].props["transform_source_type"]=99
        before=len(self.nodes)
        with self.assertRaisesRegex(ValueError,"Unsupported basis space"):
            self.module.add_runtime_basis(object())
        self.assertEqual(before,len(self.nodes))

    def test_missing_axis_fails_before_mutation(self):
        self.legacy[1][0].props["parameter_name"]="Unknown"
        before=len(self.nodes)
        with self.assertRaisesRegex(ValueError,"Expected one FaceLeftWS"):
            self.module.add_runtime_basis(object())
        self.assertEqual(before,len(self.nodes))

    def test_duplicate_patch_refused(self):
        self.module.add_runtime_basis(object())
        before=len(self.nodes)
        with self.assertRaisesRegex(ValueError,"already present"):
            self.module.add_runtime_basis(object())
        self.assertEqual(before,len(self.nodes))


if __name__=="__main__": unittest.main()
