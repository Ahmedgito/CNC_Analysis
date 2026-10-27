"""Dimension callouts in the drawing views, typed by what they say rather than where they are.

``6X Ø10 THRU`` is a hole pattern, ``Ø40 BORE`` a bore, ``Ø90 PCD`` a pitch circle, ``0.375 THK`` a
thickness, ``M6 TAPPED`` a thread, ``Ø48`` a diameter, and a bare ``40`` an unlabelled linear
dimension (kept, but marked ``inferred`` because the number alone does not say what it measures).
Values are never rescaled by the drawing scale: dimensions on a drawing are nominal sizes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.pdf.layout import Segment
from app.services.units import NUM, parse_number

_VIEW_TITLE_RE = re.compile(
    r"^(?:(?:TOP|FRONT|SIDE|END|REAR|BOTTOM|RIGHT|LEFT|ISOMETRIC|AUXILIARY|PLAN)\s+VIEW|"
    r"(?:SECTION|DETAIL|VIEW)\s+[A-Z](?:\s*-\s*[A-Z])?)\b",
    re.IGNORECASE,
)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "hole_pattern",
        re.compile(
            rf"^(?P<count>\d+)\s*[X×]\s*Ø\s*(?P<dia>{NUM})\s*(?P<rest>THRU|THROUGH|DEEP.*|.*HOLES?.*)?$",
            re.IGNORECASE,
        ),
    ),
    (
        "thread",
        re.compile(
            rf"^(?:(?P<count>\d+)\s*[X×]\s*)?M(?P<size>\d+(?:\.\d+)?)(?:\s*[X×]\s*(?P<pitch>{NUM}))?"
            r"\b(?P<rest>.*)$",
            re.IGNORECASE,
        ),
    ),
    ("bore", re.compile(rf"^Ø\s*(?P<value>{NUM})\s*(?P<fit>[A-Z]\d{{1,2}})?\s*BORE\b.*$", re.I)),
    (
        "pitch_circle",
        re.compile(rf"^Ø\s*(?P<value>{NUM})\s*(?:PCD|BCD|P\.C\.D\.?|B\.C\.D?\.?)$", re.I),
    ),
    ("diameter", re.compile(rf"^Ø\s*(?P<value>{NUM})\s*(?P<fit>[A-Z]\d{{1,2}})?$", re.IGNORECASE)),
    ("thickness", re.compile(rf"^(?P<value>{NUM})\s*(?:THK|THICK|THICKNESS)\.?$", re.IGNORECASE)),
    ("radius", re.compile(rf"^R\s*(?P<value>{NUM})$", re.IGNORECASE)),
    (
        "chamfer",
        re.compile(rf"^(?:C\s*(?P<value>{NUM})|(?P<value2>{NUM})\s*[X×]\s*45\s*°?)$", re.I),
    ),
    ("angle", re.compile(rf"^(?P<value>{NUM})\s*°$")),
    ("linear", re.compile(rf"^(?P<value>{NUM})$")),
]
KIND_LABEL = {
    "hole_pattern": "Hole pattern",
    "thread": "Thread",
    "bore": "Bore",
    "pitch_circle": "Pitch circle diameter",
    "diameter": "Diameter",
    "thickness": "Thickness",
    "radius": "Radius",
    "chamfer": "Chamfer",
    "angle": "Angle",
    "linear": "Unlabelled dimension",
}


@dataclass(slots=True)
class Dimension:
    kind: str
    text: str
    bboxes: list[list[float]]
    parsed: dict = field(default_factory=dict)

    @property
    def inferred(self) -> bool:
        return self.kind == "linear"


def is_view_title(text: str) -> bool:
    return bool(_VIEW_TITLE_RE.match(text.strip()))


def parse_callout(text: str) -> tuple[str, dict] | None:
    t = re.sub(r"\s+", " ", text.strip())
    for kind, pattern in _PATTERNS:
        m = pattern.match(t)
        if not m:
            continue
        g = m.groupdict()
        parsed: dict = {}
        if kind == "hole_pattern":
            parsed = {"count": int(g["count"]), "diameter": parse_number(g["dia"])}
            rest = (g.get("rest") or "").upper()
            parsed["through"] = "THRU" in rest or "THROUGH" in rest
        elif kind == "thread":
            rest = (g.get("rest") or "").strip()
            if rest and not re.search(r"TAP|THREAD|HOLE|DEEP|THRU", rest, re.IGNORECASE):
                return None  # "M6" followed by unrelated words is not a thread callout
            parsed = {"size": float(g["size"]), "count": int(g["count"] or 1)}
            if g.get("pitch"):
                parsed["pitch"] = parse_number(g["pitch"])
        else:
            raw = g.get("value") or g.get("value2")
            value = parse_number(raw) if raw else None
            if value is None:
                return None
            parsed = {"value": value}
            if g.get("fit"):
                parsed["fit"] = g["fit"].upper()
        if any(v is None for v in parsed.values()):
            return None
        return kind, parsed
    return None


def find_dimensions(segments: list[Segment]) -> list[Dimension]:
    """Typed callouts from view segments, de-duplicated (one fact per distinct callout)."""
    out: dict[tuple[str, str], Dimension] = {}
    for s in segments:
        text = s.text.strip()
        if not text or is_view_title(text):
            continue
        parsed = parse_callout(text)
        if parsed is None:
            continue
        kind, values = parsed
        key = (kind, re.sub(r"\s+", "", text.upper()))
        if key in out:
            out[key].bboxes.append(s.bbox)
        else:
            out[key] = Dimension(kind, text, [s.bbox], values)
    return list(out.values())
