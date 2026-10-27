"""Part-number normalisation.

Part numbers are identifiers, never quantities. ``2280`` (numeric cell), ``"2280"`` (text cell),
``2280.0`` and ``" 2280 "`` must all resolve to the same key, while ``"2280-A"`` stays distinct
and is offered as a suggestion for ``2280``.
"""

from __future__ import annotations

import re
import unicodedata

from app.ingestion.cells import RawCell

_WS_RE = re.compile(r"\s+")
_FLOAT_ZERO_RE = re.compile(r"^(\d+)\.0+$")
_BASE_RE = re.compile(r"\d{3,}")
_ID_LIKE_RE = re.compile(r"^[A-Z]{0,4}[-\s/]?\d{3,}[A-Z0-9\-/ .]*$")
MAX_PART_KEY_LEN = 64


def normalize_part_key(value: object) -> str | None:
    """Canonical key for a part number given a cell value or user input."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None  # 2280.5 is not an identifier we can trust
        value = int(value)
    text = str(value)
    text = unicodedata.normalize("NFKC", text).replace(" ", " ")
    text = _WS_RE.sub(" ", text).strip().upper()
    if not text or len(text) > MAX_PART_KEY_LEN:
        return None
    m = _FLOAT_ZERO_RE.match(text)
    if m:
        text = m.group(1)
    return text


def part_key_from_cell(cell: RawCell | None) -> str | None:
    if cell is None or cell.is_empty:
        return None
    if cell.value_type == "number":
        return normalize_part_key(cell.value)
    return normalize_part_key(cell.display_text)


def split_part_key(key: str) -> tuple[str, str | None]:
    """Split a key into base number and affix.

    ``"2280-A"`` -> ``("2280", "A")``; ``"P-2280"`` -> ``("2280", "P")``; ``"2280"`` -> no affix.

    The base is the first run of 3+ digits; whatever surrounds it is the affix.
    """
    m = _BASE_RE.search(key)
    if not m:
        return key, None
    affix = f"{key[: m.start()]} {key[m.end() :]}"
    affix = _WS_RE.sub(" ", affix.replace("-", " ").replace("_", " ").replace("/", " ")).strip()
    return m.group(0), affix or None


def looks_like_part_id(key: str) -> bool:
    return bool(_ID_LIKE_RE.match(key))
