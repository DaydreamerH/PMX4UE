"""PMX to Blender basis, matching mmd_tools rigid-body/joint creation."""
from mathutils import Euler


def point(v, scale=1):
    return [float(v[i]) * scale for i in (0, 2, 1)]


def rotation(v):
    q = Euler(tuple(-v[i] for i in (0, 2, 1)), "YXZ").to_quaternion()
    return [q.x, q.y, q.z, q.w]
