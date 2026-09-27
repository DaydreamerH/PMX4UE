"""Use the installed FBX codec's type contract, not an assumed Blender version."""


def encoder_methods(data_types, element_class):
    methods = {}
    for symbol in ("BOOL", "CHAR", "INT8", "INT16", "INT32", "INT64", "FLOAT32", "FLOAT64",
                   "BYTES", "STRING", "FLOAT32_ARRAY", "FLOAT64_ARRAY", "INT32_ARRAY",
                   "INT64_ARRAY", "BOOL_ARRAY", "BYTE_ARRAY"):
        code = getattr(data_types, symbol, None)
        if code is None:
            continue
        method = "add_" + symbol.lower()
        if not callable(getattr(element_class, method, None)):
            raise ValueError("FBX encoder lacks method for declared type: " + symbol)
        if code in methods:
            raise ValueError("Ambiguous FBX scalar/array type: " + symbol)
        methods[code] = method
    return methods
