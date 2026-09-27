"""Opt-in world-space face basis on a DUPLICATED master. No mesh/level mutation.

The old basis remains the fallback for material thumbnails/unbound previews.
New runtime values bypass Local->World; head calibration is per character.
"""
import unreal

LIB = unreal.MaterialEditingLibrary


def add_runtime_basis(material):
    nodes = list(LIB.get_material_expressions(material))
    if any(isinstance(n, unreal.MaterialExpressionScalarParameter) and
           str(n.get_editor_property("parameter_name")) == "FaceBasisRuntimeValid" for n in nodes):
        raise ValueError("Runtime basis already present; refusing repeated patch")
    pairs = []
    # Discover semantic connections, not hard-coded graph coordinates.
    for legacy, runtime in (("FaceForwardWS", "FaceForwardRuntimeWS"),
                            ("FaceLeftWS", "FaceLeftRuntimeWS")):
        params = [n for n in nodes if isinstance(n, unreal.MaterialExpressionVectorParameter)
                  and str(n.get_editor_property("parameter_name")) == legacy]
        if len(params) != 1:
            raise ValueError(f"Expected one {legacy}")
        transforms = [n for n in nodes if isinstance(n, unreal.MaterialExpressionTransform)
                      and params[0] in LIB.get_inputs_for_material_expression(material, n)]
        if len(transforms) != 1:
            raise ValueError(f"Expected one legacy local/world transform for {legacy}")
        transform = transforms[0]
        if transform.get_editor_property("transform_source_type") != unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL or \
           transform.get_editor_property("transform_type") != unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD:
            raise ValueError("Unsupported basis space; inspect before adapting")
        normalizers = [n for n in nodes if isinstance(n, unreal.MaterialExpressionNormalize)
                       and transform in LIB.get_inputs_for_material_expression(material, n)]
        if len(normalizers) != 1:
            raise ValueError(f"Expected one basis normalizer for {legacy}")
        pairs.append((runtime, params[0], transform, normalizers[0]))

    def create(cls, x, y):
        node = LIB.create_material_expression(material, cls, x, y)
        if not node:
            raise RuntimeError("Cannot create material expression")
        return node

    def connect(a, output, b, pin):
        if not LIB.connect_material_expressions(a, output, b, pin):
            raise RuntimeError(f"Cannot connect {pin}")

    active = create(unreal.MaterialExpressionScalarParameter, -3700, 1300)
    active.set_editor_property("parameter_name", "FaceBasisRuntimeValid")
    active.set_editor_property("default_value", 0.)
    for i, (name, original, transform, normalizer) in enumerate(pairs):
        vector = create(unreal.MaterialExpressionVectorParameter, -3700, 1500+i*220)
        vector.set_editor_property("parameter_name", name)
        vector.set_editor_property("default_value", original.get_editor_property("default_value"))
        blend = create(unreal.MaterialExpressionLinearInterpolate, -3400, 1500+i*220)
        blend.set_editor_property("desc", "Head world basis; no second LocalToWorld")
        connect(transform, "", blend, "A")
        connect(vector, "RGB", blend, "B")
        connect(active, "", blend, "Alpha")
        connect(blend, "", normalizer, "VectorInput")
    LIB.recompile_material(material)
    return {"version": 1, "valid": "FaceBasisRuntimeValid", "vectors": [p[0] for p in pairs],
            "space": "world", "fallback": "legacy_component_space", "light_input_unchanged": True}
