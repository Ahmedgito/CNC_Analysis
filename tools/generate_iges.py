"""Generate synthetic IGES models for the SPEC'26 test parts.

The organizers' synthetic datasets ship WITHOUT IGES files and ask teams to
model each part from the answer keys in ``backend/evals/answer_keys/``. This script does that with
build123d (OpenCascade) so the models are reproducible.

Notes
-----
* 2283 is modelled from the PDF dims (D48), NOT the Excel (D50), so the
  planted OD mismatch is visible in the 3-way cross-check.
* 2284 intentionally gets NO IGES (missing-file test).
* Default export is "faces" mode (IGES type 144 trimmed surfaces), the same as
  FreeCAD's default. Use ``--brep`` to write solids (type 186) instead.

Usage
-----
    pip install build123d
    python tools/generate_iges.py            # surfaces (default)
    python tools/generate_iges.py --brep     # BRep solids
"""
from __future__ import annotations

import argparse
from pathlib import Path

import build123d as b3d
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer

ROOT = Path(__file__).resolve().parents[1]
BATCH1 = ROOT / "docs" / "spec26_synthetic_data" / "iges"
BATCH2 = ROOT / "docs" / "spec26_batch2_hard" / "iges"


# --------------------------------------------------------------------------- #
# Part models (all dimensions in mm, Z = axial / thickness direction)
# --------------------------------------------------------------------------- #
def flange_2280() -> b3d.Part:
    """D120 x 20 flange, centre bore D40, 6 x D10 holes on D90 PCD."""
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=60, height=20, align=_base())
        b3d.Cylinder(radius=20, height=20, align=_base(), mode=b3d.Mode.SUBTRACT)
        with b3d.PolarLocations(radius=45, count=6):
            b3d.Cylinder(radius=5, height=20, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part


def shaft_2281() -> b3d.Part:
    """Stepped shaft: D30 x 160 + D25 x 40 step (overall 200)."""
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=15, height=160, align=_base())
        with b3d.Locations((0, 0, 160)):
            b3d.Cylinder(radius=12.5, height=40, align=_base())
    return p.part


def bracket_2282() -> b3d.Part:
    """4.000 x 2.500 x 0.375 in plate, 4 x D0.250 in holes 0.5 in from edges."""
    inch = 25.4
    L, W, T = 4.0 * inch, 2.5 * inch, 0.375 * inch
    e = 0.5 * inch
    with b3d.BuildPart() as p:
        b3d.Box(L, W, T, align=_corner())
        with b3d.Locations(*[(x, y, 0) for x in (e, L - e) for y in (e, W - e)]):
            b3d.Cylinder(radius=0.125 * inch, height=T, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part


def bushing_2283() -> b3d.Part:
    """Bushing per PDF: OD48 x 40, bore D30 (Excel says OD50 -> planted mismatch)."""
    return _tube(od=48, id_=30, length=40)


def gear_blank_3001() -> b3d.Part:
    """D80 x 15 gear blank, bore D25."""
    return _tube(od=80, id_=25, length=15)


def coupling_hub_3002() -> b3d.Part:
    """Rev B: D55 x 40 hub, bore D20, 1 x M6 radial tapped (modelled as D5 tap drill)."""
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=27.5, height=40, align=_base())
        b3d.Cylinder(radius=10, height=40, align=_base(), mode=b3d.Mode.SUBTRACT)
        with b3d.Locations(b3d.Location((0, 0, 20), (0, 90, 0))):
            b3d.Cylinder(radius=2.5, height=27.5, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part


def base_plate_3003() -> b3d.Part:
    """200 x 120 x 15 plate, 4 x D14 holes 20 mm from edges."""
    L, W, T, e = 200, 120, 15, 20
    with b3d.BuildPart() as p:
        b3d.Box(L, W, T, align=_corner())
        with b3d.Locations(*[(x, y, 0) for x in (e, L - e) for y in (e, W - e)]):
            b3d.Cylinder(radius=7, height=T, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part


def shaft_collar_3004() -> b3d.Part:
    """D50.8 x 19.05 collar (2.000 x 0.750 in), bore D25.4 (1.000 in)."""
    return _tube(od=50.8, id_=25.4, length=19.05)


PARTS = {
    BATCH1 / "2280_flange.igs": flange_2280,
    BATCH1 / "2281_shaft.igs": shaft_2281,
    BATCH1 / "2282_bracket.igs": bracket_2282,
    BATCH1 / "2283_bushing.igs": bushing_2283,
    # 2284: intentionally no IGES
    BATCH2 / "3001_gear_blank.igs": gear_blank_3001,
    BATCH2 / "3002_coupling_hub_RevB.igs": coupling_hub_3002,
    BATCH2 / "3003_base_plate.igs": base_plate_3003,
    BATCH2 / "3004_shaft_collar.igs": shaft_collar_3004,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _base():
    return (b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN)


def _corner():
    return (b3d.Align.MIN, b3d.Align.MIN, b3d.Align.MIN)


def _tube(od: float, id_: float, length: float) -> b3d.Part:
    with b3d.BuildPart() as p:
        b3d.Cylinder(radius=od / 2, height=length, align=_base())
        b3d.Cylinder(radius=id_ / 2, height=length, align=_base(), mode=b3d.Mode.SUBTRACT)
    return p.part


def write_iges(part: b3d.Part, path: Path, brep: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = IGESControl_Writer("MM", 1 if brep else 0)
    writer.AddShape(part.wrapped)
    writer.ComputeModel()
    if not writer.Write(str(path)):
        raise RuntimeError(f"IGES write failed: {path}")


def read_bbox(path: Path) -> tuple[float, float, float]:
    reader = IGESControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"IGES read failed: {path}")
    reader.TransferRoots()
    box = Bnd_Box()
    BRepBndLib.Add_s(reader.OneShape(), box)
    box.SetGap(0.0)
    lo, hi = box.CornerMin(), box.CornerMax()
    return (round(hi.X() - lo.X(), 3), round(hi.Y() - lo.Y(), 3), round(hi.Z() - lo.Z(), 3))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brep", action="store_true", help="export BRep solids (type 186)")
    args = ap.parse_args()

    for path, build in PARTS.items():
        write_iges(build(), path, args.brep)
        print(f"{path.relative_to(ROOT)}  bbox(mm)={read_bbox(path)}")


if __name__ == "__main__":
    main()

