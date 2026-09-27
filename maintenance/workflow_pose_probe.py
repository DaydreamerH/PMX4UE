"""Explicit MMD2UE case test of the generic agent contract, not model defaults."""
import json
import os
from pathlib import Path
import sys
import unreal

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
from ue_pose_inventory import export
from retarget_workflow import draft_model, draft_pair, compile_pair
from ue_retarget_pose import build
from ue_pose_reload import check

project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
assert project.name == 'MMD2UE'
out = project / 'Saved/PMX4UE/WorkflowPoseProbe_v1'
out.mkdir(parents=True, exist_ok=True)

def write(name, value):
    with (out/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

if os.environ.get('PMX_POSE_RELOAD') == '1':
    check(out/'build.json', out/'reload.json')
elif os.environ.get('PMX_POSE_EXPORT') == '1':
    from ue_animation_export import build as export_animation
    profile=json.loads((project/'Saved/PMX4UE/WorkflowProbe_v1/animation_profile.json').read_text(encoding='utf-8'))
    profile.update(retargeter='/Game/PMX4UE/WorkflowPoseProbe/v1/RTG_AgentContract',
                   output_directory='/Game/PMX4UE/WorkflowPoseProbe/v1/Animations')
    export_animation(profile, '/Game/PMX4UE/WorkflowPoseProbe/v1', out/'animation_export.json')
else:
    inventory = export('/Game/Characters/TololoSchool1001/Rigs/TPose_v5/RTG_UEFN_To_Tololo_TPose_v5', out/'inventory.json')
    evidence = [str(root/'characters/TololoSchool1001/tpose-v4-decision.md'),
                str(root/'characters/TololoSchool1001/tpose-v3-decision.md'), str(out/'inventory.json')]
    models = {}
    for side in ('source', 'target'):
        model = draft_model(inventory, side, 'UEFN' if side == 'source' else 'Tololo')
        model['basis'] = dict(left=[1,0,0], forward=[0,1,0], up=[0,0,1])
        source = side == 'source'
        model['roles'] = dict(pelvis='pelvis' if source else 'Center',
            spine=['spine_01','spine_05'] if source else ['UpperBody','UpperBody2'],
            arms={s: [f'upperarm_{a}',f'lowerarm_{a}',f'hand_{a}'] if source else [f'Arm_{a.upper()}',f'Elbow_{a.upper()}',f'Wrist_{a.upper()}'] for s,a in [('left','l'),('right','r')]},
            legs={s: [f'thigh_{a}',f'calf_{a}',f'foot_{a}'] if source else [f'LegD_{a.upper()}',f'KneeD_{a.upper()}',f'AnkleD_{a.upper()}'] for s,a in [('left','l'),('right','r')]})
        model['spine_chain'] = 'Spine'
        model['limb_chains'] = dict(arms=dict(left='LeftArm',right='RightArm'), legs=dict(left='LeftLeg',right='RightLeg'))
        model['review'] = dict(by='agent', rationale='Reuse user-accepted v5 semantics; native inventory must agree. No bind or hierarchy edits.', evidence=evidence, unresolved=[])
        model['role_evidence'] = {k:evidence for k in ('pelvis','spine','arms','legs','basis')}
        models[side] = model
        write(side+'.model.json', model)
    pair = draft_pair(inventory)
    pair.update(namespace='/Game/PMX4UE/WorkflowPoseProbe/v1', output_retargeter='/Game/PMX4UE/WorkflowPoseProbe/v1/RTG_AgentContract')
    pair['review'] = dict(by='agent', rationale='Preserve accepted v5 torso and match target stance; test generic contract on actual different skeletons.', evidence=evidence, unresolved=[])
    for side in ('source','target'):
        pair['sides'][side]['pose_name'] = 'AgentContract_'+side.title()+'_v1'
        pair['sides'][side]['posture_checks'] = [dict(start='pelvis' if side=='source' else 'Waist', end='neck_01' if side=='source' else 'Neck', up_axis=[0,0,1], max_tilt_degrees=5 if side=='source' else 2)]
    write('pair.json', pair)
    result = compile_pair(inventory, models, pair)
    write('compiled.json', result)
    build(result['profile'], pair['namespace'], out/'build.json')
