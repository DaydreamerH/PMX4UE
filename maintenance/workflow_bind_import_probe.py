"""Import isolated precision-normalized FBX, preserve original model assets."""
import json
import os
from pathlib import Path
import runpy
import unreal
root=Path(__file__).resolve().parents[1]
project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert project.name=='MMD2UE'
out=project/'Saved/PMX4UE/WorkflowBindProbe_v2'
out.mkdir(parents=True,exist_ok=True)
config=json.loads((root/'.local/probe-character.json').read_text(encoding='utf-8'))
config['pmx4ue']['project']=str(project/'MMD2UE.uproject')
config['paths']['ue_root']='/Game/PMX4UE/WorkflowBindProbe/v2'
config['paths']['fbx']=str(project/'Saved/PMX4UE/WorkflowProbe_v1/TololoBindRigid_v2.fbx')
with (out/'config.json').open('x',encoding='utf-8') as f:json.dump(config,f,ensure_ascii=False,indent=2)
os.environ.update(PMX4UE_CONFIG=str(out/'config.json'),PMX4UE_PROBE_OUTPUT=str(out/'inspection.json'))
runpy.run_path(str(root/'maintenance/ue_import_smoke.py'),run_name='__main__')
