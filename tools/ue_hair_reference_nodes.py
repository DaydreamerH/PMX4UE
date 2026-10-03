"""Explicit custom-node adapters; callers own copies, passes, compilation and saves."""
import unreal
from hair_reference_algorithms import (
    BAND_INPUTS, BAND_HLSL, FRINGE_INPUTS, FRINGE_HLSL, PEEK_INPUTS, PEEK_HLSL,
    validate_band,
)

LIB = unreal.MaterialEditingLibrary


def custom_node(material, recipe, bindings):
    recipes = {'head_band': (BAND_INPUTS, BAND_HLSL, True),
               'fringe_distance': (FRINGE_INPUTS, FRINGE_HLSL, False),
               'eye_peek': (PEEK_INPUTS, PEEK_HLSL, False)}
    if recipe not in recipes:
        raise ValueError('Unknown hair recipe')
    names, code, rgb = recipes[recipe]
    if set(bindings) != set(names) or any(not isinstance(v, tuple) or len(v) != 2 or v[0] is None
                                        for v in bindings.values()):
        raise ValueError('Supply every named recipe input explicitly; no guessed defaults')
    node = LIB.create_material_expression(material, unreal.MaterialExpressionCustom, -4500, 4200)
    if node is None:
        raise RuntimeError('Cannot create hair custom node')
    entries = []
    for name in names:
        entry = unreal.CustomInput()
        entry.set_editor_property('input_name', name)
        entries.append(entry)
    node.set_editor_property('inputs', entries)
    node.set_editor_property('code', code)
    node.set_editor_property('output_type', getattr(unreal.CustomMaterialOutputType,
        'CMOT_FLOAT3' if rgb else 'CMOT_FLOAT1'))
    for name, (source, pin) in bindings.items():
        if not LIB.connect_material_expressions(source, pin, node, name):
            raise RuntimeError('Cannot connect recipe input: ' + name)
    return node


def add_head_band(material, config):
    """Patch a DUPLICATED legacy master by topology, not editor coordinates.

    Retains UV highlight when runtime basis is invalid, and ALL downstream gates.
    Source assets, UVs, diffuse shading, opacity and instance values are untouched.
    """
    config = validate_band(config)
    nodes = list(LIB.get_material_expressions(material))
    inputs = lambda n: list(LIB.get_inputs_for_material_expression(material, n))

    def one(rows, label):
        if len(rows) != 1:
            raise ValueError('Expected one ' + label + '; inspect actual graph')
        return rows[0]

    def param(cls, name):
        return one([n for n in nodes if isinstance(n, cls) and
                    str(n.get_editor_property('parameter_name')) == name], name)

    if any(isinstance(n, unreal.MaterialExpressionScalarParameter) and
           str(n.get_editor_property('parameter_name')) == 'HairBandWidthCm' for n in nodes):
        raise ValueError('Head band already present')
    power = param(unreal.MaterialExpressionScalarParameter, 'HairSpecPower')
    minimum = param(unreal.MaterialExpressionScalarParameter, 'HairSpecMinIntensity')
    valid = param(unreal.MaterialExpressionScalarParameter, 'HairBasisRuntimeValid')
    center = param(unreal.MaterialExpressionVectorParameter, 'HeadSphereCenterWS')
    up = param(unreal.MaterialExpressionVectorParameter, 'HairUpRuntimeWS')
    strength = param(unreal.MaterialExpressionScalarParameter, 'HairHighlightStrength')
    destination = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionMultiply)
                       and strength in inputs(n)], 'hair highlight strength gate')
    terms = inputs(destination)
    if len(terms) != 2 or terms[1] != strength:
        raise ValueError('Unexpected strength gate input order')
    old = terms[0]
    light = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionSkyAtmosphereLightDirection)
                 and n.get_editor_property('light_index') == 0], 'actual main-light node')
    world = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionWorldPosition)], 'world position')
    normal = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionPixelNormalWS)], 'pixel normal')
    view = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionCameraVectorWS)], 'view vector')
    mask_texture = unreal.load_asset(config['mask'])
    if not isinstance(mask_texture, unreal.Texture) or mask_texture.get_editor_property('srgb') or (
            mask_texture.get_editor_property('compression_settings') != unreal.TextureCompressionSettings.TC_MASKS):
        raise ValueError('Require a reviewed linear mask texture; do not reinterpret a matcap')
    # All graph/resource checks precede mutation. Nothing is saved by this helper.
    def create(cls):
        n = LIB.create_material_expression(material, cls, -4700, 4400)
        if n is None:
            raise RuntimeError('Cannot create band expression')
        return n

    def connect(a, pin, b, name):
        if not LIB.connect_material_expressions(a, pin, b, name):
            raise RuntimeError('Cannot connect band input: ' + name)

    uv = create(unreal.MaterialExpressionTextureCoordinate)
    uv.set_editor_property('coordinate_index', config['uv_channel'])
    mask = create(unreal.MaterialExpressionTextureSampleParameter2D)
    mask.set_editor_property('parameter_name', 'HairBandMaskTexture')
    mask.set_editor_property('texture', mask_texture)
    mask.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    connect(uv, '', mask, 'UVs')
    bindings = dict(P=(world,''), N=(normal,''), V=(view,''), L=(light,''),
                    Center=(center,'RGB'), Up=(up,'RGB'), Mask=(mask,'RGB'),
                    Power=(power,''), MinIntensity=(minimum,''))
    for key, name, value in (
        ('Height','HairBandHeightCm',config['height_cm']),
        ('Width','HairBandWidthCm',config['width_cm']),
        ('ViewShift','HairBandViewShiftCm',config['view_shift_cm']),
        ('NormalBlend','HairBandSpecNormalBlend',config['spec_normal_blend'])):
        n = create(unreal.MaterialExpressionScalarParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', value)
        bindings[key] = (n,'')
    band = custom_node(material, 'head_band', bindings)
    selection = create(unreal.MaterialExpressionLinearInterpolate)
    connect(old, '', selection, 'A')
    connect(band, '', selection, 'B')
    connect(valid, '', selection, 'Alpha')
    connect(selection, '', destination, 'A')
    LIB.recompile_material(material)
    return dict(recipe='head_band', config=config, fallback='original_uv_highlight',
                downstream_gates_preserved=True, runtime_accepted=False, visual_accepted=False)
