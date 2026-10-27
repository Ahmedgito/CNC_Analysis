"""IGES file structure and Global-section header, read as text without the geometry kernel.

An IGES file is fixed 80-column records. Column 73 holds the section letter (S start, G global,
D directory, P parameter, T terminate) and columns 74-80 the sequence number. Detecting the format
from that structure (not the extension) means a renamed file is still recognised and an ``.igs``
holding something else is rejected.

The Global section is a delimited parameter list with Hollerith strings (``13HFilename.iges``).
Field positions follow IGES 5.3, section 2.2.4.
"""

from __future__ import annotations

import re

from app.domain.model import ModelHeader

_SECTIONS = set("SGDPT")
# IGES 5.3 Global parameter 14: units flag.
UNITS_FLAG = {
    1: "in",
    2: "mm",
    4: "ft",
    5: "mi",
    6: "m",
    7: "km",
    8: "mil",
    9: "um",
    10: "cm",
    11: "uin",
}
_UNIT_NAMES = {
    "IN": "in",
    "INCH": "in",
    "MM": "mm",
    "FT": "ft",
    "MI": "mi",
    "M": "m",
    "KM": "km",
    "MIL": "mil",
    "UM": "um",
    "MICRON": "um",
    "CM": "cm",
    "UIN": "uin",
}
MM_PER_UNIT = {
    "mm": 1.0,
    "in": 25.4,
    "ft": 304.8,
    "mi": 1_609_344.0,
    "m": 1000.0,
    "km": 1_000_000.0,
    "mil": 0.0254,
    "um": 0.001,
    "cm": 10.0,
    "uin": 0.0000254,
}


class NotIgesError(ValueError):
    pass


def _records(data: bytes) -> list[str]:
    text = data.decode("latin-1")
    return [line for line in text.splitlines() if line.strip()]


def looks_like_iges(data: bytes) -> bool:
    """True for ASCII IGES: 80-column records whose column 73 is a section letter, starting with
    the Start or Global section. Checks only the first lines, so it is cheap on large files."""
    head = data[:8192]
    if b"\x00" in head:
        return False
    lines = [ln for ln in head.decode("latin-1").splitlines() if ln.strip()][:8]
    if len(lines) < 2:
        return False
    flagged = [ln for ln in lines if len(ln) >= 73 and ln[72] in _SECTIONS]
    return len(flagged) >= max(2, len(lines) - 1) and flagged[0][72] in "SG"


def section_counts(data: bytes) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in _records(data):
        if len(line) >= 73 and line[72] in _SECTIONS:
            counts[line[72]] = counts.get(line[72], 0) + 1
    return counts


def _section(lines: list[str], letter: str) -> str:
    return "".join(ln[:72] for ln in lines if len(ln) >= 73 and ln[72] == letter)


def parse_global(text: str) -> list[str | None]:
    """Split a Global section into its parameters (1-based list, index 0 unused).

    Parameter and record delimiters default to ``,`` and ``;`` and may themselves be redefined in
    the first two fields as ``1Hx``. Hollerith strings ``nH...`` may contain the delimiters.
    """
    pd, rd = ",", ";"
    i = 0
    # Fields 1 and 2 can redefine the delimiters.
    for idx in (1, 2):
        m = re.match(r"1H(.)", text[i:])
        if m:
            if idx == 1:
                pd = m.group(1)
            else:
                rd = m.group(1)
            i += 3
        if i < len(text) and text[i] in (pd, ",", rd):
            i += 1
    fields: list[str | None] = [None, pd, rd]
    while i < len(text):
        if text[i] == rd:
            break
        m = re.match(r"\s*(\d+)H", text[i:])
        if m:
            n = int(m.group(1))
            start = i + m.end()
            fields.append(text[start : start + n])
            i = start + n
        else:
            j = i
            while j < len(text) and text[j] not in (pd, rd):
                j += 1
            raw = text[i:j].strip()
            fields.append(raw or None)
            i = j
        if i < len(text) and text[i] == pd:
            i += 1
    return fields


def _float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def _int(v: str | None) -> int | None:
    f = _float(v)
    return int(f) if f is not None and f.is_integer() else None


def read_header(data: bytes) -> ModelHeader:
    if not looks_like_iges(data):
        raise NotIgesError("not an ASCII IGES file (no S/G/D/P/T records in column 73)")
    lines = _records(data)
    g = parse_global(_section(lines, "G"))

    def field(n: int) -> str | None:
        return g[n] if n < len(g) else None

    flag = _int(field(14))
    name = (field(15) or "").strip().upper() or None
    units = None
    declared = True
    if flag in UNITS_FLAG:
        units = UNITS_FLAG[flag]
    elif flag == 3 and name:
        units = _UNIT_NAMES.get(name.replace(".", ""))
    elif name and name.replace(".", "") in _UNIT_NAMES:
        units = _UNIT_NAMES[name.replace(".", "")]
    if units is None:
        units, declared = "in", False  # IGES 5.3: inches when no unit is given
    scale = _float(field(13)) or 1.0
    start = " ".join(ln[:72].strip() for ln in lines if len(ln) >= 73 and ln[72] == "S").strip()
    return ModelHeader(
        sending_system=field(5) or field(6),
        product_id=field(3),
        file_name=field(4),
        units_flag=flag,
        units_name=name,
        units=units,
        units_declared=declared,
        model_scale=scale if scale > 0 else 1.0,
        resolution=_float(field(19)),
        created=field(18),
        author=field(21),
        organization=field(22),
        start_text=start[:500] or None,
    )


def entity_count(data: bytes) -> int:
    """Directory entries are two D records each."""
    return section_counts(data).get("D", 0) // 2
