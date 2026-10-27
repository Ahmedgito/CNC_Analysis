# pyright: reportAttributeAccessIssue=false
# (OCP's bundled stubs miss many generated symbols; the kernel modules are covered by tests.)
"""Hidden-line projections of a measured model, as SVG: the 2D views of the model tab.

Exact hidden-line removal (``HLRBRep_Algo``) in the part's own frame, the way a drawing is made:
visible edges solid, hidden edges dashed, centre lines dash-dot. Strokes use ``currentColor`` so
one SVG serves light and dark themes. Every cylindrical feature gets a transparent hit target with
``data-fact-id``, so a click in a projection selects the same fact as a click in the 3D view.

Views (part frame: z = turning axis or thickness direction, x = length):
- turned: front = side elevation with the axis horizontal, right = end view (circles), top = plan
- prismatic: top = plan (holes as circles), front and right = elevations
"""

from __future__ import annotations

import math
from html import escape

from OCP.BRepAdaptor import BRepAdaptor_Curve  # type: ignore[import-not-found]
from OCP.GCPnts import GCPnts_QuasiUniformDeflection  # type: ignore[import-not-found]
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # type: ignore[import-not-found]
from OCP.HLRAlgo import HLRAlgo_Projector  # type: ignore[import-not-found]
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape  # type: ignore[import-not-found]
from OCP.TopAbs import TopAbs_EDGE  # type: ignore[import-not-found]
from OCP.TopExp import TopExp_Explorer  # type: ignore[import-not-found]
from OCP.TopoDS import TopoDS  # type: ignore[import-not-found]

Vec = tuple[float, float, float]
MAX_FACES_EXACT = 3000  # beyond this, exact HLR is too slow; views are skipped with a warning


def _neg(v: Vec) -> Vec:
    return (-v[0], -v[1], -v[2])


def _view_axes(geo) -> dict[str, tuple[Vec, Vec]]:
    """view -> (normal toward the viewer, image x direction)."""
    _origin, x, y, z = geo.frame
    if geo.form == "turned":
        return {"front": (y, z), "right": (z, x), "top": (x, z)}
    return {"top": (z, x), "front": (_neg(y), x), "right": (x, y)}


def _polylines(shape, deflection: float) -> list[list[tuple[float, float]]]:
    out: list[list[tuple[float, float]]] = []
    if shape is None or shape.IsNull():
        return out
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge(ex.Current()))
        disc = GCPnts_QuasiUniformDeflection(curve, deflection)
        if disc.IsDone() and disc.NbPoints() >= 2:
            out.append(
                [(disc.Value(k).X(), disc.Value(k).Y()) for k in range(1, disc.NbPoints() + 1)]
            )
        ex.Next()
    return out


def _path(lines: list[list[tuple[float, float]]]) -> str:
    parts = []
    for pts in lines:
        parts.append("M" + " L".join(f"{x:.3f} {-y:.3f}" for x, y in pts))
    return " ".join(parts)


def _projector(origin: Vec, normal: Vec, xdir: Vec):
    """Image coordinates exactly as HLR emits them: relative to the view origin, x along ``xdir``,
    y along ``normal × xdir`` (gp_Ax2's Y direction). HLRAlgo_Projector.Project() would return
    world-based values, so markers are projected here instead."""
    ydir = (
        normal[1] * xdir[2] - normal[2] * xdir[1],
        normal[2] * xdir[0] - normal[0] * xdir[2],
        normal[0] * xdir[1] - normal[1] * xdir[0],
    )

    def project(p: Vec) -> tuple[float, float]:
        w = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        return (
            w[0] * xdir[0] + w[1] * xdir[1] + w[2] * xdir[2],
            w[0] * ydir[0] + w[1] * ydir[1] + w[2] * ydir[2],
        )

    return project


def build_views(geo) -> dict[str, str]:
    if geo.frame is None or len(geo.faces) > MAX_FACES_EXACT:
        return {}
    from app.geometry.features import _dot  # vector helpers, same package

    origin = geo.frame[0]
    out: dict[str, str] = {}
    for name, (normal, xdir) in _view_axes(geo).items():
        proj = HLRAlgo_Projector(gp_Ax2(gp_Pnt(*origin), gp_Dir(*normal), gp_Dir(*xdir)))
        project = _projector(origin, normal, xdir)
        algo = HLRBRep_Algo()
        algo.Add(geo.shape)
        algo.Projector(proj)
        algo.Update()
        algo.Hide()
        hlr = HLRBRep_HLRToShape(algo)
        visible = _polylines(hlr.VCompound(), 0.05) + _polylines(hlr.OutLineVCompound(), 0.05)
        hidden = _polylines(hlr.HCompound(), 0.05) + _polylines(hlr.OutLineHCompound(), 0.05)
        pts = [p for line in visible + hidden for p in line]
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [-p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
        pad = span * 0.08
        vb = (
            min(xs) - pad,
            min(ys) - pad,
            max(xs) - min(xs) + 2 * pad,
            max(ys) - min(ys) + 2 * pad,
        )
        markers, centres = [], []
        for f in geo.features:
            if not f.segments or f.kind not in ("boss", "bore", "hole", "hole_pattern"):
                continue
            fact = escape(f"{geo.stem}!m!{f.feature_id}")
            r = f.numbers.get("diameter_mm", 0.0) / 2
            for seg in f.segments:
                a, b = tuple(seg[:3]), tuple(seg[3:])
                axis = tuple(b[i] - a[i] for i in range(3))
                length = math.sqrt(_dot(axis, axis)) or 1.0
                along = abs(_dot(axis, normal)) / length
                (ax, ay), (bx, by) = project(a), project(b)
                if along > 0.999:  # axis toward the viewer: a circle
                    cx, cy = ax, -ay
                    markers.append(
                        f'<circle class="feature" data-fact-id="{fact}" '
                        f'cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}"/>'
                    )
                    ext = r * 1.25
                    centres.append(
                        f"M{cx - ext:.3f} {cy:.3f} L{cx + ext:.3f} {cy:.3f} "
                        f"M{cx:.3f} {cy - ext:.3f} L{cx:.3f} {cy + ext:.3f}"
                    )
                elif along < 0.001:  # axis in the view plane: the cylinder's outline
                    dx, dy = bx - ax, -(by - ay)
                    seg_len = math.hypot(dx, dy) or 1.0
                    nx, ny = -dy / seg_len * r, dx / seg_len * r
                    p1 = (ax + nx, -ay + ny)
                    p2 = (bx + nx, -by + ny)
                    p3 = (bx - nx, -by - ny)
                    p4 = (ax - nx, -ay - ny)
                    poly = " ".join(f"{x:.3f},{y:.3f}" for x, y in (p1, p2, p3, p4))
                    markers.append(
                        f'<polygon class="feature" data-fact-id="{fact}" points="{poly}"/>'
                    )
                    ext = min(r, seg_len * 0.1)
                    ux, uy = dx / seg_len * ext, dy / seg_len * ext
                    centres.append(f"M{ax - ux:.3f} {-ay - uy:.3f} L{bx + ux:.3f} {-by + uy:.3f}")
        stroke = span / 400
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{vb[0]:.3f} {vb[1]:.3f} {vb[2]:.3f} {vb[3]:.3f}" '
            f'data-view="{name}" data-units="mm" fill="none" stroke="currentColor" '
            f'stroke-linecap="round" '
            f'stroke-linejoin="round">'
            f"<title>{escape(geo.stem)} · {name} view</title>"
            f'<path class="hidden" d="{_path(hidden)}" stroke-width="{stroke * 0.9:.4f}" '
            f'stroke-dasharray="{stroke * 6:.4f} {stroke * 4:.4f}" opacity="0.5"/>'
            f'<path class="centre" d="{" ".join(centres)}" stroke-width="{stroke * 0.7:.4f}" '
            f'stroke-dasharray="{stroke * 14:.4f} {stroke * 3:.4f} {stroke * 2:.4f} '
            f'{stroke * 3:.4f}" opacity="0.45"/>'
            f'<path class="visible" d="{_path(visible)}" stroke-width="{stroke * 1.6:.4f}"/>'
            f'<g class="features" stroke="transparent" fill="transparent" '
            f'stroke-width="{stroke * 6:.4f}">'
            f"{''.join(markers)}</g></svg>"
        )
        out[name] = svg
    return out
