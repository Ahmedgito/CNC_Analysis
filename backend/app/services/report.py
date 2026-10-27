"""The part report: everything the app knows about one part, as a PDF a person can file or send.

The report is built from the same ``PartRecord`` the API serves, so it never states anything the
app would not: every value carries the file and the exact place it came from (a cell, a drawing
region, a measured feature), the cross-check verdicts are the deterministic ones, and questions
asked in a conversation appear with the evidence that was verified for them.

Fonts are the PDF standard fonts, so the report renders the same on Windows, Linux and in the
container; text is mapped to their character set first (``_clean``).
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.answer import AskResult
from app.domain.drawing import REGION_LABEL, CrossCheck, DrawingSlice
from app.domain.evidence import Fact
from app.domain.model import ModelSlice
from app.domain.record import PartRecord, SheetSlice
from app.services.file_store import FileStore

Row = Sequence[Flowable | str]  # one table row: cells are paragraphs or plain text

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
WIDTH = PAGE_W - 2 * MARGIN
MAX_DRAWING_PAGES = 6  # per drawing; the rest are listed, not pictured
PAGE_DPI = 100

INK = colors.HexColor("#18181b")
MUTED = colors.HexColor("#71717a")
RULE = colors.HexColor("#e4e4e7")
ZEBRA = colors.HexColor("#fafafa")
HEAD_BG = colors.HexColor("#f4f4f5")
ACCENT = colors.HexColor("#0891b2")
BOX = colors.HexColor("#e11d48")

SOURCE_LABEL = {"excel": "Spreadsheet", "pdf": "Drawing", "iges": "3D model"}
SOURCE_NOUN = {"excel": "spreadsheet", "pdf": "drawing", "iges": "3D model"}
VERDICT_LABEL = {
    "agree": "Agree",
    "agree_after_conversion": "Agree after unit conversion",
    "equivalent_by_convention": "Equivalent by convention",
    "consistent": "Fits the stock",
    "within_tolerance": "Within tolerance, check",
    "not_modelled": "Not modelled",
    "disagree": "Disagree",
    "excel_only": "Spreadsheet only",
    "pdf_only": "Drawing only",
    "iges_only": "Model only",
    "not_comparable": "Not comparable",
}
VERDICT_MEANING = {
    "agree": "The sources state the same value.",
    "agree_after_conversion": "The same value once units are converted (for example inch to mm).",
    "equivalent_by_convention": "Different notation for the same requirement (for example Ra/RMS).",
    "consistent": "The finished part fits inside the stated raw stock.",
    "within_tolerance": "Values differ, but by less than the stated tolerance. Worth a look.",
    "not_modelled": "The drawing calls for a feature 3D models often omit (chamfers).",
    "disagree": "The sources state different values. Resolve before machining.",
    "excel_only": "Only the spreadsheet states this field.",
    "pdf_only": "Only the drawing states this field.",
    "iges_only": "Only the 3D model shows this field.",
    "not_comparable": "Stated in a way that cannot be compared safely (an ambiguous unit).",
}
VERDICT_COLOR = {
    "agree": "#047857",
    "agree_after_conversion": "#0f766e",
    "equivalent_by_convention": "#0369a1",
    "consistent": "#047857",
    "within_tolerance": "#b45309",
    "not_modelled": "#52525b",
    "disagree": "#be123c",
    "excel_only": "#52525b",
    "pdf_only": "#52525b",
    "iges_only": "#52525b",
    "not_comparable": "#b45309",
}
_ORDER = [  # disagreements first, then what needs a reader's judgement, then agreements
    "disagree",
    "within_tolerance",
    "not_comparable",
    "not_modelled",
    "agree_after_conversion",
    "equivalent_by_convention",
    "consistent",
    "agree",
    "excel_only",
    "pdf_only",
    "iges_only",
]
NEEDS_LOOK = {"within_tolerance", "not_comparable", "not_modelled"}
AGREE = {"agree", "agree_after_conversion", "equivalent_by_convention", "consistent"}
CONFIDENCE_MEANING = {
    "exact": "The text is in the file verbatim.",
    "inferred": "Derived by a rule from text in the file (a SEE NOTE pointer, an unlabelled "
    "dimension).",
    "vision": "Read from a scanned image by a vision model, with the user's consent. Not "
    "verifiable against a text layer.",
    "measured": "Computed by the app from the 3D model's geometry; exact to the model, not text.",
}
STATUS_LABEL = {
    "answered": "Answered from the files",
    "computed": "Computed from the files",
    "not_found": "Not found in the files",
    "clarify": "Needs clarification",
    "needs_consent": "Needs consent to read a scan",
    "blocked": "Declined",
    "part_not_found": "Part not found",
    "invalid_question": "Invalid question",
    "error": "No model could answer",
}

# The standard fonts cover Windows-1252; these are the characters the files and the app use
# outside it.
_REPLACE = str.maketrans(
    {
        "⌀": "Ø",  # diameter sign
        "∅": "Ø",
        "−": "-",
        "‐": "-",
        "‑": "-",
        "→": "->",
        "←": "<-",
        "↔": "<->",
        "≈": "~",
        "≤": "<=",
        "≥": ">=",
        "≠": "!=",
        "∞": "inf",
        "✓": "yes",
        "✗": "no",
        " ": " ",
        " ": " ",
        " ": " ",
        "μ": "µ",
        "″": '"',
        "′": "'",
        "〈": "<",
        "〉": ">",
    }
)


def _clean(value: object) -> str:
    text = str(value).translate(_REPLACE)
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _t(value: object) -> str:
    """Text for a Paragraph: mapped to the font's characters and XML-escaped."""
    return escape(_clean(value))


# -- styles ------------------------------------------------------------------------------------

_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
S = {
    "body": _BASE,
    "small": ParagraphStyle("small", parent=_BASE, fontSize=7.5, leading=9.5),
    "muted": ParagraphStyle("muted", parent=_BASE, fontSize=8, leading=10.5, textColor=MUTED),
    "cell": ParagraphStyle("cell", parent=_BASE, fontSize=7.5, leading=9.2),
    "cellb": ParagraphStyle(
        "cellb", parent=_BASE, fontName="Helvetica-Bold", fontSize=7.5, leading=9.2
    ),
    "mono": ParagraphStyle("mono", parent=_BASE, fontName="Courier", fontSize=7, leading=8.8),
    "kicker": ParagraphStyle(
        "kicker",
        parent=_BASE,
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=ACCENT,
        spaceAfter=2,
    ),
    "title": ParagraphStyle(
        "title", parent=_BASE, fontName="Helvetica-Bold", fontSize=24, leading=28
    ),
    "subtitle": ParagraphStyle("subtitle", parent=_BASE, fontSize=13, leading=17, textColor=MUTED),
    "h1": ParagraphStyle(
        "h1",
        parent=_BASE,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceBefore=6,
        spaceAfter=6,
    ),
    "h2": ParagraphStyle(
        "h2",
        parent=_BASE,
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
    ),
    "h3": ParagraphStyle(
        "h3",
        parent=_BASE,
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        spaceBefore=6,
        spaceAfter=3,
        textColor=colors.HexColor("#3f3f46"),
    ),
    "stat": ParagraphStyle(
        "stat",
        parent=_BASE,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        alignment=TA_CENTER,
    ),
    "statlabel": ParagraphStyle(
        "statlabel", parent=_BASE, fontSize=7.5, leading=9, textColor=MUTED, alignment=TA_CENTER
    ),
}


def _p(text: str, style: str = "body") -> Paragraph:
    """A paragraph from markup that is already escaped (use ``_t`` on any data first)."""
    return Paragraph(text, S[style])


def _c(value: object, style: str = "cell") -> Paragraph:
    return Paragraph(_t(value) if value not in (None, "") else "-", S[style])


def _markdown(text: str) -> str:
    """The little markdown answers use (``**bold**``, ``- `` bullets) as Paragraph markup."""
    out = _t(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?m)^\s*[-*] ", "• ", out)
    return out.replace("\n", "<br/>")


def _verdict(verdict: str, style: str = "cellb") -> Paragraph:
    return Paragraph(
        f'<font color="{VERDICT_COLOR.get(verdict, "#52525b")}">'
        f"{_t(VERDICT_LABEL.get(verdict, verdict))}</font>",
        S[style],
    )


def _table(
    rows: Sequence[Row],
    widths: Sequence[float],
    header: bool = True,
    extra: Sequence[tuple] = (),
) -> Table:
    """A ruled table; ``widths`` are fractions of the text width."""
    total = sum(widths)
    table = Table(
        [list(r) for r in rows],
        colWidths=[WIDTH * w / total for w in widths],
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )
    style: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#d4d4d8")),
        ]
    style += list(extra)
    table.setStyle(TableStyle(style))
    return table


def _kv(pairs: Sequence[tuple[str, object]]) -> Table:
    rows = [[_c(k, "cellb"), _c(v)] for k, v in pairs if v not in (None, "", [])]
    return _table(rows, [1, 3.2], header=False)


def _head(*labels: str) -> list[Flowable | str]:
    return [_c(label, "cellb") for label in labels]


# -- flowables ---------------------------------------------------------------------------------


class _DrawingPage(Flowable):
    """A rendered drawing page with a numbered box on every fact read from it."""

    def __init__(
        self,
        png: bytes,
        width_pt: float,
        height_pt: float,
        boxes: Sequence[tuple[int, list[float]]],
        max_h: float,
    ) -> None:
        super().__init__()
        self.image = ImageReader(io.BytesIO(png))
        iw, ih = self.image.getSize()
        scale = min(WIDTH / iw, max_h / ih)
        self.w, self.h = iw * scale, ih * scale
        self.page_w, self.page_h = width_pt or 1, height_pt or 1
        self.boxes = boxes

    def wrap(self, aW: float, aH: float) -> tuple[float, float]:
        return self.w, self.h

    def draw(self) -> None:
        c = self.canv
        c.drawImage(self.image, 0, 0, self.w, self.h)
        c.setStrokeColor(RULE)
        c.rect(0, 0, self.w, self.h, stroke=1, fill=0)
        sx, sy = self.w / self.page_w, self.h / self.page_h
        # Facts read from one printed string ("SK / C": drawn by and revision) share a box.
        merged: dict[tuple[float, ...], list[str]] = {}
        for number, b in self.boxes:
            merged.setdefault(tuple(round(v, 1) for v in b), []).append(str(number))
        for (x0, y0, x1, y1), numbers in merged.items():
            # Boxes are PDF points with a top-left origin; the canvas origin is bottom-left.
            bx, by = x0 * sx - 1, self.h - y1 * sy - 1
            bh = (y1 - y0) * sy + 2
            c.setStrokeColor(BOX)
            c.setLineWidth(0.6)
            c.rect(bx, by, (x1 - x0) * sx + 2, bh, stroke=1, fill=0)
            # The number sits just left of the box, so it never covers the text it marks.
            label = ",".join(numbers)
            tw = c.stringWidth(label, "Helvetica-Bold", 5) + 2.5
            tx, ty = max(bx - tw, 0), by + bh / 2 - 3
            c.setFillColor(BOX)
            c.rect(tx, ty, tw, 6, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 5)
            c.drawString(tx + 1.25, ty + 1.6, label)


_PATH_RE = re.compile(r'<path class="(\w+)" d="([^"]*)"')
_VIEWBOX_RE = re.compile(r'viewBox="([-\d.\s]+)"')
_POINT_RE = re.compile(r"(-?[\d.]+) (-?[\d.]+)")
_LINE_STYLE = {  # stroke width (pt), dash, colour
    "visible": (0.8, None, INK),
    "hidden": (0.35, (2, 1.5), colors.HexColor("#a1a1aa")),
    "centre": (0.3, (5, 1.2, 1, 1.2), ACCENT),
}


class _Projections(Flowable):
    """The model's hidden-line views side by side, drawn from the SVGs the worker made."""

    def __init__(self, views: Sequence[tuple[str, bytes]], height: float = 46 * mm) -> None:
        super().__init__()
        self.views = [(name, *self._parse(svg)) for name, svg in views]
        self.h = height

    @staticmethod
    def _parse(svg: bytes) -> tuple[list[float], list[tuple[str, list[list[tuple[float, float]]]]]]:
        """The viewBox and, per line class, polylines (``M x y L x y L x y ...``)."""
        text = svg.decode("utf-8", errors="replace")
        vb = _VIEWBOX_RE.search(text)
        box = [float(v) for v in vb.group(1).split()] if vb else [0.0, 0.0, 1.0, 1.0]
        paths = [
            (
                cls,
                [
                    [(float(x), float(y)) for x, y in _POINT_RE.findall(run)]
                    for run in d.split("M")
                    if run.strip()
                ],
            )
            for cls, d in _PATH_RE.findall(text)
        ]
        return box, paths

    def wrap(self, aW: float, aH: float) -> tuple[float, float]:
        return WIDTH, self.h

    def draw(self) -> None:
        c = self.canv
        n = max(len(self.views), 1)
        gap = 4 * mm
        cell_w = (WIDTH - gap * (n - 1)) / n
        label_h = 10
        for i, (name, (vx, vy, vw, vh), paths) in enumerate(self.views):
            ox = i * (cell_w + gap)
            c.setStrokeColor(RULE)
            c.setLineWidth(0.5)
            c.setDash()
            c.rect(ox, 0, cell_w, self.h, stroke=1, fill=0)
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(ox + 4, self.h - 9, f"{name.title()} view")
            pad = 6
            avail_w, avail_h = cell_w - 2 * pad, self.h - 2 * pad - label_h
            scale = min(avail_w / (vw or 1), avail_h / (vh or 1))
            # Centre the view; SVG y grows downward, so flip it.
            x0 = ox + pad + (avail_w - vw * scale) / 2
            y0 = pad + (avail_h - vh * scale) / 2
            for cls in ("hidden", "centre", "visible"):
                width, dash, colour = _LINE_STYLE[cls]
                c.setLineWidth(width)
                c.setStrokeColor(colour)
                c.setDash(list(dash) if dash else [])
                for k, polylines in paths:
                    if k != cls:
                        continue
                    for pts in polylines:
                        if len(pts) < 2:
                            continue
                        path = c.beginPath()
                        for j, (px, py) in enumerate(pts):
                            point = (x0 + (px - vx) * scale, y0 + (vy + vh - py) * scale)
                            path.moveTo(*point) if j == 0 else path.lineTo(*point)
                        c.drawPath(path, stroke=1, fill=0)
        c.setDash()


class _NumberedCanvas(Canvas):
    """Draws the running footer once the page count is known ("Page 3 of 9")."""

    footer = ""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self) -> None:  # reportlab API name
        self._pages.append(dict(self.__dict__))
        self._startPage()  # type: ignore[attr-defined]  # reportlab internal

    def save(self) -> None:
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(MUTED)
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
            self.drawString(MARGIN, 7.5 * mm, _clean(self.footer))
            self.drawRightString(
                PAGE_W - MARGIN, 7.5 * mm, f"Page {self.getPageNumber()} of {total}"
            )
            super().showPage()
        super().save()


# -- sections ----------------------------------------------------------------------------------


def _where(fact: Fact | None, fact_id: str) -> str:
    return f"{fact.file} › {fact.locator}" if fact else fact_id


def _sorted_checks(checks: Sequence[CrossCheck]) -> list[CrossCheck]:
    return sorted(checks, key=lambda c: _ORDER.index(c.verdict) if c.verdict in _ORDER else 99)


def _side(check: CrossCheck, source: str) -> Paragraph:
    """One source's statement, as the UI shows it: the value as written, then normalised."""
    side = next((s for s in check.sides if s.source == source), None)
    legacy = {"excel": check.excel_value, "pdf": check.pdf_value, "iges": check.iges_value}
    value = side.value if side else legacy[source]
    if value is None:
        return _p(f"<i>{_t(side.note if side and side.note else 'not stated')}</i>", "muted")
    text = _t(value)
    # A normalised value with no number in it adds nothing ("mm"), so it is not shown.
    if side and side.normalised and side.normalised != value and re.search(r"\d", side.normalised):
        text += f'<br/><font color="#71717a">= {_t(side.normalised.strip())}</font>'
    ids = set(side.facts) if side else set()
    if check.odd_one_out == source or ids & set(check.dissent):
        label = "odd one out" if check.odd_one_out == source else "differs"
        text += f'<br/><font color="#be123c"><b>{label}</b></font>'
    return Paragraph(text, S["cell"])


def _summary(
    record: PartRecord, related: Sequence[str], answers: Sequence[AskResult], generated: datetime
) -> list[Flowable]:
    out: list[Flowable] = [
        _p("PART REPORT", "kicker"),
        _p(f"Part {_t(record.display_part_number)}", "title"),
    ]
    if desc := record.description():
        out.append(_p(_t(desc), "subtitle"))
    out.append(Spacer(1, 4))
    meta = [f"Generated {_t(generated.strftime('%Y-%m-%d %H:%M UTC'))}"]
    aliases = [a for a in record.aliases if a != record.display_part_number]
    if aliases:
        meta.append(f"Also written as {_t(', '.join(aliases))}")
    if related:
        meta.append(f"Related part numbers {_t(', '.join(related))}")
    out.append(_p(" · ".join(meta), "muted"))
    out.append(Spacer(1, 10))

    checks = record.cross_checks
    disagree = [c for c in checks if c.verdict == "disagree"]
    review = [c for c in checks if c.verdict in NEEDS_LOOK]
    agree = [c for c in checks if c.verdict in AGREE]
    files = {k: len(v.files) for k, v in record.sources.items()}
    stats = [
        (str(files.get("excel", 0)), "spreadsheet files", INK),
        (str(files.get("pdf", 0)), "drawings", INK),
        (str(files.get("iges", 0)), "3D models", INK),
        (str(len(agree)), "fields agree", colors.HexColor("#047857")),
        (str(len(review)), "need a look", colors.HexColor("#b45309")),
        (str(len(disagree)), "disagree", colors.HexColor("#be123c")),
    ]
    tiles = Table(
        [
            [
                Paragraph(f'<font color="#{c.hexval()[2:]}">{v}</font>', S["stat"])
                for v, _, c in stats
            ],
            [_p(_t(label), "statlabel") for _, label, _ in stats],
        ],
        colWidths=[WIDTH / len(stats)] * len(stats),
    )
    tiles.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("LINEAFTER", (0, 0), (-2, -1), 0.5, RULE),
                ("BACKGROUND", (0, 0), (-1, -1), ZEBRA),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    out += [tiles, Spacer(1, 12), _p("Key findings", "h2")]

    findings: list[str] = []
    for c in disagree:
        odd = f" The {SOURCE_NOUN[c.odd_one_out]} is the odd one out." if c.odd_one_out else ""
        findings.append(
            f'<font color="#be123c"><b>{_t(c.label)} disagrees.</b></font> {_t(c.detail)}{_t(odd)}'
        )
    for c in review:
        findings.append(
            f'<font color="#b45309"><b>{_t(c.label)}: '
            f"{_t(VERDICT_LABEL[c.verdict].lower())}.</b></font> {_t(c.detail)}"
        )
    for f in record.unread_scans():
        findings.append(
            f"<b>{_t(f)}</b> is a scanned drawing that has not been read. Its values "
            "are not in this report; read it in the app (it asks for consent first)."
        )
    for status_kind, status in record.sources.items():
        if not status.available:
            findings.append(
                f"No {SOURCE_NOUN[status_kind]} for this part"
                + (f": {_t(status.note)}" if status.note else ".")
            )
    if agree and not disagree:
        findings.append(
            f"All {len(agree)} compared fields agree across the sources that state them."
        )
    if answers:
        findings.append(
            f"{len(answers)} question(s) asked in this session are included at the "
            "end, each with its verified sources."
        )
    out += [_p(f"• {f}", "body") for f in findings] or [_p("Nothing to flag.", "muted")]
    if record.warnings:
        out += [_p("Ingestion warnings", "h3")]
        out += [_p(f"• {_t(w)}", "small") for w in record.warnings]
    return out


def _sources(record: PartRecord) -> list[Flowable]:
    out: list[Flowable] = [
        _p("1. Sources", "h1"),
        _p(
            "Every file the app read for this part. Values in this report "
            "name the file and the exact place they came from.",
            "muted",
        ),
        Spacer(1, 4),
    ]
    rows: list[Row] = [_head("Source", "Status", "Files", "Revision", "Notes")]
    for kind in ("excel", "pdf", "iges"):
        st = record.sources.get(kind)  # type: ignore[call-overload]
        if st is None:
            continue
        status = "Available" if st.available else "Not available"
        if kind == "pdf" and st.readable is False:
            status += " (scan, not read)"
        if kind == "iges" and st.valid is not None:
            status += " (valid solid)" if st.valid else " (not one valid solid)"
        notes = [st.note] if st.note else []
        if st.scanned:
            notes.append("Scanned: " + ", ".join(st.scanned))
        rows.append(
            [
                _c(SOURCE_LABEL[kind], "cellb"),
                _c(status),
                _c(", ".join(st.files)),
                _c(st.current_revision),
                _c(" ".join(notes)),
            ]
        )
    out.append(_table(rows, [1.1, 1.3, 2.4, 0.8, 2]))

    inventory: list[Row] = [_head("File", "Kind", "Content hash (SHA-256)")]
    sheets_by_file: dict[str, list[str]] = {}
    for s in record.sheets:
        sheets_by_file.setdefault(s.file, []).append(s.sheet)
    for f, names in sheets_by_file.items():
        inventory.append([_c(f), _c(f"Spreadsheet: {', '.join(dict.fromkeys(names))}"), _c("-")])
    for d in record.drawings:
        inventory.append([_c(d.file), _c(f"Drawing, {d.page_count} page(s)"), _c(d.sha256, "mono")])
    for m in record.models:
        inventory.append(
            [_c(m.file), _c(f"IGES model, {m.topology.replace('_', ' ')}"), _c(m.sha256, "mono")]
        )
    out += [_p("File inventory", "h3"), _table(inventory, [2, 1.8, 3.4])]
    return out


def _cross_checks(record: PartRecord, facts: dict[str, Fact]) -> list[Flowable]:
    out: list[Flowable] = [
        _p("2. Cross-check: spreadsheet, drawing and 3D model", "h1"),
        _p(
            "The same field compared across every source that states it, after unit "
            "reconciliation. Verdicts are computed in code, never by a language model. "
            "Disagreements are listed first.",
            "muted",
        ),
        Spacer(1, 4),
    ]
    if not record.cross_checks:
        return [
            *out,
            _p("No field is stated by more than one source, so nothing could be compared.", "body"),
        ]
    rows: list[Row] = [_head("Field", "Verdict", "Spreadsheet", "Drawing", "3D model")]
    extra: list[tuple] = []
    for c in _sorted_checks(record.cross_checks):
        r = len(rows)
        rows.append(
            [
                _c(c.label, "cellb"),
                _verdict(c.verdict),
                _side(c, "excel"),
                _side(c, "pdf"),
                _side(c, "iges"),
            ]
        )
        lines = [_t(c.detail)]
        if c.pairs:
            pairs = "; ".join(
                f"{SOURCE_LABEL[a]} vs {SOURCE_NOUN[b]}: {VERDICT_LABEL.get(v, v).lower()}"
                for k, v in c.pairs.items()
                for a, b in [k.split("~")]
            )
            lines.append(f"<i>{_t(pairs)}</i>")
        if c.odd_one_out:
            lines.append(f"<b>Odd one out:</b> {_t(SOURCE_LABEL[c.odd_one_out])}")
        for kind, ids in (("excel", c.excel), ("pdf", c.pdf), ("iges", c.iges)):
            if ids:
                where = "; ".join(_where(facts.get(i), i) for i in ids)
                lines.append(f"<b>{SOURCE_LABEL[kind]} source:</b> {_t(where)}")
        rows.append(["", _p("<br/>".join(lines), "small"), "", "", ""])
        extra += [
            ("SPAN", (1, r + 1), (4, r + 1)),
            ("LINEBELOW", (0, r), (-1, r), 0, colors.white),
            ("TOPPADDING", (0, r + 1), (-1, r + 1), 0),
            ("LINEBEFORE", (0, r), (0, r + 1), 2, colors.HexColor(VERDICT_COLOR[c.verdict])),
        ]
    out.append(_table(rows, [1.3, 1.3, 1.6, 1.6, 1.6], extra=extra))
    return out


def _header(header: str, unit: str | None) -> str:
    """A column header with its unit, unless the header already says it ("Bore (mm)")."""
    return f"{header} ({unit})" if unit and f"({unit.lower()}" not in header.lower() else header


def _sheet(s: SheetSlice) -> list[Flowable]:
    flags = [s.kind, s.layout] + (["hidden sheet"] if s.hidden else [])
    if s.default_unit:
        flags.append(f"default unit {s.default_unit}")
    title = f"{_t(s.file)} › {_t(s.sheet)}"
    out: list[Flowable] = [_p(title, "h2"), _p(_t(" · ".join(flags)), "muted")]
    if s.stale:
        out.append(
            _p(
                f'<font color="#b45309">History: {_t(s.stale_reason or "archived")}. '
                "Not the current values.</font>",
                "small",
            )
        )
    if s.banner:
        out.append(
            _p(
                "Sheet banner: " + _t("; ".join(f"{b.value} ({b.col}{b.row})" for b in s.banner)),
                "small",
            )
        )
    out.append(Spacer(1, 3))
    used = [col for col in s.columns if any(c.col == col.col for r in s.rows for c in r.cells)]
    if s.kind == "rows" and 0 < len(used) <= 7 and len(s.rows) > 1:
        # A table of rows (operations, revisions) reads best as the grid it is in the file.
        rows: list[Row] = [_head("Row", *[_header(c.header, c.unit) for c in used])]
        extra: list[tuple] = []
        for r in s.rows:
            by_col = {c.col: c for c in r.cells}
            rows.append(
                [_c(r.row)] + [_c(by_col[c.col].value if c.col in by_col else None) for c in used]
            )
            if r.stale:
                extra.append(("TEXTCOLOR", (0, len(rows) - 1), (-1, len(rows) - 1), MUTED))
        out.append(_table(rows, [0.9] + [2] * len(used), extra=extra))
        stale = [r for r in s.rows if r.stale]
        if stale:
            out.append(
                _p(
                    "Greyed rows are history: "
                    + _t(
                        "; ".join(f"row {r.row}: {r.stale_reason or 'superseded'}" for r in stale)
                    ),
                    "small",
                )
            )
        return out
    for r in s.rows:
        rows = [_head("Field", "Value", "Cell")]
        for c in r.cells:
            label = _header(c.header, c.unit)
            note = [
                x
                for x in (
                    c.comment and f"comment: {c.comment}",
                    c.formula and f"formula {c.formula}",
                    c.hidden and "hidden",
                )
                if x
            ]
            value = c.value + (f"  [{'; '.join(note)}]" if note else "")
            rows.append([_c(label, "cellb"), _c(value), _c(f"{c.col}{c.row}", "mono")])
        caption = f"Row {r.row}" + (f" (history: {r.stale_reason})" if r.stale else "")
        out += [_p(_t(caption), "h3"), _table(rows, [2, 4, 0.8])]
    return out


def _drawing(d: DrawingSlice, store: FileStore) -> list[Flowable]:
    out: list[Flowable] = [_p(_t(d.file), "h2")]
    extraction = {
        "text": "Text layer",
        "vision": "Read from a scan by a vision model",
        "none": "Scanned, not read",
    }[d.extraction]
    out.append(
        _kv(
            [
                ("Title", d.title),
                (
                    "Part number",
                    f"{d.part_number} (from the {d.part_number_source.replace('_', ' ')})"
                    if d.part_number and d.part_number_source
                    else d.part_number,
                ),
                ("Current revision", d.current_revision),
                ("Units", d.units),
                ("Pages", d.page_count),
                ("Extraction", extraction),
                ("SHA-256", d.sha256),
            ]
        )
    )
    for w in d.warnings:
        out.append(_p(f"• {_t(w)}", "small"))
    if d.scanned and d.extraction == "none":
        out.append(
            _p(
                "This drawing is an image with no text layer. The app reads it only "
                "after the user agrees, so no values from it are in this report.",
                "muted",
            )
        )

    for page in d.pages[:MAX_DRAWING_PAGES]:
        page_facts = [f for f in d.facts if f.page == page.page]
        numbered = list(enumerate(page_facts, start=1))
        caption = f"Page {page.page} · {page.role.replace('_', ' ')}"
        if page.units:
            caption += f" · units {page.units}"
        block: list[Flowable] = [_p(_t(caption), "h3")]
        png = store.page_png(d.sha256, page.page, PAGE_DPI, page.correction)
        if png:
            boxes = [(n, b) for n, f in numbered for b in f.bboxes if len(b) == 4]
            block.append(_DrawingPage(png, page.width, page.height, boxes, max_h=118 * mm))
        else:
            block.append(
                _p(
                    "The original file is not in the file store, so the page cannot be pictured.",
                    "muted",
                )
            )
        out += [CondPageBreak(70 * mm), *block, Spacer(1, 4)]
        if not numbered:
            continue
        rows: list[Row] = [_head("#", "Region", "Label", "Value", "Confidence", "Status")]
        extra: list[tuple] = []
        for n, f in numbered:
            status = (f.stale_reason or "history") if f.stale else "current"
            if f.points_to:
                status += f"; see {f.points_to.split('!')[-1]}"
            rows.append(
                [
                    _c(n, "cellb"),
                    _c(REGION_LABEL.get(f.region, f.region)),
                    _c(f.label),
                    _c(f.value + (f" {f.unit}" if f.unit and f.unit not in f.value else "")),
                    _c(f.confidence),
                    _c(status),
                ]
            )
            if f.stale:
                extra.append(("TEXTCOLOR", (0, len(rows) - 1), (-1, len(rows) - 1), MUTED))
        out.append(_table(rows, [0.35, 1.1, 1.3, 3, 0.9, 1.3], extra=extra))
    if len(d.pages) > MAX_DRAWING_PAGES:
        out.append(
            _p(f"Pages {MAX_DRAWING_PAGES + 1} to {len(d.pages)} are not pictured.", "muted")
        )
    return out


def _model(m: ModelSlice, store: FileStore) -> list[Flowable]:
    h = m.header
    units = h.units or "unknown"
    if not h.units_declared:
        units += " (not declared; IGES default applied)"
    out: list[Flowable] = [
        _p(_t(m.file), "h2"),
        _kv(
            [
                (
                    "Geometry",
                    f"{m.topology.replace('_', ' ')}, "
                    f"{'one closed valid solid' if m.valid else 'not one valid solid'}",
                ),
                ("Bodies / faces", f"{m.bodies} / {m.faces}"),
                ("Part form", m.form),
                (
                    "Part number",
                    f"{m.part_number} (from the {m.part_number_source})"
                    if m.part_number and m.part_number_source
                    else m.part_number,
                ),
                (
                    "Revision",
                    f"{m.revision} (from the {m.revision_source.replace('_', ' ')})"
                    if m.revision and m.revision_source
                    else m.revision,
                ),
                ("Units", units),
                ("Sending system", h.sending_system),
                ("Created", h.created),
                ("Author", " / ".join(x for x in (h.author, h.organization) if x) or None),
                ("Geometry kernel", m.kernel),
                ("SHA-256", m.sha256),
            ]
        ),
    ]
    for w in m.warnings:
        out.append(_p(f"• {_t(w)}", "small"))
    views = [(v, svg) for v in m.views if (svg := store.view(m.sha256, v))]
    if views:
        out += [
            _p("Hidden-line projections (exact, from the model)", "h3"),
            _Projections(views),
            Spacer(1, 4),
        ]
    features = [f for f in m.features if f.kind != "header"]
    if features:
        rows: list[Row] = [_head("Feature", "Value", "Confidence", "How it was measured")]
        extra: list[tuple] = []
        for f in features:
            rows.append(
                [_c(f.label, "cellb"), _c(f.value), _c(f.confidence), _c(f.method or "-", "small")]
            )
            if f.stale:
                extra.append(("TEXTCOLOR", (0, len(rows) - 1), (-1, len(rows) - 1), MUTED))
        out += [
            _p("Measured features", "h3"),
            _table(rows, [1.4, 2.4, 0.8, 3], extra=extra),
            _p(
                "A 3D model never states material, tolerance, surface finish, threads or "
                "mass; those come only from the spreadsheet and the drawing.",
                "muted",
            ),
        ]
    return out


def _answers(answers: Sequence[AskResult]) -> list[Flowable]:
    out: list[Flowable] = [
        PageBreak(),
        _p("6. Questions and answers", "h1"),
        _p(
            "Questions asked about this part in this session. Each answer lists only the sources "
            "the app verified against the files.",
            "muted",
        ),
    ]
    for i, a in enumerate(answers, start=1):
        block: list[Flowable] = [
            _p(f"Q{i}. {_t(a.question)}", "h2"),
            _p(
                f"<b>{_t(STATUS_LABEL.get(a.status, a.status))}</b> · confidence "
                f"{_t(a.confidence)}",
                "muted",
            ),
            Spacer(1, 2),
            _p(_markdown(a.answer), "body"),
        ]
        out.append(KeepTogether(block))
        if a.computation:
            comp = a.computation
            out += [_p("Working", "h3"), _p(_t(f"{comp.label}: {comp.working}"), "small")]
        if a.evidence:
            rows: list[Row] = [_head("Source", "Location", "Value", "Confidence")]
            for e in a.evidence:
                loc = f"{e.file} › {e.locator}" if e.locator else e.file
                rows.append(
                    [
                        _c(SOURCE_LABEL.get(e.source, e.source)),
                        _c(loc),
                        _c(e.value),
                        _c(e.confidence + (" (auto-linked)" if e.auto_linked else "")),
                    ]
                )
            out += [_p("Sources", "h3"), _table(rows, [1, 3, 2.2, 1.1])]
        if a.missing_information:
            out.append(_p("Not in the files: " + _t("; ".join(a.missing_information)), "small"))
        if a.general_knowledge:
            out.append(
                _p(
                    "General knowledge (not from the files): " + _t("; ".join(a.general_knowledge)),
                    "small",
                )
            )
        meta: list[str] = []
        if a.verification:
            v = a.verification
            meta.append(f"{v.citations_verified} of {v.citations_checked} citations verified")
            if v.dropped:
                meta.append(f"{len(v.dropped)} unverifiable citation(s) removed")
        if a.provider:
            p = a.provider
            meta.append(f"{p.provider} {p.model}" + (" (fallback)" if p.fallback_used else ""))
        if a.created_at:
            meta.append(a.created_at.strftime("%Y-%m-%d %H:%M UTC"))
        if meta:
            out.append(_p(_t(" · ".join(meta)), "muted"))
        out.append(Spacer(1, 6))
    return out


def _legend(number: int) -> list[Flowable]:
    out: list[Flowable] = [CondPageBreak(90 * mm), _p(f"{number}. How to read this report", "h1")]
    rows: list[Row] = [_head("Verdict", "Meaning")]
    rows += [[_verdict(v), _c(VERDICT_MEANING[v])] for v in _ORDER]
    out += [_table(rows, [1.5, 5])]
    rows = [_head("Confidence", "Meaning")]
    rows += [[_c(k, "cellb"), _c(v)] for k, v in CONFIDENCE_MEANING.items()]
    out += [
        Spacer(1, 6),
        _table(rows, [1.5, 5]),
        Spacer(1, 6),
        _p(
            "Locations read as <b>file › sheet › cell</b> for spreadsheets, <b>file › page › "
            "region › label</b> for drawings (numbered boxes on the pictured page) and "
            "<b>file › Model › feature</b> for 3D models. Greyed rows are history: an "
            "archived sheet, a superseded revision or a revision-history page.",
            "small",
        ),
    ]
    return out


def build_report(
    record: PartRecord,
    store: FileStore,
    *,
    related: Sequence[str] = (),
    answers: Sequence[AskResult] = (),
    generated_at: datetime | None = None,
) -> bytes:
    """The full part report as PDF bytes."""
    generated = generated_at or datetime.now(UTC)
    facts = record.fact_index()
    story: list[Flowable] = _summary(record, related, answers, generated)
    story += [
        Spacer(1, 14),
        *_sources(record),
        CondPageBreak(60 * mm),
        *_cross_checks(record, facts),
    ]

    story += [PageBreak(), _p("3. Manufacturing record (spreadsheet)", "h1")]
    if record.sheets:
        for s in record.sheets:
            story += _sheet(s)
    else:
        story.append(_p("No spreadsheet row names this part.", "body"))

    story += [PageBreak(), _p("4. Engineering drawings (PDF)", "h1")]
    if record.drawings:
        for d in record.drawings:
            story += _drawing(d, store)
    else:
        story.append(_p("No drawing was found for this part.", "body"))

    story += [PageBreak(), _p("5. 3D models (IGES)", "h1")]
    if record.models:
        for m in record.models:
            story += _model(m, store)
    else:
        story.append(_p("No 3D model was found for this part.", "body"))

    if answers:
        story += _answers(answers)
    story += _legend(7 if answers else 6)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=16 * mm,
        title=_clean(f"Part {record.display_part_number} report"),
        author="SPEC'26 CNC Part Analyzer",
        subject=_clean(record.description() or f"Part {record.display_part_number}"),
    )
    footer = (
        f"SPEC'26 CNC Part Analyzer · Part {record.display_part_number} · "
        f"generated {generated.strftime('%Y-%m-%d %H:%M UTC')}"
    )
    canvas_cls = type("_Footer", (_NumberedCanvas,), {"footer": footer})
    doc.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()
