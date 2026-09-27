"""MMD2UE-only rest-without-animation regression using reviewed case inputs."""
import json
import os
from pathlib import Path
import runpy
import sys
import unreal
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'tools'),str(root/'tools/legacy')]
from pmx_physics_plan import make_plan
project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert project.name == 'MMD2UE'
out=project/'Saved/PMX4UE/WorkflowRestProbe_v1'
out.mkdir(parents=True,exist_ok=True)
stage=os.environ.get('PMX_REST_STAGE','build')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
if stage=='build':
    old=project/'Saved/PMX4UE/WorkflowProbe_v1'
    profile=read(old/'physics_profile_reviewed.json')
    profile.update(rest_only=True,test_animation='',asset_root='/Game/PMX4UE/WorkflowRestProbe/v1/Physics')
    profile['performance_test']['enabled']=False
    plan=make_plan(read(project/'Saved/PmxPhysicsWorkflow/Tololo/inventory.json'),profile,read(old/'physics_inspect.json'))
    with (out/'plan.json').open('x',encoding='utf-8') as f:json.dump(plan,f,ensure_ascii=False,indent=2)
os.environ.update(PMX_PHYSICS_STAGE=stage,PMX_PHYSICS_OUTPUT=str(out/(stage+'.json')),PMX_PHYSICS_PLAN=str(out/'plan.json'))
runpy.run_path(str(root/'tools/legacy/ue_pmx_physics_workflow.py'),run_name='__main__')
