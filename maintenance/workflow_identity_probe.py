"""Read-only Blender evidence for PMX metadata preservation; no exports/saves."""
import bpy
import addon_utils
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'tools'))
from bone_identity import collect, unique_map
addon_utils.enable('mmd_tools')
armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
assert len(armatures) == 1
rows = collect(armatures[0])
mapping, ambiguous = unique_map(rows)
out = root.parent/'Saved/PMX4UE/WorkflowProbe_v1/bone_identity_v2.json'
with out.open('x',encoding='utf-8') as f:
    json.dump(dict(rows=rows, unique_count=len(mapping), ambiguous=ambiguous),f,ensure_ascii=False,indent=2)
assert mapping, 'mmd_tools source metadata not loaded; refuse guessed mappings'
