# pyright: reportAttributeAccessIssue=false
# (OCP's bundled stubs miss many generated symbols; the kernel modules are covered by tests.)
"""Tessellate a measured model into binary glTF (GLB) for the 3D viewer.

One mesh per feature (node name = feature id, so the client maps a cited fact to its faces), one
``body`` mesh for the remaining faces, and one ``edges`` line set with the sharp edges (seams and
tangent edges between smooth faces are left out, the way CAD viewers draw). Two levels of detail;
triangle counts are capped so a huge model cannot stall the browser.

No numpy: positions are packed with ``array``. Normals are area-weighted per vertex within each
face, so faces shade smoothly and stay crisp at their boundaries.
"""

from __future__ import annotations

import json
import math
import struct
from array import array

from OCP.BRep import BRep_Tool  # type: ignore[import-not-found]
from OCP.BRepAdaptor import BRepAdaptor_Curve  # type: ignore[import-not-found]
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # type: ignore[import-not-found]
from OCP.BRepTools import BRepTools  # type: ignore[import-not-found]
from OCP.GCPnts import GCPnts_QuasiUniformDeflection  # type: ignore[import-not-found]
from OCP.GeomAbs import GeomAbs_C0  # type: ignore[import-not-found]
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED  # type: ignore[import-not-found]
from OCP.TopExp import TopExp_Explorer  # type: ignore[import-not-found]
from OCP.TopLoc import TopLoc_Location  # type: ignore[import-not-found]
from OCP.TopoDS import TopoDS  # type: ignore[import-not-found]

from app.domain.model import MeshInfo

MAX_TRIANGLES = {0: 300_000, 1: 30_000}
_RELATIVE = {0: 0.0006, 1: 0.004}  # linear deflection as a share of the envelope diagonal
_ANGULAR = {0: 0.25, 1: 0.6}


def _bounds(geo) -> tuple[list[float], list[float]]:
    from OCP.Bnd import Bnd_Box  # type: ignore[import-not-found]
    from OCP.BRepBndLib import BRepBndLib  # type: ignore[import-not-found]

    box = Bnd_Box()
    BRepBndLib.Add_s(geo.shape, box)
    lo, hi = box.CornerMin(), box.CornerMax()
    return [lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]


def _triangulate(geo, deflection: float, angular: float) -> dict[str, tuple[array, array, array]]:
    """feature id -> (positions, normals, indices)."""
    BRepTools.Clean_s(geo.shape)
    BRepMesh_IncrementalMesh(geo.shape, deflection, False, angular, True)
    out: dict[str, tuple[array, array, array]] = {}
    for i, face in enumerate(geo.faces):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        key = geo.face_feature.get(i, "body")
        pos, nor, idx = out.setdefault(key, (array("f"), array("f"), array("I")))
        base = len(pos) // 3
        trsf = loc.Transformation()
        n_nodes = tri.NbNodes()
        acc = [[0.0, 0.0, 0.0] for _ in range(n_nodes)]
        pts = []
        for k in range(1, n_nodes + 1):
            p = tri.Node(k).Transformed(trsf)
            pts.append((p.X(), p.Y(), p.Z()))
            pos.extend((p.X(), p.Y(), p.Z()))
        flip = face.Orientation() == TopAbs_REVERSED
        for k in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(k).Get()
            if flip:
                b, c = c, b
            pa, pb, pc = pts[a - 1], pts[b - 1], pts[c - 1]
            u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
            v = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            for j in (a, b, c):
                s = acc[j - 1]
                s[0] += n[0]
                s[1] += n[1]
                s[2] += n[2]
            idx.extend((base + a - 1, base + b - 1, base + c - 1))
        for s in acc:
            m = math.sqrt(s[0] ** 2 + s[1] ** 2 + s[2] ** 2) or 1.0
            nor.extend((s[0] / m, s[1] / m, s[2] / m))
    return out


def _sharp_edges(geo, deflection: float) -> array:
    """Line segments (pairs of points) for the edges a drawing would show."""
    edge_faces: dict[int, list] = {}
    edges: dict[int, object] = {}
    for face in geo.faces:
        ex = TopExp_Explorer(face, TopAbs_EDGE)
        while ex.More():
            e = TopoDS.Edge(ex.Current())
            h = hash(e)
            edges.setdefault(h, e)
            edge_faces.setdefault(h, []).append(face)
            ex.Next()
    out = array("f")
    for h, e in edges.items():
        fs = edge_faces[h]
        if BRep_Tool.Degenerated_s(e):
            continue
        if len(fs) == 1 and BRep_Tool.IsClosed_s(e, fs[0]):
            continue  # seam of a periodic face
        if len(fs) == 2 and fs[0].IsSame(fs[1]):
            continue  # seam seen from both sides of one face
        if len(fs) == 2 and BRep_Tool.Continuity_s(e, fs[0], fs[1]) != GeomAbs_C0:
            continue  # tangent edge between smooth faces (split cylinder halves)
        curve = BRepAdaptor_Curve(e)
        disc = GCPnts_QuasiUniformDeflection(curve, deflection)
        if not disc.IsDone() or disc.NbPoints() < 2:
            continue
        prev = None
        for k in range(1, disc.NbPoints() + 1):
            p = disc.Value(k)
            cur = (p.X(), p.Y(), p.Z())
            if prev is not None:
                out.extend(prev)
                out.extend(cur)
            prev = cur
    return out


def _glb(meshes: dict[str, tuple[array, array, array]], lines: array, stem: str) -> bytes:
    blob = bytearray()
    views, accessors, gl_meshes, nodes = [], [], [], []

    def add_view(data: bytes, target: int | None) -> int:
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        views.append(view)
        return len(views) - 1

    def add_accessor(view: int, ctype: int, count: int, kind: str, mn=None, mx=None) -> int:
        acc = {"bufferView": view, "componentType": ctype, "count": count, "type": kind}
        if mn is not None:
            acc["min"], acc["max"] = mn, mx
        accessors.append(acc)
        return len(accessors) - 1

    def minmax(pos: array) -> tuple[list[float], list[float]]:
        xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
        return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]

    for key in sorted(meshes, key=lambda k: (k == "body", k)):
        pos, nor, idx = meshes[key]
        if not idx:
            continue
        mn, mx = minmax(pos)
        a_pos = add_accessor(add_view(pos.tobytes(), 34962), 5126, len(pos) // 3, "VEC3", mn, mx)
        a_nor = add_accessor(add_view(nor.tobytes(), 34962), 5126, len(nor) // 3, "VEC3")
        a_idx = add_accessor(add_view(idx.tobytes(), 34963), 5125, len(idx), "SCALAR")
        gl_meshes.append(
            {
                "name": key,
                "primitives": [
                    {
                        "attributes": {"POSITION": a_pos, "NORMAL": a_nor},
                        "indices": a_idx,
                        "mode": 4,
                    }
                ],
            }
        )
        nodes.append(
            {
                "name": key,
                "mesh": len(gl_meshes) - 1,
                "extras": {"feature": key, "fact_id": f"{stem}!m!{key}" if key != "body" else None},
            }
        )
    if lines:
        mn, mx = minmax(lines)
        a_line = add_accessor(
            add_view(lines.tobytes(), 34962), 5126, len(lines) // 3, "VEC3", mn, mx
        )
        gl_meshes.append(
            {"name": "edges", "primitives": [{"attributes": {"POSITION": a_line}, "mode": 1}]}
        )
        nodes.append({"name": "edges", "mesh": len(gl_meshes) - 1, "extras": {"feature": "edges"}})
    doc = {
        "asset": {"version": "2.0", "generator": "cnc-analyzer (OpenCascade)"},
        "extras": {"units": "mm"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": gl_meshes,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(js), b"JSON")
        + js
        + struct.pack("<I4s", len(blob), b"BIN\x00")
        + bytes(blob)
    )


def build_meshes(geo) -> tuple[dict[int, bytes], MeshInfo]:
    lo, hi = _bounds(geo)
    diag = math.dist(lo, hi) or 1.0
    out: dict[int, bytes] = {}
    tris: dict[str, int] = {}
    for lod in (1, 0):
        deflection = max(diag * _RELATIVE[lod], 0.002)
        meshes: dict[str, tuple[array, array, array]] = {}
        count = 0
        for _ in range(5):
            meshes = _triangulate(geo, deflection, _ANGULAR[lod])
            count = sum(len(m[2]) // 3 for m in meshes.values())
            if count <= MAX_TRIANGLES[lod]:
                break
            deflection *= 2
        lines = _sharp_edges(geo, deflection)
        out[lod] = _glb(meshes, lines, geo.stem)
        tris[str(lod)] = count
    info = MeshInfo(
        lods=sorted(out),
        triangles=tris,
        face_feature={str(k): v for k, v in geo.face_feature.items()},
        bounds=[lo, hi],
    )
    return out, info
