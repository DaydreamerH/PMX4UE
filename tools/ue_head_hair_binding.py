"""Install a reviewed report onto one existing character; no asset or level saves."""
import unreal


def apply_binding(report, component, driver):
    if report.get('status') != 'built_needs_runtime_visual_review':
        raise ValueError('Require a successfully built head-hair report')
    if not isinstance(component, unreal.SkeletalMeshComponent):
        raise ValueError('Require the actual character SkeletalMeshComponent')
    profile = report['profile']
    mesh = component.get_editor_property('skeletal_mesh_asset')
    if mesh is None or mesh.get_path_name().split('.')[0] != profile['mesh']:
        raise ValueError('Report and character mesh differ; review calibration again')
    if component.get_bone_index(profile['head_bone']) < 0:
        raise ValueError('Reviewed head bone is missing')
    # Check driver capability and every slot BEFORE changing anything.
    for key in ('drive_hair', 'hair_material_slots', 'reference_hair_up', 'hair_sphere_center_reference_cs'):
        driver.get_editor_property(key)
    slots = list(mesh.get_editor_property('materials'))
    overrides = []
    for entry in report['component_overrides']:
        index = entry['index']
        if index < 0 or index >= len(slots) or str(slots[index].material_slot_name) != entry['slot']:
            raise ValueError('Material slot layout changed')
        material = unreal.load_asset(entry['material'])
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Missing built hair material')
        overrides.append((index, material))
    # Release owned MIDs first, then establish one shared face/hair driver.
    driver.set_editor_property('source_mesh', None)
    driver.update_face_parameters()
    for index, material in overrides:
        component.set_material(index, material)
    driver.set_editor_property('source_mesh', component)
    driver.set_editor_property('head_bone', profile['head_bone'])
    driver.set_editor_property('hair_material_slots', [index for index, _ in overrides])
    driver.set_editor_property('reference_hair_up', unreal.Vector(*profile['reference_up']))
    driver.set_editor_property('hair_sphere_center_reference_cs', unreal.Vector(*profile['sphere_center_reference_cs']))
    driver.set_editor_property('drive_hair', True)
    driver.update_face_parameters()
