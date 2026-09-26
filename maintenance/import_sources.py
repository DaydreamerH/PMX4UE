"""One-time, explicit copy of reviewed tools. Never modifies the source tree.

Not a runtime dependency. Run only into a fresh PMX4UE checkout before adapting.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

FILES = '''mmd2ue_core.py mmd2ue.py blender_fbx_units.py blender_skeleton_audit.py blender_audit_fbx_bind_pose.py
skeleton_review.py skeleton_plan.py skeleton_ue_mapping.py blender_apply_skeleton_plan.py
blender_face_sdf.py ue_context.py ue_build_character.py ue_master_material.py
ue_material_instances.py ue_preview.py ue_apply_features.py ue_feature_outline.py
ue_feature_depth_rim.py ue_feature_cloth.py ue_feature_stocking.py ue_validate.py
blender_pmx_physics_inventory.py pmx_physics_plan.py pmx_physics_settings.py
ue_pmx_physics_workflow.py ue_pmx_pie_performance.py'''.split()
TESTS = '''test_mmd2ue_core.py test_skeleton_plan.py test_skeleton_review.py
test_skeleton_ue_mapping.py test_pmx_physics_plan.py test_pmx_physics_settings.py'''.split()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.source.resolve()
    pairs = [(f'Tools/MMDPipeline/framework/{f}', f'tools/legacy/{f}') for f in FILES]
    pairs += [(f'Tools/MMDPipeline/framework/tests/{f}', f'tests/inherited/{f}') for f in TESTS]
    pairs += [('Tools/MMDPipeline/blender_prepare.py', 'tools/blender_prepare.py'),
              ('Tools/MMDPipeline/blender_face_sdf_probe.py', 'tools/blender_face_sdf_probe.py'),
              ('Tools/MMDPipeline/framework/profiles/material_profile_presets.v1.json',
               'presets/materials.v1.json')]
    for module, names in {'MMD2UE': ['Public/AnimNode_PmxFilteredRigidBody.h', 'Private/AnimNode_PmxFilteredRigidBody.cpp'],
                          'MMD2UEEditor': ['Public/AnimGraphNode_PmxFilteredRigidBody.h',
                              'Public/MMD2UEPmxSkirtTools.h', 'Private/MMD2UEPmxSkirtTools.cpp',
                              'Public/MMD2UEAgentMCPTools.h', 'Private/MMD2UEAgentMCPTools.cpp']}.items():
        for name in names:
            pairs.append((f'Source/{module}/{name}',
                          f'unreal/PMX4UE/Source/{module.replace("MMD2UE", "PMX4UE")}/{name.replace("MMD2UE", "PMX4UE")}'))
    if any((root / dst).exists() for _, dst in pairs):
        raise SystemExit('Refusing to overwrite copied/adapted tools')
    records = []
    for src, dst in pairs:
        original = (source / src).read_bytes()
        content = original.decode('utf-8-sig').replace('\r\n', '\n')
        if dst.startswith('unreal/'):
            content = content.replace('MMD2UE', 'PMX4UE')
            # Python-exposed functions do not require the optional MCP plugin.
            content = content.replace('"ModelContextProtocolEditorToolLibrary.h"', '"Kismet/BlueprintFunctionLibrary.h"')
            content = content.replace('UModelContextProtocolEditorToolLibrary', 'UBlueprintFunctionLibrary')
        else:
            content = content.replace('unreal.MMD2UE', 'unreal.PMX4UE')
        target = root / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        records.append({'source': src, 'destination': dst,
                        'source_sha256': hashlib.sha256(original).hexdigest()})
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    (root / 'PROVENANCE.json').write_text(json.dumps({'source_commit': commit,
        'note': 'Copied from working tree; source hashes identify exact bytes, including pre-existing changes. Subsequent adaptations tracked in PMX4UE Git.',
        'files': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Copied {len(records)} files into {root}')

if __name__ == '__main__':
    main()
