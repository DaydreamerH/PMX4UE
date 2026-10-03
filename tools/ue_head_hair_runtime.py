"""Patch a DUPLICATED legacy hair master, preserving the unbound baseline.

No material instance, mesh or level writes. Callers must save/compile copies,
calibrate head data and install the shared FaceSDF component themselves.
"""
import unreal

LIB = unreal.MaterialEditingLibrary


def add_head_hair_runtime(material):
    nodes = list(LIB.get_material_expressions(material))

    def params(cls, name):
        return [n for n in nodes if isinstance(n, cls)
                and str(n.get_editor_property('parameter_name')) == name]

    if params(unreal.MaterialExpressionScalarParameter, 'HairBasisRuntimeValid'):
        raise ValueError('Head hair runtime already present; do not patch twice')

    def one(rows, label):
        if len(rows) != 1:
            raise ValueError('Expected one ' + label + '; inspect graph before adapting')
        return rows[0]

    def inputs(node):
        return list(LIB.get_inputs_for_material_expression(material, node))

    offset = one(params(unreal.MaterialExpressionVectorParameter, 'NormalSphereOffset'), 'sphere offset')
    center = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionAdd)
                  and offset in inputs(n)
                  and any(isinstance(i, unreal.MaterialExpressionObjectPositionWS) for i in inputs(n))],
                 'legacy object-space sphere center')
    subtract = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionSubtract)
                    and center in inputs(n)
                    and any(isinstance(i, unreal.MaterialExpressionWorldPosition) for i in inputs(n))],
                   'world position minus sphere center')
    if inputs(subtract) != [next(i for i in inputs(subtract)
                                if isinstance(i, unreal.MaterialExpressionWorldPosition)), center]:
        raise ValueError('Unexpected sphere subtraction order')
    speed = one(params(unreal.MaterialExpressionScalarParameter, 'HairSpecOffsetSpeed'), 'hair offset speed')
    multiply = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionMultiply)
                    and speed in inputs(n)], 'hair view offset multiplier')
    terms = inputs(multiply)
    if len(terms) != 2 or terms[1] != speed:
        raise ValueError('Unexpected hair view/speed wiring')
    old_vertical = terms[0]
    camera = one([n for n in nodes if isinstance(n, unreal.MaterialExpressionCameraVectorWS)
                  and n in inputs(old_vertical)], 'view vector into legacy vertical selector')
    if not isinstance(old_vertical, unreal.MaterialExpressionComponentMask) or not (
            old_vertical.get_editor_property('g') and not old_vertical.get_editor_property('r')
            and not old_vertical.get_editor_property('b') and not old_vertical.get_editor_property('a')):
        raise ValueError('Expected legacy world-Y view selector; adapt the actual graph explicitly')

    # All topology checks precede mutations; no hard-coded graph coordinates.
    def create(cls, x, y):
        node = LIB.create_material_expression(material, cls, x, y)
        if node is None:
            raise RuntimeError('Cannot create head hair expression')
        return node

    def connect(a, output, b, pin):
        if not LIB.connect_material_expressions(a, output, b, pin):
            raise RuntimeError('Cannot connect head hair pin: ' + pin)

    def vector(name, value, y):
        n = create(unreal.MaterialExpressionVectorParameter, -4000, y)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', unreal.LinearColor(*value))
        return n

    active = create(unreal.MaterialExpressionScalarParameter, -4000, 1100)
    active.set_editor_property('parameter_name', 'HairBasisRuntimeValid')
    active.set_editor_property('default_value', 0.)
    world_center = vector('HeadSphereCenterWS', (0, 0, 0, 0), 1300)
    world_up = vector('HairUpRuntimeWS', (0, 0, 1, 0), 1500)
    center_blend = create(unreal.MaterialExpressionLinearInterpolate, -3700, 1300)
    connect(center, '', center_blend, 'A')
    connect(world_center, 'RGB', center_blend, 'B')
    connect(active, '', center_blend, 'Alpha')
    connect(center_blend, '', subtract, 'B')
    up_normal = create(unreal.MaterialExpressionNormalize, -3700, 1500)
    connect(world_up, 'RGB', up_normal, 'VectorInput')
    vertical = create(unreal.MaterialExpressionDotProduct, -3400, 1500)
    connect(camera, '', vertical, 'A')
    connect(up_normal, '', vertical, 'B')
    vertical_blend = create(unreal.MaterialExpressionLinearInterpolate, -3100, 1500)
    connect(old_vertical, '', vertical_blend, 'A')
    connect(vertical, '', vertical_blend, 'B')
    connect(active, '', vertical_blend, 'Alpha')
    connect(vertical_blend, '', multiply, 'A')
    LIB.recompile_material(material)
    return dict(schema='pmx4ue.head-hair-runtime.v1', space='world',
                valid='HairBasisRuntimeValid', vectors=['HeadSphereCenterWS', 'HairUpRuntimeWS'],
                fallback='original_graph', diffuse_only_sphere=True,
                uv_texture_spec_gate_unchanged=True, runtime_accepted=False)
