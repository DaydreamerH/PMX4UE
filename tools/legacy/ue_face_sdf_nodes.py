"""Build and read back the selected face SDF light response."""
import math
import unreal
from ue_context import expression, connect, safe_set
from face_sdf_convention import ENCODING, POLE_EPSILON


def angular_threshold(material, forward_dot, left_dot, x=-2540, y=1620):
    lateral = expression(material, unreal.MaterialExpressionAbs, x, y)
    connect(left_dot, "", lateral, "")
    safe_lateral = expression(material, unreal.MaterialExpressionMax, x + 180, y)
    connect(lateral, "", safe_lateral, "A")
    safe_set(safe_lateral, "const_b", POLE_EPSILON)
    angle = expression(material, unreal.MaterialExpressionArctangent2, x + 360, y)
    connect(safe_lateral, "", angle, "Y")
    connect(forward_dot, "", angle, "X")
    result = expression(material, unreal.MaterialExpressionMultiply, x + 540, y)
    connect(angle, "", result, "A")
    safe_set(result, "const_b", 1.0 / math.pi)
    safe_set(result, "desc", "Face SDF: " + ENCODING + "; head-plane atan2(abs(left),forward)/pi")
    return result


def cosine_half_threshold(material, forward_dot, x=-2540, y=1620):
    half = expression(material, unreal.MaterialExpressionMultiply, x, y)
    connect(forward_dot, "", half, "A")
    safe_set(half, "const_b", 0.5)
    shifted = expression(material, unreal.MaterialExpressionAdd, x + 180, y)
    connect(half, "", shifted, "A")
    safe_set(shifted, "const_b", 0.5)
    result = expression(material, unreal.MaterialExpressionOneMinus, x + 360, y)
    connect(shifted, "", result, "")
    safe_set(result, "desc", "Face SDF response: cosine_half_art; (1-dot(L,Forward))/2")
    return result


def response_readback(material):
    """Verify the node feeding both SDF thresholds, not just a present marker.

    Does not prove upstream face axes, texture UV or the compiled visual result.
    """
    if not material:
        return None
    lib = unreal.MaterialEditingLibrary
    nodes = lib.get_material_expressions(material)
    markers = {"Face SDF threshold use: shadow": None,
               "Face SDF threshold use: specular": None,
               "Face SDF threshold use: specular inverse": None,
               "Face SDF threshold use: inverse": None}
    for node in nodes:
        desc = str(node.get_editor_property("desc"))
        if desc in markers:
            if markers[desc] is not None:
                return None
            markers[desc] = node
    if any(node is None for node in markers.values()):
        return None
    def first(node):
        inputs = lib.get_inputs_for_material_expression(material, node)
        return inputs[0] if inputs else None
    shadow = first(markers["Face SDF threshold use: shadow"])
    specular = first(markers["Face SDF threshold use: specular"])
    inverse = first(markers["Face SDF threshold use: inverse"])
    specular_inverse = first(markers["Face SDF threshold use: specular inverse"])
    if (shadow is None or shadow != specular or shadow != inverse or
            specular_inverse != markers["Face SDF threshold use: inverse"]):
        return None
    desc = str(shadow.get_editor_property("desc"))
    if (isinstance(shadow, unreal.MaterialExpressionMultiply) and
            desc.startswith("Face SDF: " + ENCODING + ";") and
            abs(float(shadow.get_editor_property("const_b")) - 1 / math.pi) < 1e-6 and
            isinstance(first(shadow), unreal.MaterialExpressionArctangent2)):
        return ENCODING
    if (isinstance(shadow, unreal.MaterialExpressionOneMinus) and
            desc.startswith("Face SDF response: cosine_half_art;") and
            isinstance(first(shadow), unreal.MaterialExpressionAdd)):
        shifted = first(shadow)
        half = first(shifted)
        if (abs(float(shifted.get_editor_property("const_b")) - 0.5) < 1e-6 and
                isinstance(half, unreal.MaterialExpressionMultiply) and
                abs(float(half.get_editor_property("const_b")) - 0.5) < 1e-6 and
                isinstance(first(half), unreal.MaterialExpressionDotProduct)):
            return "cosine_half_art"
    return None
