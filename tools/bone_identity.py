"""Preserve imported PMX identities, never translate or infer by display name."""
def collect(armature):
    rows = []
    for bone in armature.pose.bones:
        mmd = getattr(bone, "mmd_bone", None)
        source_name = getattr(mmd, "name_j", "") if mmd else ""
        source_id = getattr(mmd, "bone_id", -1) if mmd else -1
        rows.append(dict(export_bone=bone.name, source_name=source_name, source_bone_id=source_id))
    return rows


def unique_map(rows):
    result = {}
    ambiguous = set()
    for row in rows:
        name = row["source_name"]
        if not name:
            continue
        if name in result and result[name] != row["export_bone"]:
            ambiguous.add(name)
        result[name] = row["export_bone"]
    for name in ambiguous:
        result.pop(name)
    return result, sorted(ambiguous)
