"""Synthetic PDF drawings for edge cases the sample data does not cover.

Built with ReportLab the way the judges' sample drawings are (A4 landscape, a ruled title block,
numbered notes, dimension text in the views), then varied: no title block, no units, rotated
pages, password protection, active content, injection text, more pages than allowed.
"""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

W, H = landscape(A4)


def _title_block(c: canvas.Canvas, rows: list[tuple[str, str]], top: float = 150) -> None:
    x, width, row_h = W - 310, 280, 14
    y = top
    c.setFont("Helvetica-Bold", 9)
    c.rect(x, y - row_h, width, row_h)
    c.drawString(x + 60, y - 10, "ACME PRECISION MACHINING")
    for label, value in rows:
        y -= row_h
        c.rect(x, y - row_h, 100, row_h)
        c.rect(x + 100, y - row_h, width - 100, row_h)
        c.setFont("Helvetica", 7)
        c.drawString(x + 4, y - 10, label)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 104, y - 10, value)


def _notes(c: canvas.Canvas, notes: list[str], top: float = 160) -> None:
    c.setFont("Helvetica-Bold", 8)
    c.drawString(28, top, "NOTES:")
    c.setFont("Helvetica", 7.5)
    for i, text in enumerate(notes, start=1):
        c.drawString(28, top - 13 * i, f"{i}. {text}")


def drawing_pdf(
    *,
    title_block: list[tuple[str, str]] | None = None,
    notes: list[str] | None = None,
    dims: list[tuple[str, float, float]] | None = None,
    rotated_dims: list[tuple[str, float, float]] | None = None,
    pages: int = 1,
    page_rotation: int = 0,
    password: str | None = None,
    javascript: bool = False,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for _ in range(pages):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(200, H - 50, "TOP VIEW")
        c.setFont("Helvetica", 9)
        for text, x, y in dims or []:
            c.drawString(x, H - y, text)
        for text, x, y in rotated_dims or []:
            c.saveState()
            c.translate(x, H - y)
            c.rotate(90)
            c.drawString(0, 0, text)
            c.restoreState()
        if notes:
            _notes(c, notes)
        if title_block:
            _title_block(c, title_block)
        c.showPage()
    c.save()
    data = buf.getvalue()
    if page_rotation or password or javascript:
        reader = PdfReader(io.BytesIO(data))
        writer = PdfWriter()
        for page in reader.pages:
            if page_rotation:
                page.rotate(page_rotation)
            writer.add_page(page)
        if javascript:
            from pypdf.generic import DictionaryObject, NameObject, TextStringObject

            writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
                {
                    NameObject("/S"): NameObject("/JavaScript"),
                    NameObject("/JS"): TextStringObject("app.alert('hello');"),
                }
            )
        if password:
            writer.encrypt(user_password=password, owner_password=password + "-owner")
        out = io.BytesIO()
        writer.write(out)
        data = out.getvalue()
    return data


STANDARD_TB = [
    ("PART NO", "7001"),
    ("PART NAME", "TEST BLOCK"),
    ("MATERIAL", "AL 6082-T6"),
    ("SCALE", "1:1"),
    ("UNITS", "MM"),
    ("GEN. TOLERANCE", "±0.1"),
    ("DRAWN / REV", "QA / D"),
]


def standard_drawing(**overrides) -> bytes:
    kwargs = {
        "title_block": STANDARD_TB,
        "notes": ["ALL DIMENSIONS IN MM.", "DEBURR ALL EDGES."],
        "dims": [("4X Ø8 THRU", 420, 110), ("Ø60", 220, 300), ("25", 300, 380)],
        "rotated_dims": [("Ø120", 660, 250)],
    }
    kwargs.update(overrides)
    return drawing_pdf(**kwargs)
