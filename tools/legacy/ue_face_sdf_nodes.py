"""Angular decoder shared by new masters and small engine compile probes."""
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


def decoder_encoding(material):
    """Read a generated decoder marker and its immediate arithmetic connection.

    This is a version/readback check, not a proof of every upstream UV/basis link.
    """
    if not material:
        return None
    lib = unreal.MaterialEditingLibrary
    for node in lib.get_material_expressions(material):
        if (isinstance(node, unreal.MaterialExpressionMultiply) and
                str(node.get_editor_property("desc")).startswith("Face SDF: " + ENCODING + ";") and
                abs(float(node.get_editor_property("const_b")) - 1 / math.pi) < 1e-6):
            inputs = lib.get_inputs_for_material_expression(material, node)
            if inputs and isinstance(inputs[0], unreal.MaterialExpressionArctangent2):
                return ENCODING
    return None
