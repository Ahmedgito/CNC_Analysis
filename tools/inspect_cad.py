"""Inspect a STEP/IGES file and report geometry facts that can be extracted reliably.

Optionally converts STEP -> IGES (or IGES -> STEP).

Usage
-----
    python tools/inspect_cad.py path/to/model.step
    python tools/inspect_cad.py path/to/model.step --to-iges out.igs
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from OCP.Bnd import Bnd_Box, Bnd_OBB
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def read_shape(path: Path):
    ext = path.suffix.lower()
    reader = STEPControl_Reader() if ext in (".step", ".stp") else IGESControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"cannot read {path}")
    reader.TransferRoots()
    return reader.OneShape()


def file_units(path: Path) -> str:
    """Best-effort unit detection from the raw file header."""
    head = path.read_bytes()[:200_000].decode("latin-1", "ignore").upper()
    if path.suffix.lower() in (".step", ".stp"):
        if "SI_UNIT(.MILLI.,.METRE.)" in head.replace(" ", ""):
            return "mm"
        if "INCH" in head:
            return "inch"
        if "SI_UNIT($,.METRE.)" in head.replace(" ", ""):
            return "m"
        return "unknown"
    # IGES global section: unit flag (param 14) / unit name (param 15)
    for name, unit in (("MM", "mm"), ("INCH", "inch"), ("IN", "inch"), ("M", "m")):
        if f"H{name}," in head or f"{len(name)}H{name}" in head:
            return unit
    return "unknown"


def count(shape, kind) -> int:
    exp, n = TopExp_Explorer(shape, kind), 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def cylinders(shape):
    """Group cylindrical faces by (radius, axis) -> holes (concave) vs bosses (convex)."""
    groups = defaultdict(lambda: {"faces": 0, "concave": 0})
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face(exp.Current())
        ad = BRepAdaptor_Surface(face)
        if ad.GetType() == GeomAbs_Cylinder:
            cyl = ad.Cylinder()
            ax = cyl.Axis()
            d, p = ax.Direction(), ax.Location()
            # canonical axis line: direction sign + closest point to origin
            dx, dy, dz = d.X(), d.Y(), d.Z()
            if (dx, dy, dz) < (0, 0, 0):
                dx, dy, dz = -dx, -dy, -dz
            t = p.X() * dx + p.Y() * dy + p.Z() * dz
            c = (p.X() - t * dx, p.Y() - t * dy, p.Z() - t * dz)
            key = (round(cyl.Radius() * 2, 3), tuple(round(v, 2) for v in (dx, dy, dz)),
                   tuple(round(v, 1) for v in c))
            g = groups[key]
            g["faces"] += 1
            # outward normal of a reversed cylinder face points to the axis -> hole
            if face.Orientation() == TopAbs_REVERSED:
                g["concave"] += 1
        exp.Next()

    summary = defaultdict(lambda: {"holes": 0, "bosses": 0})
    for (dia, _axis, _c), g in groups.items():
        summary[dia]["holes" if g["concave"] else "bosses"] += 1
    return {f"D{d}": v for d, v in sorted(summary.items())}


def planar_faces(shape) -> int:
    exp, n = TopExp_Explorer(shape, TopAbs_FACE), 0
    while exp.More():
        if BRepAdaptor_Surface(TopoDS.Face(exp.Current())).GetType() == GeomAbs_Plane:
            n += 1
        exp.Next()
    return n


def inspect(path: Path) -> dict:
    shape = read_shape(path)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    box.SetGap(0.0)
    lo, hi = box.CornerMin(), box.CornerMax()
    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, obb, True, True, False)
    n_solids = count(shape, TopAbs_SOLID)
    props = GProp_GProps()
    volume = None
    if n_solids:
        BRepGProp.VolumeProperties_s(shape, props)
        volume = round(props.Mass(), 1)
    sprops = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, sprops)
    return {
        "file": path.name,
        "units_in_file": file_units(path),
        "solids": n_solids,
        "shells": count(shape, TopAbs_SHELL),
        "faces": count(shape, TopAbs_FACE),
        "planar_faces": planar_faces(shape),
        "bbox_axis_aligned": [round(hi.X() - lo.X(), 3), round(hi.Y() - lo.Y(), 3),
                              round(hi.Z() - lo.Z(), 3)],
        "bbox_oriented": sorted(round(2 * v, 3) for v in
                                (obb.XHSize(), obb.YHSize(), obb.ZHSize())),
        "volume": volume,
        "surface_area": round(sprops.Mass(), 1),
        "cylinders_by_diameter": cylinders(shape),
    }


def convert(src: Path, dst: Path) -> None:
    shape = read_shape(src)
    if dst.suffix.lower() in (".igs", ".iges"):
        Interface_Static.SetCVal_s("write.iges.unit", "MM")
        w = IGESControl_Writer("MM", 1)  # BRep solids (type 186)
        w.AddShape(shape)
        w.ComputeModel()
        ok = w.Write(str(dst))
    else:
        w = STEPControl_Writer()
        w.Transfer(shape, STEPControl_AsIs)
        ok = w.Write(str(dst)) == IFSelect_RetDone
    if not ok:
        raise RuntimeError(f"conversion failed: {dst}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--to-iges", type=Path)
    ap.add_argument("--to-step", type=Path)
    a = ap.parse_args()
    print(json.dumps(inspect(a.path), indent=2))
    for out in (a.to_iges, a.to_step):
        if out:
            convert(a.path, out)
            print(f"\nwrote {out}; re-inspecting:")
            print(json.dumps(inspect(out), indent=2))


if __name__ == "__main__":
    main()
