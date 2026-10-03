"""Versioned hair graph copies, preserving source assets and instance inheritance."""
import hashlib
import json
import os
from pathlib import Path
import unreal
from head_hair_profile import validate_profile
from ue_head_hair_runtime import add_head_hair_runtime
from ue_hair_reference_nodes import add_head_band


def run():
    config = json.loads(Path(os.environ['PMX4UE_CONFIG']).read_text(encoding='utf-8-sig'))
    profile = validate_profile(json.loads(Path(os.environ['PMX4UE_HEAD_HAIR_PROFILE']).read_text(
        encoding='utf-8-sig')), config['paths']['ue_root'])
    project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
    if project != Path(config['pmx4ue']['project']).resolve().parent:
        raise RuntimeError('Wrong project')
    output = Path(os.environ['PMX4UE_OUTPUT'])
    if output.exists():
        raise RuntimeError('Report already exists; choose a new version')
    assets, lib = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    dest = profile['destination']
    if assets.does_directory_exist(dest) or assets.does_asset_exist(dest):
        raise RuntimeError('Destination occupied; preserve it and choose a new version')
    prefix = 'MMD2UE' if profile['provider'] == 'mmd2ue' else 'PMX4UE'
    tools = getattr(unreal, prefix + 'AgentMCPTools', None)
    driver_class = getattr(unreal, 'MMDFaceSDFComponent' if profile['provider'] == 'mmd2ue'
                           else 'PMX4UEFaceSDFComponent', None)
    if tools is None or driver_class is None:
        raise RuntimeError('Compile/reload the selected runtime provider first')
    driver = unreal.new_object(driver_class)
    driver.get_editor_property('hair_sphere_center_reference_cs')
    mesh = unreal.load_asset(profile['mesh'])
    if not isinstance(mesh, unreal.SkeletalMesh):
        raise ValueError('mesh is not a SkeletalMesh')
    probe = unreal.new_object(unreal.SkeletalMeshComponent)
    probe.set_skeletal_mesh_asset(mesh)
    if probe.get_bone_index(profile['head_bone']) < 0:
        raise ValueError('Reviewed head bone is missing')
    selected = []
    for name in profile['hair_slots']:
        rows = [(i, m.material_interface) for i, m in enumerate(mesh.get_editor_property('materials'))
                if str(m.material_slot_name) == name]
        if len(rows) != 1 or not isinstance(rows[0][1], unreal.MaterialInstanceConstant):
            raise ValueError('Expected one constant material instance for hair slot: ' + name)
        selected.append((rows[0][0], name, rows[0][1]))
    sources, chains = {mesh.get_path_name(): mesh}, {}
    for _, _, leaf in selected:
        chain, parent = [], leaf
        while isinstance(parent, unreal.MaterialInstanceConstant):
            if parent in chain:
                raise ValueError('Cyclic material parent chain')
            chain.append(parent)
            sources[parent.get_path_name()] = parent
            parent = parent.get_editor_property('parent')
        if not isinstance(parent, unreal.Material):
            raise ValueError('Unsupported parent chain; adapt explicitly')
        sources[parent.get_path_name()] = parent
        chains[leaf.get_path_name()] = (chain, parent)

    def digest(obj):
        package = obj.get_path_name().split('.')[0]
        if not package.startswith('/Game/'):
            raise ValueError('Require saved /Game inputs')
        return hashlib.sha256((project / 'Content' / (package[6:] + '.uasset')).read_bytes()).hexdigest()

    if profile.get('highlight_mode') == 'head_band':
        mask = unreal.load_asset(profile['band']['mask'])
        if not isinstance(mask, unreal.Texture) or mask.get_editor_property('srgb') or (
                mask.get_editor_property('compression_settings') != unreal.TextureCompressionSettings.TC_MASKS):
            raise ValueError('Band needs a reviewed linear texture')
        sources[mask.get_path_name()] = mask
    hashes = {key: digest(obj) for key, obj in sources.items()}
    report = dict(status='building', profile=profile, input_hashes=hashes,
                  created=[], compile=[], contracts=[], component_overrides=[],
                  runtime_accepted=False, visual_accepted=False)
    copies = {}

    def duplicate(original):
        key = original.get_path_name()
        if key in copies:
            return copies[key]
        name = ('M' if isinstance(original, unreal.Material) else 'MI') + '_HeadHair_' + str(len(copies))
        obj = assets.duplicate_asset(key, dest + '/' + name)
        if obj is None:
            raise RuntimeError('Cannot duplicate ' + key)
        copies[key] = obj
        report['created'].append(obj.get_path_name())
        return obj

    def save(obj):
        if not assets.save_loaded_asset(obj):
            raise RuntimeError('Cannot save ' + obj.get_path_name())

    try:
        for index, name, leaf in selected:
            chain, master = chains[leaf.get_path_name()]
            new_master = duplicate(master)
            if not any(c.get('master') == new_master.get_path_name() for c in report['contracts']):
                params = {str(n.get_editor_property('parameter_name')) for n in lib.get_material_expressions(new_master)
                          if isinstance(n, unreal.MaterialExpressionScalarParameter)}
                if 'HairBasisRuntimeValid' in params:
                    # Fresh builders already contain the contract; require the complete vector pair.
                    vectors = {str(n.get_editor_property('parameter_name')) for n in lib.get_material_expressions(new_master)
                               if isinstance(n, unreal.MaterialExpressionVectorParameter)}
                    if not {'HeadSphereCenterWS', 'HairUpRuntimeWS'} <= vectors:
                        raise ValueError('Incomplete head hair runtime graph')
                    contract = dict(existing=True, runtime_accepted=False)
                else:
                    contract = add_head_hair_runtime(new_master)
                contract['master'] = new_master.get_path_name()
                if profile.get('highlight_mode') == 'head_band':
                    contract['highlight'] = add_head_band(new_master, profile['band'])
                report['contracts'].append(contract)
                compiled = json.loads(tools.inspect_material_compile(new_master.get_path_name()))
                report['compile'].append(compiled)
                if not compiled.get('ok'):
                    raise RuntimeError('Shader compile failed; see report')
                save(new_master)
            parent = new_master
            for original in reversed(chain):
                obj = duplicate(original)
                lib.set_material_instance_parent(obj, parent)
                save(obj)
                parent = obj
            report['component_overrides'].append(dict(index=index, slot=name, material=parent.get_path_name()))
        report.update(status='built_needs_runtime_visual_review',
                      pending=['apply ue_head_hair_binding to actual character',
                               'animated head and owner turn', 'missing bone and recovery',
                               'daylight visual A/B and complete highlight gates', 'LOD and game cost'])
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        report['input_assets_unchanged'] = all(digest(obj) == hashes[key] for key, obj in sources.items())
        if not report['input_assets_unchanged']:
            report.update(status='failed', error='Protected source fingerprint changed')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    if not report['input_assets_unchanged']:
        raise RuntimeError('Protected source fingerprint changed')


if __name__ == '__main__':
    run()
