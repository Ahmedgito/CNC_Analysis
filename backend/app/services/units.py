"""Length, time and surface-finish units shared by the cross-check and the drawing parser.

Kept deliberately small and table-driven: the conversions are exact definitions (25.4 mm per
inch), and the surface-finish equivalences are the conventional N-grade table, which is a
convention rather than an exact conversion and is reported as such.
"""

from __future__ import annotations

import re

MM_PER = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
MIN_PER = {"min": 1.0, "h": 60.0, "s": 1 / 60}

_UNIT_WORDS = {
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "cm": "cm",
    "in": "in",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "″": "in",
    "min": "min",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
}

# Ra (µm) -> conventional RMS/µin and N-grade (ISO 1302 table).
FINISH_TABLE = [
    (0.05, 2, "N2"),
    (0.1, 4, "N3"),
    (0.2, 8, "N4"),
    (0.4, 16, "N5"),
    (0.8, 32, "N6"),
    (1.6, 63, "N7"),
    (3.2, 125, "N8"),
    (6.3, 250, "N9"),
    (12.5, 500, "N10"),
    (25.0, 1000, "N11"),
]

NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)"
_INLINE_UNIT_RE = re.compile(rf"{NUM}\s*(mm|cm|in(?:ch(?:es)?)?|\"|″)(?![a-z])", re.IGNORECASE)


def normalize_unit(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().strip(".").casefold()
    return _UNIT_WORDS.get(t)


def parse_number(text: str) -> float | None:
    """'0.250' -> 0.25, '.010' -> 0.01, '1/2' -> 0.5, '1 1/2' -> 1.5."""
    t = text.strip()
    try:
        if " " in t and "/" in t:
            whole, frac = t.split(None, 1)
            n, d = frac.split("/")
            return float(whole) + float(n) / float(d)
        if "/" in t:
            n, d = t.split("/")
            return float(n) / float(d)
        return float(t)
    except (ValueError, ZeroDivisionError):
        return None


def inline_length_unit(text: str) -> str | None:
    """A length unit written right after a number inside the text: '2.000 x 0.750 in' -> in."""
    m = _INLINE_UNIT_RE.search(text)
    return normalize_unit(m.group(1)) if m else None


def to_mm(value: float, unit: str) -> float:
    return value * MM_PER[unit]


def close(a: float, b: float, rel: float = 0.005, abs_tol: float = 0.05) -> bool:
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))


def fmt(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def finish_equivalent(ra_um: float, rms_uin: float) -> bool:
    """True when an Ra (µm) and an RMS/µin callout are the same grade in the N-grade table."""
    for ra, uin, _ in FINISH_TABLE:
        if close(ra, ra_um, rel=0.02, abs_tol=0.001) and close(uin, rms_uin, rel=0.05, abs_tol=1):
            return True
    return False
