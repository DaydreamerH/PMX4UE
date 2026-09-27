"""Read-only FBX bind-pose and skin-cluster matrix comparison."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from io_scene_fbx import parse_fbx
from mathutils import Matrix


def children(elem, key):
    return [item for item in elem.elems if item.id == key]


def matrix_of(elem):
    values = elem.props[0]
    return Matrix(tuple(tuple(values[4 * i + j] for j in range(4)) for i in range(4)))


def audit(path):
    root, _ = parse_fbx.parse(str(path))
    objects = children(root, b"Objects")[0]
    models = {item.props[0]: item for item in children(objects, b"Model")}
    poses = []
    for pose in children(objects, b"Pose"):
        nodes = []
        for entry in children(pose, b"PoseNode"):
            node = children(entry, b"Node")[0].props[0]
            matrix = matrix_of(children(entry, b"Matrix")[0])
            model = models.get(node)
            name = model.props[1].split(b"\0")[0].decode("utf-8", "replace") if model else str(node)
            nodes.append((node, name, matrix))
        poses.append({"name": repr(pose.props[1]), "node_count": len(nodes),
                      "nodes": nodes})
    clusters = []
    for item in children(objects, b"Deformer"):
        if item.props[2] != b"Cluster":
            continue
        link = children(item, b"TransformLink")
        reference = children(item, b"Transform")
        clusters.append({"name": item.props[1].split(b"\0")[0].decode("utf-8", "replace"),
                         "link": matrix_of(link[0]) if link else None,
                         "reference": matrix_of(reference[0]) if reference else None})
    bind = max(poses, key=lambda pose: pose["node_count"])
    pose_by_name = {name: mat for _, name, mat in bind["nodes"]}
    findings = []
    for cluster in clusters:
        name = cluster["name"]
        matches = [(name, pose_by_name[name])] if name in pose_by_name else []
        if len(matches) == 1 and cluster["link"] is not None:
            bone, matrix = matches[0]
            delta = max(abs(matrix[i][j] - cluster["link"][i][j])
                        for i in range(4) for j in range(4))
            findings.append((delta, bone, name))
    mesh_nodes = [(name, matrix) for ident, name, matrix in bind["nodes"]
                  if models[ident].props[2] == b"Mesh"]
    mesh_findings = []
    for cluster in clusters:
        if cluster["reference"] is None:
            continue
        for name, matrix in mesh_nodes:
            # Serialized FBX row-vector matrices: Transform is relative to the
            # link, not the global mesh matrix returned by SDK GetTransformMatrix.
            # This diagnostic is float32 and cannot certify SDK bind validity.
            global_reference = cluster["reference"] @ cluster["link"]
            delta = max(abs(matrix[i][j] - global_reference[i][j])
                        for i in range(4) for j in range(4))
            mesh_findings.append((delta, name, cluster["name"]))
    return {
        "path": str(path), "model_count": len(models), "cluster_count": len(clusters),
        "scope": "Blender serialized matrix consistency only; SDK/UE bind validation still required. Mesh comparisons assume a single mesh.",
        "poses": [{"name": p["name"], "node_count": p["node_count"]} for p in poses],
        "bind_missing_models": sorted(m.props[1].split(b"\0")[0].decode("utf-8", "replace")
                                      for ident, m in models.items()
                                      if ident not in {node for node, _, _ in bind["nodes"]}),
        "bind_names_sample": [name for _, name, _ in bind["nodes"][:12]],
        "matched_cluster_count": len(findings),
        "cluster_pose_max_matrix_delta": max((item[0] for item in findings), default=None),
        "cluster_pose_largest_deltas": sorted(findings, reverse=True)[:12],
        "mesh_pose_matrix_samples": {name: [list(row) for row in mat]
                                     for name, mat in mesh_nodes[:3]},
        "cluster_reference_matrix_sample": [list(row) for row in clusters[0]["reference"]]
                                           if clusters and clusters[0]["reference"] else None,
        "mesh_cluster_reference_max_delta": max((item[0] for item in mesh_findings), default=None),
        "mesh_cluster_reference_largest_deltas": sorted(mesh_findings, reverse=True)[:10],
        "cluster_reference_largest_samples": [
            {"name": item[2], "matrix": [list(row) for row in next(
                cluster["reference"] for cluster in clusters if cluster["name"] == item[2])]
            } for item in sorted(mesh_findings, reverse=True)[:2]
        ],
        "matrix_samples": {name: [list(row) for row in pose_by_name[name]]
                           for name in ("Center", "LowerBody", "ParentNode")
                           if name in pose_by_name},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fbx", nargs="+", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    for path in args.fbx:
        print("MMD2UE_BIND_AUDIT " + json.dumps(audit(path), ensure_ascii=False))


if __name__ == "__main__":
    main()
