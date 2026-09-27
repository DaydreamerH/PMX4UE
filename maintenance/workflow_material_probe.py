"""Read-only validation of generic compile stage on existing accepted materials."""
import os
from pathlib import Path
import runpy
import sys
import unreal
root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools'))
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert project.name == 'MMD2UE'
from ue_material_compile import compile_parents
mesh = unreal.load_asset('/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1')
paths = sorted({s.material_interface.get_path_name() for s in mesh.get_editor_property('materials') if s.material_interface})
compile_parents(paths, project/'Saved/PMX4UE/WorkflowProbe_v1/material_compile_v2.json')
