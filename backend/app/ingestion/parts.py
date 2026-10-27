"""Part-number normalisation and part identity.

Part numbers are identifiers, never quantities. ``2280`` (numeric cell), ``"2280"`` (text cell),
``2280.0`` and ``" 2280 "`` all normalise to the same key, while ``"2280-A"`` stays distinct and
is offered as a suggestion for ``2280``.

Across files one part is often written several ways: a register writes ``P-3001``, an archive
sheet ``3001``, a zero-padded export ``003003``, and the drawing's title block ``3001``. The
*identity key* removes those spellings (a short letter prefix before the number, zero padding)
so every file's facts about one part land in one record. Revision suffixes such as ``-A`` are
kept: ``3004-A`` and ``3004`` stay different identities, and are reconciled only when exactly
one record has that base number (see ``app/repositories/parts.py``).
"""

from __future__ import annotations

import re
import unicodedata

from app.ingestion.cells import RawCell

_WS_RE = re.compile(r"\s+")
_FLOAT_ZERO_RE = re.compile(r"^(\d+)\.0+$")
_BASE_RE = re.compile(r"\d{3,}")
_ID_LIKE_RE = re.compile(r"^[A-Z]{0,4}[-\s/]?\d{3,}[A-Z0-9\-/ .]*$")
# Prefixes that label a number as a part/drawing number rather than being part of it.
_ID_PREFIX_RE = re.compile(r"^(?:P|PN|PT|PART|PART NO|ITEM|DWG|DRG|DRAWING)[-_.:# ]*(?=\d{3})")
_ZERO_PAD_RE = re.compile(r"^0+(?=[1-9]\d{2})")
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


def identity_key(key: str) -> str:
    """The key that every spelling of one part shares.

    ``P-3001`` -> ``3001``; ``003003`` -> ``3003``; ``DWG 2281`` -> ``2281``;
    ``3004-A`` -> ``3004-A`` (revision suffixes are not spellings); ``0042`` -> ``0042``
    (fewer than three significant digits is too short to be sure it is padding).
    """
    k = _ID_PREFIX_RE.sub("", key)
    return _ZERO_PAD_RE.sub("", k) or key


def base_of(key: str) -> str:
    """The base number of a key's identity, used to group spellings and revisions."""
    return split_part_key(identity_key(key))[0]
