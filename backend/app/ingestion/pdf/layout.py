"""Page text layout: words, rotated words, line segments and ruled tables, from pdfplumber.

Everything downstream (title block, notes, dimensions) works on ``Segment``s: runs of words on
one baseline separated by ordinary word spacing. A wide gap ends a segment, which is what keeps a
title-block label ("PART NO") apart from its value ("2280"), and two dimension callouts that
share a baseline ("Ø120" ... "20") apart from each other.

Rotated dimension text is the classic trap: a naive extraction of a 90° label reads ``021Ø`` for
``Ø120``. Non-upright characters are regrouped by their text matrix and read in the direction the
text runs.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

_DIAMETER_EQUIV = str.maketrans({"⌀": "Ø", "∅": "Ø", "ø": "Ø"})
_LINE_TOL = 2.5  # points: words whose tops differ by less share a baseline


def clean(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_DIAMETER_EQUIV).replace(" ", " ")


@dataclass(slots=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    size: float
    upright: bool = True

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(slots=True)
class Segment:
    words: list[Word]
    upright: bool = True

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def size(self) -> float:
        return max(w.size for w in self.words)

    @property
    def bbox(self) -> list[float]:
        return [round(self.x0, 1), round(self.top, 1), round(self.x1, 1), round(self.bottom, 1)]


@dataclass(slots=True)
class TableCell:
    text: str
    bbox: list[float]


@dataclass(slots=True)
class Table:
    bbox: list[float]
    rows: list[list[TableCell | None]]

    def contains(self, w: Word | Segment, pad: float = 1.0) -> bool:
        x0, top, x1, bottom = self.bbox
        cx = (w.x0 + w.x1) / 2
        cy = (w.top + w.bottom) / 2
        return x0 - pad <= cx <= x1 + pad and top - pad <= cy <= bottom + pad


@dataclass(slots=True)
class PageText:
    number: int  # 1-based
    width: float
    height: float
    rotation: int
    words: list[Word]
    tables: list[Table]
    char_count: int
    image_count: int
    image_area_ratio: float  # share of the page covered by raster images
    unmapped_glyphs: int = 0
    upright_chars: int = 0
    correction: int = 0  # clockwise degrees applied so the text reads upright (0, 90, 180, 270)
    segments: list[Segment] = field(default_factory=list)

    @property
    def upright_ratio(self) -> float:
        return self.upright_chars / self.char_count if self.char_count else 1.0

    @property
    def scanned(self) -> bool:
        return self.char_count == 0 and self.image_area_ratio >= 0.5

    @property
    def hybrid(self) -> bool:
        return self.char_count > 0 and self.image_area_ratio >= 0.3


def _upright_words(page: Any) -> list[Word]:
    filtered = page.filter(lambda o: o.get("object_type") != "char" or o.get("upright", True))
    words = filtered.extract_words(
        keep_blank_chars=False, x_tolerance=2, y_tolerance=2, extra_attrs=["size"]
    )
    return [
        Word(clean(w["text"]), w["x0"], w["top"], w["x1"], w["bottom"], float(w["size"]))
        for w in words
        if clean(w["text"]).strip()
    ]


def _rotated_words(page: Any) -> list[Word]:
    """Rebuild vertical text: group non-upright chars by column and reading direction."""
    chars = [c for c in page.chars if not c.get("upright", True) and c["text"].strip()]
    columns: dict[tuple[int, int], list[dict]] = {}
    for c in chars:
        b = c["matrix"][1]
        direction = 1 if b > 0 else -1  # +1: reads bottom-to-top (90° CCW), -1: top-to-bottom
        columns.setdefault((round(c["x0"] / 2), direction), []).append(c)
    words: list[Word] = []
    for (_, direction), cs in columns.items():
        cs.sort(key=lambda c: -c["top"] if direction == 1 else c["top"])
        run: list[dict] = [cs[0]]
        for c in cs[1:]:
            prev = run[-1]
            gap = (prev["top"] - c["bottom"]) if direction == 1 else (c["top"] - prev["bottom"])
            if gap > max(c["size"] * 0.6, 3):
                words.append(_word_from_chars(run))
                run = [c]
            else:
                run.append(c)
        words.append(_word_from_chars(run))
    return words


def _word_from_chars(cs: list[dict]) -> Word:
    return Word(
        text=clean("".join(c["text"] for c in cs)),
        x0=min(c["x0"] for c in cs),
        top=min(c["top"] for c in cs),
        x1=max(c["x1"] for c in cs),
        bottom=max(c["bottom"] for c in cs),
        size=max(float(c["size"]) for c in cs),
        upright=False,
    )


def _tables(page: Any) -> list[Table]:
    out: list[Table] = []
    for t in page.find_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"}):
        texts = t.extract()
        rows: list[list[TableCell | None]] = []
        for r_idx, row in enumerate(t.rows):
            cells: list[TableCell | None] = []
            for c_idx, cell_bbox in enumerate(row.cells):
                text = (
                    texts[r_idx][c_idx]
                    if r_idx < len(texts) and c_idx < len(texts[r_idx])
                    else None
                )
                if cell_bbox is None or text is None:
                    cells.append(None)
                else:
                    cells.append(TableCell(clean(text).strip(), [round(v, 1) for v in cell_bbox]))
            rows.append(cells)
        out.append(Table([round(v, 1) for v in t.bbox], rows))
    return out


def segments(words: list[Word]) -> list[Segment]:
    """Group upright words into baseline runs, split where the gap is wider than word spacing."""
    upright = sorted((w for w in words if w.upright), key=lambda w: (round(w.top), w.x0))
    lines: list[list[Word]] = []
    for w in upright:
        if lines and abs(lines[-1][0].top - w.top) <= _LINE_TOL:
            lines[-1].append(w)
        else:
            lines.append([w])
    out: list[Segment] = []
    for line in lines:
        line.sort(key=lambda w: w.x0)
        current = [line[0]]
        for w in line[1:]:
            gap = w.x0 - current[-1].x1
            if gap > max(1.2 * max(w.size, current[-1].size), 6):
                out.append(Segment(current))
                current = [w]
            else:
                current.append(w)
        out.append(Segment(current))
    out.extend(Segment([w], upright=False) for w in words if not w.upright)
    out.sort(key=lambda s: (round(s.top), s.x0))
    return out


def read_page(page: Any, number: int) -> PageText:
    area = float(page.width * page.height) or 1.0
    image_area = 0.0
    for im in page.images:
        w = max(0.0, min(im["x1"], page.width) - max(im["x0"], 0))
        h = max(0.0, min(im["bottom"], page.height) - max(im["top"], 0))
        image_area += w * h
    chars = page.chars
    unmapped = sum(1 for c in chars if c["text"].startswith("(cid:"))
    words = _upright_words(page) + _rotated_words(page) if chars else []
    text = PageText(
        number=number,
        width=float(page.width),
        height=float(page.height),
        rotation=int(getattr(page, "rotation", 0) or 0) % 360,
        words=words,
        tables=_tables(page) if chars else [],
        char_count=len(chars),
        image_count=len(page.images),
        image_area_ratio=min(1.0, image_area / area),
        unmapped_glyphs=unmapped,
        upright_chars=sum(1 for c in chars if c.get("upright", True) and c["matrix"][0] > 0),
    )
    text.segments = segments(words)
    return text
