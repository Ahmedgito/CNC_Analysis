# pyright: reportAttributeAccessIssue=false
# (OCP's bundled stubs miss many generated symbols; the kernel modules are covered by tests.)
"""Measure a transferred IGES shape: topology, part frame, and the features a reviewer can trust.

Conservative by design. A feature is reported only when the geometry proves it, and it records
the faces it came from and the rule that produced it (``method``). Rules (PLAN_LEVEL3 4.3):

- A face is a cylinder when its surface is a native cylinder, a revolution of a line parallel to
  the axis (how faces-mode exporters write them), or a B-spline that canonical recognition
  matches within 1e-4 mm (then ``inferred``).
- Exporters split full cylinders into partial faces; faces with the same radius on the same
  axis line and overlapping axial span are merged. Only a 360° sweep is a hole or a boss.
- Hole vs boss: the face normal (with orientation) points toward the axis for a hole.
- Through vs blind: a probe just past each end of the hole, on its axis, is outside material.
- The part is turned when its largest boss is the outer envelope around that axis; the
  envelope is measured in the part's own frame, never the file's axes.
- A circular pattern is centred on the main axis or another hole/boss axis with equal angular
  spacing; otherwise equal holes form a grid or a row with their pitch.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from OCP.Bnd import Bnd_Box, Bnd_OBB  # type: ignore[import-not-found]
from OCP.BRep import BRep_Tool  # type: ignore[import-not-found]
from OCP.BRepAdaptor import BRepAdaptor_Surface  # type: ignore[import-not-found]
from OCP.BRepBndLib import BRepBndLib  # type: ignore[import-not-found]
from OCP.BRepBuilderAPI import (  # type: ignore[import-not-found]
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
    BRepBuilderAPI_Transform,
)
from OCP.BRepCheck import BRepCheck_Analyzer  # type: ignore[import-not-found]
from OCP.BRepClass3d import BRepClass3d_SolidClassifier  # type: ignore[import-not-found]
from OCP.BRepGProp import BRepGProp  # type: ignore[import-not-found]
from OCP.BRepLProp import BRepLProp_SLProps  # type: ignore[import-not-found]
from OCP.GeomAbs import (  # type: ignore[import-not-found]
    GeomAbs_BSplineSurface,
    GeomAbs_Circle,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Line,
    GeomAbs_Plane,
    GeomAbs_SurfaceOfRevolution,
    GeomAbs_Torus,
)
from OCP.gp import gp_Ax3, gp_Cylinder, gp_Dir, gp_Pnt, gp_Trsf  # type: ignore[import-not-found]
from OCP.GProp import GProp_GProps  # type: ignore[import-not-found]
from OCP.ShapeAnalysis import ShapeAnalysis_CanonicalRecognition  # type: ignore[import-not-found]
from OCP.TopAbs import (  # type: ignore[import-not-found]
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp_Explorer  # type: ignore[import-not-found]
from OCP.TopoDS import TopoDS  # type: ignore[import-not-found]

from app.domain.model import ModelFeature, ModelHeader, PartForm, Topology
from app.geometry.errors import ModelLimitError, UnreadableModelError

EPS = 1e-3  # mm: positions and radii are equal within this
ANG = 1e-4  # rad: directions are parallel within this
RECOGNITION_TOL = 1e-4  # mm: B-spline faces recognised as cylinders within this
MAX_FACES = 20_000

Vec = tuple[float, float, float]


# ----------------------------------------------------------------------------------- vectors


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec) -> Vec:
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 0 else (0.0, 0.0, 1.0)


def _canon_dir(d: Vec) -> Vec:
    """Directions differing only in sign describe the same axis line."""
    for c in d:
        if abs(c) > ANG:
            return d if c > 0 else _mul(d, -1.0)
    return d


def _parallel(a: Vec, b: Vec) -> bool:
    return abs(abs(_dot(a, b)) - 1.0) < ANG


def _xyz(p) -> Vec:
    return (p.X(), p.Y(), p.Z())


def fmt(x: float, places: int = 4) -> str:
    """120.0 -> '120', 6.35 -> '6.35', 9.525 -> '9.525'."""
    s = f"{x:.{places}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ----------------------------------------------------------------------------------- surfaces


@dataclass(slots=True)
class Cyl:
    face: int
    radius: float
    foot: Vec  # point of the axis line closest to the origin
    dir: Vec  # canonical unit direction
    hole: bool
    sweep: float  # radians covered by this face
    t0: float  # axial extent along dir, measured from foot
    t1: float
    how: str  # native | revolved line | recognised


@dataclass(slots=True)
class Cone:
    face: int
    half_angle: float
    length: float
    foot: Vec
    dir: Vec


@dataclass(slots=True)
class Torus:
    face: int
    minor: float
    major: float


@dataclass(slots=True)
class Geometry:
    """What the measurement found, plus the kernel shapes the artifact builders reuse."""

    topology: Topology
    valid: bool
    bodies: int
    form: PartForm
    features: list[ModelFeature]
    faces: list = field(default_factory=list)  # TopoDS_Face, in a stable order
    face_feature: dict[int, str] = field(default_factory=dict)
    shape: object = None  # the shape the faces belong to (solid, compound or shell)
    solids: list = field(default_factory=list)
    frame: tuple[Vec, Vec, Vec, Vec] | None = None  # origin, x, y, z of the part frame
    stem: str = ""


def _foot(loc: Vec, d: Vec) -> Vec:
    return _sub(loc, _mul(d, _dot(loc, d)))


def _face_vertices(face) -> list[Vec]:
    pts: list[Vec] = []
    ex = TopExp_Explorer(face, TopAbs_VERTEX)
    while ex.More():
        pts.append(_xyz(BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))))
        ex.Next()
    if not pts:
        box = Bnd_Box()
        BRepBndLib.Add_s(face, box)
        pts = [_xyz(box.CornerMin()), _xyz(box.CornerMax())]
    return pts


def _normal_points_to_axis(face, ad, foot: Vec, d: Vec) -> bool:
    u = (ad.FirstUParameter() + ad.LastUParameter()) / 2
    v = (ad.FirstVParameter() + ad.LastVParameter()) / 2
    props = BRepLProp_SLProps(ad, u, v, 1, 1e-7)
    if not props.IsNormalDefined():
        return False
    n = _xyz(props.Normal())
    if face.Orientation() == TopAbs_REVERSED:
        n = _mul(n, -1.0)
    p = _xyz(props.Value())
    w = _sub(p, foot)
    radial = _sub(w, _mul(d, _dot(w, d)))
    return _dot(radial, n) < 0


def _as_cylinder(face, ad) -> tuple[float, Vec, Vec, str] | None:
    t = ad.GetType()
    if t == GeomAbs_Cylinder:
        c = ad.Cylinder()
        ax = c.Axis()
        return c.Radius(), _xyz(ax.Location()), _xyz(ax.Direction()), "native"
    if t == GeomAbs_SurfaceOfRevolution:
        basis = ad.BasisCurve()
        if basis.GetType() != GeomAbs_Line:
            return None
        ax = ad.AxeOfRevolution()
        a, o = _xyz(ax.Direction()), _xyz(ax.Location())
        ln = basis.Line()
        if not _parallel(_xyz(ln.Direction()), a):
            return None
        w = _sub(_xyz(ln.Location()), o)
        r = _norm(_sub(w, _mul(a, _dot(w, a))))
        return r, o, a, "revolved line"
    if t == GeomAbs_BSplineSurface:
        cyl = gp_Cylinder()
        if ShapeAnalysis_CanonicalRecognition(face).IsCylinder(RECOGNITION_TOL, cyl):
            ax = cyl.Axis()
            return cyl.Radius(), _xyz(ax.Location()), _xyz(ax.Direction()), "recognised"
    return None


def _cylinder(i: int, face) -> Cyl | None:
    ad = BRepAdaptor_Surface(face)
    found = _as_cylinder(face, ad)
    if found is None:
        return None
    r, loc, d, how = found
    d = _canon_dir(_unit(d))
    foot = _foot(loc, d)
    ts = [_dot(_sub(p, foot), d) for p in _face_vertices(face)]
    sweep = abs(ad.LastUParameter() - ad.FirstUParameter())
    if how == "recognised":  # u range of a B-spline is not an angle; measure it from vertices
        sweep = _sweep_from_vertices(face, foot, d)
    return Cyl(
        face=i,
        radius=r,
        foot=foot,
        dir=d,
        hole=_normal_points_to_axis(face, ad, foot, d),
        sweep=min(sweep, 2 * math.pi),
        t0=min(ts),
        t1=max(ts),
        how=how,
    )


def _sweep_from_vertices(face, foot: Vec, d: Vec) -> float:
    """For a recognised B-spline cylinder: a closed face (seam) is a full turn."""
    ad = BRepAdaptor_Surface(face)
    return 2 * math.pi if (ad.IsUClosed() or ad.IsVClosed()) else math.pi


def _cone(i: int, face, ad) -> Cone | None:
    t = ad.GetType()
    if t == GeomAbs_Cone:
        c = ad.Cone()
        ax = c.Axis()
        d = _canon_dir(_unit(_xyz(ax.Direction())))
        foot = _foot(_xyz(ax.Location()), d)
        ts = [_dot(_sub(p, foot), d) for p in _face_vertices(face)]
        return Cone(i, abs(c.SemiAngle()), max(ts) - min(ts), foot, d)
    if t == GeomAbs_SurfaceOfRevolution and ad.BasisCurve().GetType() == GeomAbs_Line:
        ax = ad.AxeOfRevolution()
        a = _unit(_xyz(ax.Direction()))
        ld = _unit(_xyz(ad.BasisCurve().Line().Direction()))
        cosang = abs(_dot(a, ld))
        if ANG < cosang < 1 - ANG:  # neither parallel (cylinder) nor perpendicular (plane)
            d = _canon_dir(a)
            foot = _foot(_xyz(ax.Location()), d)
            ts = [_dot(_sub(p, foot), d) for p in _face_vertices(face)]
            return Cone(i, math.acos(cosang), max(ts) - min(ts), foot, d)
    return None


def _torus(i: int, ad) -> Torus | None:
    t = ad.GetType()
    if t == GeomAbs_Torus:
        tor = ad.Torus()
        return Torus(i, tor.MinorRadius(), tor.MajorRadius())
    if t == GeomAbs_SurfaceOfRevolution and ad.BasisCurve().GetType() == GeomAbs_Circle:
        return Torus(i, ad.BasisCurve().Circle().Radius(), 0.0)
    return None


# ----------------------------------------------------------------------------------- topology


def _faces(shape) -> list:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return out


def _count(shape, kind) -> int:
    n = 0
    ex = TopExp_Explorer(shape, kind)
    while ex.More():
        n += 1
        ex.Next()
    return n


def _volume(solid) -> float:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    return g.Mass()


def _solidify(shape, tolerance: float, warnings: list[str]):
    """Return (topology, solids, shape_for_faces, valid)."""
    solids = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        solids.append(TopoDS.Solid(ex.Current()))
        ex.Next()
    if not solids:
        if _count(shape, TopAbs_FACE) == 0:
            return ("wireframe" if _count(shape, TopAbs_EDGE) else "empty"), [], shape, False
        sew = BRepBuilderAPI_Sewing(tolerance)
        sew.Add(shape)
        sew.Perform()
        sewn = sew.SewedShape()
        free = sew.NbFreeEdges()
        shells = []
        sx = TopExp_Explorer(sewn, TopAbs_SHELL)
        while sx.More():
            shells.append(TopoDS.Shell(sx.Current()))
            sx.Next()
        if free or not shells:
            warnings.append(
                f"the surfaces do not close into a solid ({free} free "
                f"edge{'s' if free != 1 else ''} "
                f"after sewing at {tolerance:g} mm); volume and surface area are not derivable"
            )
            return "open_shell", [], sewn, False
        for sh in shells:
            mk = BRepBuilderAPI_MakeSolid(sh)
            if mk.IsDone():
                solids.append(mk.Solid())
    fixed = []
    for s in solids:
        if _volume(s) < 0:  # shell oriented inside out
            s.Reverse()
            warnings.append("a shell was oriented inside out and was reversed before measuring")
        fixed.append(s)
    fixed.sort(key=_volume, reverse=True)
    valid = all(BRepCheck_Analyzer(s).IsValid() for s in fixed)
    if not valid:
        warnings.append("the solid fails the kernel's validity check; volume is not reported")
    topology: Topology = "solid" if len(fixed) == 1 else "multi_solid"
    if topology == "multi_solid":
        warnings.append(
            f"the file holds {len(fixed)} separate solids; part-level size checks are not "
            "comparable and each body is measured on its own"
        )
    from OCP.BRep import BRep_Builder  # type: ignore[import-not-found]
    from OCP.TopoDS import TopoDS_Compound  # type: ignore[import-not-found]

    if len(fixed) == 1:
        container = fixed[0]
    else:
        container = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(container)
        for s in fixed:
            b.Add(container, s)
    return topology, fixed, container, valid


def _extents_in_frame(shape, origin: Vec, z: Vec, x: Vec) -> tuple[Vec, Vec]:
    """Axis-aligned box of the shape expressed in the frame (origin, x, z)."""
    trsf = gp_Trsf()
    trsf.SetTransformation(gp_Ax3(gp_Pnt(*origin), gp_Dir(*z), gp_Dir(*x)))
    local = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(local, box, False, False)
    return _xyz(box.CornerMin()), _xyz(box.CornerMax())


def _perpendicular(z: Vec) -> Vec:
    for cand in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        x = _sub(cand, _mul(z, _dot(cand, z)))
        if _norm(x) > 0.5:
            return _unit(x)
    return (1.0, 0.0, 0.0)


def _plane_normals(faces) -> list[tuple[float, Vec]]:
    """(total area, canonical normal) per distinct planar direction, largest first."""
    groups: dict[tuple, list] = {}
    for face in faces:
        ad = BRepAdaptor_Surface(face)
        if ad.GetType() != GeomAbs_Plane:
            continue
        n = _canon_dir(_unit(_xyz(ad.Plane().Axis().Direction())))
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, g)
        key = tuple(round(v / ANG) for v in n)
        entry = groups.setdefault(key, [0.0, n])
        entry[0] += g.Mass()
    return sorted(((a, n) for a, n in groups.values()), key=lambda t: -t[0])


def _prismatic_frame(shape, faces):
    """Sides (largest first) as (size, direction), the box centre, and how it was measured.

    The frame comes from the part's planar faces: the direction with the most flat area is the
    thickness axis, the next perpendicular one the length axis, and the box is measured exactly
    in that frame. The kernel's "optimal" oriented box is only an approximation (a plate with
    holes came out 0.2 mm long), so it is the fallback for parts without usable flat faces.
    """
    normals = _plane_normals(faces)
    if normals:
        z = normals[0][1]
        x = next((n for _, n in normals[1:] if abs(_dot(n, z)) < ANG), None) or _perpendicular(z)
        y = _cross(z, x)
        lo, hi = _extents_in_frame(shape, (0.0, 0.0, 0.0), z, x)
        local_c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
        centre = _add(_add(_mul(x, local_c[0]), _mul(y, local_c[1])), _mul(z, local_c[2]))
        axes = [(hi[0] - lo[0], x), (hi[1] - lo[1], y), (hi[2] - lo[2], z)]
        how = (
            "exact box in the part's own frame (axes from its flat faces), so a model rotated "
            "in its file is measured true"
        )
    else:
        obb = Bnd_OBB()
        BRepBndLib.AddOBB_s(shape, obb, False, True, False)
        axes = [
            (2 * obb.XHSize(), _unit(_xyz(obb.XDirection()))),
            (2 * obb.YHSize(), _unit(_xyz(obb.YDirection()))),
            (2 * obb.ZHSize(), _unit(_xyz(obb.ZDirection()))),
        ]
        centre = _xyz(obb.Center())
        how = "oriented bounding box (the part has no flat faces to align to; approximate)"
    axes.sort(key=lambda a: -a[0])
    return axes[0], axes[1], axes[2], centre, how


# ----------------------------------------------------------------------------------- features


@dataclass(slots=True)
class CylFeature:
    radius: float
    foot: Vec
    dir: Vec
    hole: bool
    t0: float
    t1: float
    faces: list[int]
    how: set[str]
    full: bool
    through: bool | None = None
    cbore: CylFeature | None = None

    @property
    def diameter(self) -> float:
        return 2 * self.radius

    @property
    def length(self) -> float:
        return self.t1 - self.t0

    def centre(self) -> Vec:
        return _add(self.foot, _mul(self.dir, (self.t0 + self.t1) / 2))

    def segment(self) -> list[float]:
        a = _add(self.foot, _mul(self.dir, self.t0))
        b = _add(self.foot, _mul(self.dir, self.t1))
        return [*a, *b]

    def same_line(self, other: CylFeature) -> bool:
        return _parallel(self.dir, other.dir) and _norm(_sub(self.foot, other.foot)) < EPS


def _merge(cyls: list[Cyl]) -> list[CylFeature]:
    groups: dict[tuple, list[Cyl]] = {}
    for c in cyls:
        key = (
            round(c.radius / EPS),
            c.hole,
            tuple(round(v / ANG) for v in c.dir),
            tuple(round(v / EPS) for v in c.foot),
        )
        groups.setdefault(key, []).append(c)
    out: list[CylFeature] = []
    for members in groups.values():
        members.sort(key=lambda c: c.t0)
        clusters: list[list[Cyl]] = []
        for c in members:
            if clusters and c.t0 <= max(m.t1 for m in clusters[-1]) + EPS:
                clusters[-1].append(c)
            else:
                clusters.append([c])
        for cl in clusters:
            # Faces covering the same span add up their sweep; a full turn is >= 360°.
            sweep = sum(c.sweep for c in cl)
            f = cl[0]
            out.append(
                CylFeature(
                    radius=f.radius,
                    foot=f.foot,
                    dir=f.dir,
                    hole=f.hole,
                    t0=min(c.t0 for c in cl),
                    t1=max(c.t1 for c in cl),
                    faces=[c.face for c in cl],
                    how={c.how for c in cl},
                    full=sweep >= 2 * math.pi - 1e-3,
                )
            )
    return out


def _probe_through(solid, h: CylFeature) -> bool | None:
    """Both ends of the hole open (a probe just past each end, on the axis, is not in material)."""
    if solid is None:
        return None
    delta = max(0.01, 0.02 * h.radius)
    for t in (h.t0 - delta, h.t1 + delta):
        p = _add(h.foot, _mul(h.dir, t))
        cl = BRepClass3d_SolidClassifier(solid, gp_Pnt(*p), 1e-6)
        if cl.State() == TopAbs_IN:
            return False
    return True


def _line_distance(p: Vec, foot: Vec, d: Vec) -> float:
    w = _sub(p, foot)
    return _norm(_sub(w, _mul(d, _dot(w, d))))


def _lines_intersect(a: CylFeature, foot: Vec, d: Vec) -> bool:
    """Does the hole's axis line cross the line (foot, d)? (radial holes)"""
    n = _cross(a.dir, d)
    if _norm(n) < ANG:
        return False
    return abs(_dot(_sub(a.foot, foot), _unit(n))) < EPS


def _confidence(how: set[str], topology: Topology) -> str:
    if "recognised" in how or topology == "open_shell":
        return "inferred"
    return "measured"


def _method_surfaces(how: set[str], n_faces: int) -> str:
    kinds = {
        "native": "cylindrical faces",
        "revolved line": "surfaces of revolution of a line parallel to the axis",
        "recognised": f"B-spline faces recognised as cylinders within {RECOGNITION_TOL:g} mm",
    }
    return (
        f"{n_faces} face{'s' if n_faces != 1 else ''} ({'; '.join(kinds[h] for h in sorted(how))})"
    )


def measure(shape, stem: str, header: ModelHeader, warnings: list[str]) -> Geometry:
    tolerance = min(0.01, max(1e-4, 10 * (header.resolution or 0.0)))
    topology, solids, container, valid = _solidify(shape, tolerance, warnings)
    if topology == "empty":
        raise UnreadableModelError("the file contains no surfaces or curves")
    faces = _faces(container)
    if len(faces) > MAX_FACES:
        raise ModelLimitError(f"the model has {len(faces)} faces; the limit is {MAX_FACES}")
    geo = Geometry(
        topology=topology,
        valid=valid and topology == "solid",
        bodies=len(solids),
        form="unknown",
        features=[],
        faces=faces,
        shape=container,
        solids=solids,
        stem=stem,
    )
    if topology == "wireframe":
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        lo, hi = _xyz(box.CornerMin()), _xyz(box.CornerMax())
        size = sorted((hi[i] - lo[i] for i in range(3)), reverse=True)
        warnings.append(
            "the file holds curves only (no surfaces); only an approximate envelope is reported"
        )
        geo.features.append(
            ModelFeature(
                feature_id="envelope",
                kind="envelope",
                label="Envelope",
                canonical="envelope",
                value=f"{' × '.join(fmt(s, 3) for s in size)} mm (curves only, approximate)",
                numbers={"l_mm": size[0], "w_mm": size[1], "t_mm": size[2]},
                confidence="inferred",
                method="axis-aligned box of the curves in the file's coordinates",
            )
        )
        return geo

    # Surfaces --------------------------------------------------------------------------------
    cyls: list[Cyl] = []
    cones: list[Cone] = []
    tori: list[Torus] = []
    for i, face in enumerate(faces):
        c = _cylinder(i, face)
        if c is not None:
            cyls.append(c)
            continue
        ad = BRepAdaptor_Surface(face)
        if ad.GetType() == GeomAbs_Plane:
            continue
        k = _cone(i, face, ad)
        if k is not None:
            cones.append(k)
            continue
        tr = _torus(i, ad)
        if tr is not None:
            tori.append(tr)
    merged = _merge(cyls)
    full = [f for f in merged if f.full]
    partial = [f for f in merged if not f.full]
    if partial:
        warnings.append(
            f"{len(partial)} partial cylindrical surface{'s' if len(partial) != 1 else ''} "
            "(rounded edges, slots) are not counted as holes or diameters"
        )
    solid = solids[0] if topology == "solid" else None
    main_solid = solids[0] if solids else None

    # Part frame and form -----------------------------------------------------------------------
    bosses = sorted((f for f in full if not f.hole), key=lambda f: -f.radius)
    form: PartForm = "unknown"
    frame_z: Vec = (0.0, 0.0, 1.0)
    frame_x: Vec = (1.0, 0.0, 0.0)
    origin: Vec = (0.0, 0.0, 0.0)
    envelope: ModelFeature | None = None
    target = main_solid if topology != "multi_solid" and main_solid is not None else container
    main = None
    if bosses:
        cand = bosses[0]
        x = _perpendicular(cand.dir)
        lo, hi = _extents_in_frame(target, cand.foot, cand.dir, x)
        sx, sy = hi[0] - lo[0], hi[1] - lo[1]
        if abs(sx - cand.diameter) < 10 * EPS and abs(sy - cand.diameter) < 10 * EPS:
            main = cand
            form = "turned"
            origin = _add(cand.foot, _mul(cand.dir, lo[2]))
            frame_z, frame_x = cand.dir, x
            length = hi[2] - lo[2]
            envelope = ModelFeature(
                feature_id="envelope",
                kind="envelope",
                label="Envelope",
                canonical="envelope",
                value=(
                    f"Ø{fmt(cand.diameter)} × {fmt(length)} mm (diameter × length); "
                    f"bounding box {fmt(cand.diameter)} × {fmt(cand.diameter)} × {fmt(length)} mm"
                ),
                numbers={"diameter_mm": cand.diameter, "length_mm": length},
                method=(
                    "turned part: the largest outer cylinder is the envelope around its axis; "
                    "length "
                    "measured along that axis"
                ),
                faces=list(cand.faces),
                anchor=list(_add(origin, _mul(frame_z, length / 2))),
                axis=list(frame_z),
            )
    if main is None or envelope is None:
        form = "prismatic"
        (L, lx), (W, _wy), (T, tz), c, how = _prismatic_frame(target, faces)
        frame_z, frame_x = _canon_dir(tz), _canon_dir(lx)
        origin = c
        envelope = ModelFeature(
            feature_id="envelope",
            kind="envelope",
            label="Envelope",
            canonical="envelope",
            value=f"{fmt(L)} × {fmt(W)} × {fmt(T)} mm (length × width × thickness)",
            numbers={"l_mm": L, "w_mm": W, "t_mm": T},
            method=how,
            anchor=list(c),
            axis=list(frame_z),
        )
    assert envelope is not None
    if topology == "multi_solid":
        envelope.method += f"; measured on the largest of {len(solids)} bodies"
    if topology == "open_shell":
        envelope.confidence = "inferred"
        envelope.method += "; the surfaces do not close into a solid"
    geo.form = form
    frame_y = _cross(frame_z, frame_x)
    geo.frame = (origin, frame_x, frame_y, frame_z)
    feats: list[ModelFeature] = [envelope]
    if form == "turned":
        feats.append(
            ModelFeature(
                feature_id="length",
                kind="envelope",
                label="Overall length",
                canonical="length",
                value=f"{fmt(envelope.numbers['length_mm'])} mm",
                numbers={"length_mm": envelope.numbers["length_mm"]},
                method="extent of the solid along the turning axis",
                anchor=envelope.anchor,
                axis=envelope.axis,
            )
        )
    else:
        feats.append(
            ModelFeature(
                feature_id="thickness",
                kind="envelope",
                label="Thickness",
                canonical="thickness",
                value=f"{fmt(envelope.numbers['t_mm'])} mm",
                numbers={"thickness_mm": envelope.numbers["t_mm"]},
                method="smallest side of the envelope, measured in the part's own frame",
                anchor=envelope.anchor,
                axis=envelope.axis,
            )
        )

    # Bosses: OD and steps on the main axis -----------------------------------------------------
    face_feature: dict[int, str] = {}
    on_axis = [b for b in bosses if main is not None and b.same_line(main)]
    on_axis.sort(key=lambda b: b.t0)
    step_n = 0
    for b in on_axis:
        is_od = b is main
        if is_od:
            fid, label, canon = "od_1", "Outer diameter", "outer_diameter"
        else:
            step_n += 1
            fid, label, canon = f"step_{step_n}", f"Step {step_n}", "step"
        feats.append(
            ModelFeature(
                feature_id=fid,
                kind="boss",
                label=label,
                canonical=canon,
                value=f"Ø{fmt(b.diameter)} × {fmt(b.length)} long",
                numbers={"diameter_mm": b.diameter, "length_mm": b.length},
                confidence=_confidence(b.how, topology),  # type: ignore[arg-type]
                method=(
                    f"outer cylinder on the turning axis; {_method_surfaces(b.how, len(b.faces))}"
                ),
                faces=b.faces,
                anchor=list(b.centre()),
                axis=list(b.dir),
                segments=[b.segment()],
            )
        )
        for fi in b.faces:
            face_feature[fi] = fid
    other_bosses = [b for b in bosses if b not in on_axis]
    for n, b in enumerate(other_bosses, start=1):
        fid = f"boss_{n}"
        feats.append(
            ModelFeature(
                feature_id=fid,
                kind="boss",
                label=f"Boss {n}",
                canonical="boss",
                value=f"Ø{fmt(b.diameter)} × {fmt(b.length)} long",
                numbers={"diameter_mm": b.diameter, "length_mm": b.length},
                confidence=_confidence(b.how, topology),  # type: ignore[arg-type]
                method=f"outer cylinder off the main axis; {_method_surfaces(b.how, len(b.faces))}",
                faces=b.faces,
                anchor=list(b.centre()),
                axis=list(b.dir),
                segments=[b.segment()],
            )
        )
        for fi in b.faces:
            face_feature[fi] = fid

    # Holes ---------------------------------------------------------------------------------------
    holes = [f for f in full if f.hole]
    for h in holes:
        h.through = _probe_through(solid, h)
    # Counterbores: two holes on one line, touching spans, different radius.
    for a in holes:
        for b in holes:
            if a is b or not a.same_line(b) or b.radius <= a.radius + EPS:
                continue
            touching = abs(b.t1 - a.t0) < EPS or abs(b.t0 - a.t1) < EPS
            if touching and a.cbore is None:
                a.cbore = b
    cbores = {id(h.cbore) for h in holes if h.cbore is not None}
    holes = [h for h in holes if id(h) not in cbores]
    bores = [h for h in holes if main is not None and h.same_line(main)]
    bores.sort(key=lambda h: -h.length)
    for n, h in enumerate(bores, start=1):
        fid = "bore" if n == 1 else f"bore_{n}"
        feats.append(
            _hole_feature(fid, "bore", "Bore" if n == 1 else f"Bore {n}", h, topology, main)
        )
        for fi in h.faces + (h.cbore.faces if h.cbore else []):
            face_feature[fi] = fid
    off = [h for h in holes if h not in bores]
    patterns = _patterns(off, main, full, frame_x, frame_z)
    for n, (members, kind, info) in enumerate(patterns, start=1):
        if len(members) == 1:
            h = members[0]
            fid = f"hole_{n}"
            f = _hole_feature(fid, "hole", f"Hole {n}", h, topology, main)
        else:
            fid = f"hole_pattern_{n}"
            f = _pattern_feature(fid, n, members, kind, info, topology)
        feats.append(f)
        for h in members:
            for fi in h.faces + (h.cbore.faces if h.cbore else []):
                face_feature[fi] = fid
    total = sum(len(m) for m, _, _ in patterns)
    feats.append(
        ModelFeature(
            feature_id="holes",
            kind="hole_pattern",
            label="Holes (excluding the bore)",
            canonical="holes",
            value=_holes_summary(patterns) if total else "none",
            numbers={"count": float(total)},
            method=(
                "full cylindrical holes off the turning axis, after merging split faces"
                if main is not None
                else "full cylindrical holes, after merging split faces"
            ),
        )
    )

    # Chamfers and fillets (informational) --------------------------------------------------------
    groups: dict[tuple, list[Cone]] = {}
    for k in cones:
        groups.setdefault((round(k.length, 3), round(math.degrees(k.half_angle), 2)), []).append(k)
    for n, ((length, angle), ks) in enumerate(sorted(groups.items()), start=1):
        fid = f"chamfer_{n}"
        count = f"{len(ks)} × " if len(ks) > 1 else ""
        feats.append(
            ModelFeature(
                feature_id=fid,
                kind="chamfer",
                label=f"Chamfer {n}",
                canonical="chamfer",
                value=f"{count}chamfer {fmt(length, 3)} mm × {fmt(90 - angle, 2)}°",
                numbers={"count": float(len(ks)), "length_mm": length, "angle_deg": 90 - angle},
                method="conical faces; length along the axis, angle from the axis",
                faces=[k.face for k in ks],
            )
        )
        for k in ks:
            face_feature[k.face] = fid
    radii: dict[float, list[Torus]] = {}
    for t in tori:
        radii.setdefault(round(t.minor, 3), []).append(t)
    for n, (r, ts) in enumerate(sorted(radii.items()), start=1):
        fid = f"fillet_{n}"
        feats.append(
            ModelFeature(
                feature_id=fid,
                kind="fillet",
                label=f"Fillet {n}",
                canonical="fillet",
                value=f"{len(ts)} × R{fmt(r, 3)}" if len(ts) > 1 else f"R{fmt(r, 3)}",
                numbers={"count": float(len(ts)), "radius_mm": r},
                method="toroidal faces (revolved arcs)",
                faces=[t.face for t in ts],
            )
        )
        for t in ts:
            face_feature[t.face] = fid

    # Mass properties ---------------------------------------------------------------------------
    if topology in ("solid", "multi_solid") and solids:
        body = solids[0]
        if geo.valid or topology == "multi_solid":
            g = GProp_GProps()
            BRepGProp.VolumeProperties_s(body, g)
            vol = g.Mass()
            cg = _xyz(g.CentreOfMass())
            ga = GProp_GProps()
            BRepGProp.SurfaceProperties_s(body, ga)
            where = "" if topology == "solid" else f" (largest of {len(solids)} bodies)"
            feats.append(
                ModelFeature(
                    feature_id="volume",
                    kind="body",
                    label="Volume",
                    canonical="volume",
                    value=f"{fmt(vol, 2)} mm³ ({fmt(vol / 1000, 3)} cm³){where}",
                    numbers={"volume_mm3": vol, "volume_cm3": vol / 1000},
                    unit="mm³",
                    method=(
                        "mass properties of the closed, valid solid (exact integration over "
                        "its faces)"
                    ),
                    anchor=list(cg),
                )
            )
            feats.append(
                ModelFeature(
                    feature_id="surface_area",
                    kind="body",
                    label="Surface area",
                    canonical="surface_area",
                    value=f"{fmt(ga.Mass(), 2)} mm²{where}",
                    numbers={"area_mm2": ga.Mass()},
                    unit="mm²",
                    method="surface integral over every face of the solid",
                )
            )
    feats.append(
        ModelFeature(
            feature_id="bodies",
            kind="body",
            label="Bodies",
            canonical="bodies",
            value=_topology_text(topology, len(solids), len(faces), geo.valid),
            numbers={"bodies": float(len(solids)), "faces": float(len(faces))},
            unit=None,
            method=(
                "faces sewn and closed shells turned into solids; validity per the kernel's checker"
            ),
        )
    )
    geo.features = feats
    geo.face_feature = face_feature
    return geo


def _topology_text(topology: Topology, bodies: int, faces: int, valid: bool) -> str:
    if topology == "solid":
        return f"1 closed {'valid ' if valid else ''}solid, {faces} faces"
    if topology == "multi_solid":
        return f"{bodies} separate solids, {faces} faces"
    if topology == "open_shell":
        return f"open surfaces ({faces} faces) that do not close into a solid"
    return "curves only"


def _through_text(h: CylFeature) -> str:
    if h.through is True:
        return " through"
    if h.through is False:
        return f" blind, {fmt(h.length)} deep"
    return ""


def _hole_feature(
    fid: str, kind: str, label: str, h: CylFeature, topology: Topology, main
) -> ModelFeature:
    radial = (
        main is not None
        and not _parallel(h.dir, main.dir)
        and _lines_intersect(h, main.foot, main.dir)
    )
    extra = " radial" if radial else ""
    cb = ""
    nums = {"count": 1.0, "diameter_mm": h.diameter}
    if h.through is False:
        nums["depth_mm"] = h.length
    if h.cbore is not None:
        cb = f", counterbored Ø{fmt(h.cbore.diameter)} × {fmt(h.cbore.length)} deep"
        nums |= {"cbore_diameter_mm": h.cbore.diameter, "cbore_depth_mm": h.cbore.length}
    how = (
        "through: probes past both ends are outside material"
        if h.through
        else (
            "blind: a probe past one end is inside material"
            if h.through is False
            else "through/blind not determinable"
        )
    )
    return ModelFeature(
        feature_id=fid,
        kind=kind,  # type: ignore[arg-type]
        label=label,
        canonical="bore" if kind == "bore" else "hole",
        value=f"Ø{fmt(h.diameter)}{extra}{_through_text(h)}{cb}",
        numbers=nums,
        confidence=_confidence(h.how, topology),  # type: ignore[arg-type]
        method=f"{_method_surfaces(h.how, len(h.faces))}; normals point to the axis; {how}",
        faces=h.faces + (h.cbore.faces if h.cbore else []),
        anchor=list(h.centre()),
        axis=list(h.dir),
        segments=[h.segment()],
    )


def _patterns(holes: list[CylFeature], main, full: list[CylFeature], frame_x: Vec, frame_z: Vec):
    """Group equal parallel holes; classify each group as circular, grid, row or loose."""
    groups: dict[tuple, list[CylFeature]] = {}
    for h in holes:
        key = (round(h.diameter / EPS), tuple(round(v / ANG) for v in h.dir), h.cbore is None)
        groups.setdefault(key, []).append(h)
    out: list[tuple[list[CylFeature], str, dict]] = []
    for members in sorted(groups.values(), key=lambda m: (-len(m), -m[0].diameter)):
        d = members[0].dir
        if len(members) == 1:
            out.append((members, "single", {}))
            continue
        centres = [_sub(h.foot, _mul(d, _dot(h.foot, d))) for h in members]
        # Circular: centred on an axis line parallel to the holes (main axis first).
        axes = [main] if main is not None and _parallel(main.dir, d) else []
        axes += [f for f in full if _parallel(f.dir, d) and f not in members and f not in axes]
        found = None
        if len(members) >= 3:
            for ax in axes:
                dists = [_line_distance(c, ax.foot, ax.dir) for c in centres]
                if min(dists) < 10 * EPS or max(dists) - min(dists) > EPS:
                    continue
                u = _perpendicular(d)
                v = _cross(d, u)
                base = _foot(ax.foot, d)
                angles = sorted(
                    math.atan2(_dot(_sub(c, base), v), _dot(_sub(c, base), u)) % (2 * math.pi)
                    for c in centres
                )
                gaps = [
                    (angles[(i + 1) % len(angles)] - angles[i]) % (2 * math.pi)
                    for i in range(len(angles))
                ]
                if max(gaps) - min(gaps) < 1e-4 * 2 * math.pi:
                    found = {"pcd_mm": 2 * dists[0]}
                    break
        if found:
            out.append((members, "circular", found))
            continue
        # Grid / row in the part frame (projected onto the plane of the holes).
        u = _sub(frame_x, _mul(d, _dot(frame_x, d)))
        u = _unit(u) if _norm(u) > 0.5 else _perpendicular(d)
        v = _cross(d, u)
        coords = [(_dot(c, u), _dot(c, v)) for c in centres]
        xs = _cluster([p[0] for p in coords])
        ys = _cluster([p[1] for p in coords])
        if len(xs) * len(ys) == len(members) and _uniform(xs) and _uniform(ys):
            pitch = {"pitch_x_mm": (xs[-1] - xs[0]) / (len(xs) - 1) if len(xs) > 1 else 0.0}
            pitch["pitch_y_mm"] = (ys[-1] - ys[0]) / (len(ys) - 1) if len(ys) > 1 else 0.0
            kind = "grid" if len(xs) > 1 and len(ys) > 1 else "row"
            out.append((members, kind, pitch | {"nx": float(len(xs)), "ny": float(len(ys))}))
        else:
            out.append((members, "loose", {}))
    return out


def _cluster(values: list[float]) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > EPS:
            out.append(v)
    return out


def _uniform(values: list[float]) -> bool:
    if len(values) < 3:
        return True
    gaps = [b - a for a, b in itertools.pairwise(values)]
    return max(gaps) - min(gaps) < EPS


def _pattern_feature(
    fid: str, n: int, members: list[CylFeature], kind: str, info: dict, topology: Topology
):
    h = members[0]
    through = {m.through for m in members}
    t = _through_text(h) if len(through) == 1 else " (mixed through and blind)"
    cb = f", counterbored Ø{fmt(h.cbore.diameter)} × {fmt(h.cbore.length)}" if h.cbore else ""
    if kind == "circular":
        where = f" on Ø{fmt(info['pcd_mm'])} PCD"
    elif kind == "grid":
        where = (
            f", {int(info['nx'])} × {int(info['ny'])} grid at "
            f"{fmt(info['pitch_x_mm'])} × {fmt(info['pitch_y_mm'])} mm pitch"
        )
    elif kind == "row":
        p = info["pitch_x_mm"] or info["pitch_y_mm"]
        where = f", in a row at {fmt(p)} mm pitch"
    else:
        where = ""
    how = set().union(*(m.how for m in members))
    rule = {
        "circular": "centres equidistant from an axis with equal angular spacing",
        "grid": "centres on a regular lattice in the part frame",
        "row": "centres evenly spaced on a line",
        "loose": "equal holes without a regular arrangement",
    }[kind]
    faces = [fi for m in members for fi in m.faces + (m.cbore.faces if m.cbore else [])]
    return ModelFeature(
        feature_id=fid,
        kind="hole_pattern",
        label=f"Hole pattern {n}",
        canonical="hole_pattern",
        value=f"{len(members)} × Ø{fmt(h.diameter)}{t}{where}{cb}",
        numbers={"count": float(len(members)), "diameter_mm": h.diameter}
        | {k: v for k, v in info.items() if k in ("pcd_mm", "pitch_x_mm", "pitch_y_mm")},
        confidence=_confidence(how, topology),  # type: ignore[arg-type]
        method=(
            f"{len(members)} holes of equal diameter on parallel axes; {rule}; "
            f"{_method_surfaces(how, len(faces))}"
        ),
        faces=faces,
        anchor=list(_mean([m.centre() for m in members])),
        axis=list(h.dir),
        segments=[m.segment() for m in members],
    )


def _mean(pts: list[Vec]) -> Vec:
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def _holes_summary(patterns) -> str:
    parts = []
    for members, _, _ in patterns:
        h = members[0]
        parts.append(f"{len(members)} × Ø{fmt(h.diameter)}")
    return ", ".join(parts)
