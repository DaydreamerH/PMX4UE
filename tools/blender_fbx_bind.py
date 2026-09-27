"""Normalize only near-unit bind-matrix roundoff in new centimeter FBX exports.

Float32 accumulated basis drift can fail SDK relative-matrix checks even when
Pose == TransformLink. Use double-precision polar rotation and relative solve.
Preserve positions, local model transforms, hierarchy, geometry and weights.
Reject non-unit scale/reflections/real bind discrepancies; never overwrite input.
Requires Blender's numpy and bundled FBX parser. Relative-only is diagnostic,
not a repair (83 failures remained in the Tololo experiment).
"""
from pathlib import Path
import argparse
import sys
import numpy as np
from io_scene_fbx import parse_fbx, encode_bin

def children(node, key):
    return [e for e in node.elems if e.id == key]

def encoder(elem, overrides):
    dst = encode_bin.FBXElem(elem.id)
    methods = {b'Y': 'int16', b'C':'bool', b'I':'int32', b'L':'int64', b'F':'float32', b'D':'float64',
               b'R':'bytes', b'S':'string', b'f':'float32_array', b'd':'float64_array', b'l':'int64_array',
               b'i':'int32_array', b'b':'bool_array', b'c':'byte_array'}
    values = overrides.get(id(elem), elem.props)
    for typ, value in zip(elem.props_type, values):
        key = bytes([typ])
        if key not in methods:
            raise ValueError("Unsupported FBX property: " + repr(key))
        getattr(dst, 'add_'+methods[key])(value)
    dst.elems = [encoder(child, overrides) for child in elem.elems]
    return dst

def normalize(source, destination, orthogonalize=True):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Refusing to overwrite an FBX")
    root, version = parse_fbx.parse(str(source))
    objects = children(root, b'Objects')[0]
    by_id = {e.props[0]: e for e in objects.elems}
    parents = {}
    for c in children(root, b'Connections')[0].elems:
        if c.props[0] == b'OO':
            parents.setdefault(c.props[1], []).append(c.props[2])
    poses = []
    overrides = {}
    max_basis_change = 0.
    def rigid(matrix):
        nonlocal max_basis_change
        if not np.all(np.isfinite(matrix)):
            raise ValueError('Nonfinite bind matrix')
        u,s,v = np.linalg.svd(matrix[:3,:3])
        rotation = u@v
        # Bounded 100-ppm bind-basis correction, not object/unit rescaling.
        # The separate cm-native object-scale contract remains unchanged.
        if np.max(np.abs(s-1)) > 1e-4 or np.linalg.det(rotation) < 0:
            raise ValueError('Not a near-unit rigid bind matrix; no precision repair allowed: singular_values='+str(s)+' determinant='+str(np.linalg.det(rotation)))
        result = matrix.copy()
        result[:3,:3] = rotation
        max_basis_change = max(max_basis_change, float(np.max(np.abs(matrix-result))))
        return result
    for pose in children(objects, b'Pose'):
        if pose.props[2] != b'BindPose':
            continue
        poses.append({children(n,b'Node')[0].props[0]: np.array(children(n,b'Matrix')[0].props[0], dtype=np.float64).reshape(4,4).T
                      for n in children(pose,b'PoseNode')})
        if orthogonalize:
            for n in children(pose,b'PoseNode'):
                ident = children(n,b'Node')[0].props[0]
                poses[-1][ident] = rigid(poses[-1][ident])
                overrides[id(children(n,b'Matrix')[0])] = [poses[-1][ident].T.reshape(-1)]
    residuals, new_residuals = [], []
    for cluster in children(objects,b'Deformer'):
        if cluster.props[2] != b'Cluster':
            continue
        skins = parents.get(cluster.props[0], [])
        geometries = [g for s in skins for g in parents.get(s, []) if by_id.get(g) and by_id[g].id == b'Geometry']
        meshes = [m for g in geometries for m in parents.get(g, []) if by_id.get(m) and by_id[m].id == b'Model']
        if len(meshes) != 1:
            raise ValueError("Ambiguous skin-to-mesh connection")
        candidates = [p[meshes[0]] for p in poses if meshes[0] in p]
        if not candidates or any(np.max(np.abs(m-candidates[0])) > 1e-6 for m in candidates):
            raise ValueError("Missing/conflicting mesh bind pose")
        mesh = candidates[0]
        link = np.array(children(cluster,b'TransformLink')[0].props[0], dtype=np.float64).reshape(4,4).T
        if orthogonalize:
            link = rigid(link)
            overrides[id(children(cluster,b'TransformLink')[0])] = [link.T.reshape(-1)]
        node = children(cluster,b'Transform')[0]
        relative = np.array(node.props[0], dtype=np.float64).reshape(4,4).T
        residual = float(np.max(np.abs(link @ relative - mesh)))
        # Refuse real pose changes: this adapter is for roundoff, not bad binding.
        if not np.isfinite(residual) or residual > .01:
            raise ValueError("Cluster inconsistency exceeds precision-only bound: " + str(residual))
        corrected = np.linalg.solve(link, mesh)
        overrides[id(node)] = [corrected.T.reshape(-1)]
        residuals.append(residual)
        new_residuals.append(float(np.max(np.abs(link @ corrected - mesh))))
    if not residuals:
        raise ValueError("No skin clusters to validate")
    destination.parent.mkdir(parents=True, exist_ok=True)
    encode_bin.write(str(destination), encoder(root, overrides), version)
    # Reparse and verify EVERY semantic field, not just counts. Only explicitly
    # listed matrices may change, and those must equal the calculated doubles.
    reread, reread_version = parse_fbx.parse(str(destination))
    def verify(a,b):
        if a.id != b.id or a.props_type != b.props_type or len(a.elems)!=len(b.elems):
            raise ValueError('FBX structure changed during serialization')
        expected=overrides.get(id(a),a.props)
        if len(expected)!=len(b.props) or any(not np.array_equal(x,y) for x,y in zip(expected,b.props)):
            raise ValueError('Unexpected FBX property change: '+repr(a.id))
        for x,y in zip(a.elems,b.elems):verify(x,y)
    if reread_version != version:raise ValueError('FBX version changed')
    verify(root,reread)
    return dict(status="bind_precision_normalized" if orthogonalize else "relative_only_diagnostic", cluster_count=len(residuals),
                max_residual_before=max(residuals), max_residual_after=max(new_residuals),
                max_basis_element_change=max_basis_change, serialized_fields_verified=True,
                raw_fbx=str(source), output_fbx=str(destination),
                changed_fields="Cluster relative matrix" if not orthogonalize else 'Pose/Link near-unit rotation orthogonality and relative matrices; positions, topology, weights untouched')

if __name__ == '__main__':
    import json
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--relative-only',action='store_true',help='Diagnostic only; does not fix accumulated basis drift')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    print(json.dumps(normalize(args.input,args.output,not args.relative_only)))
