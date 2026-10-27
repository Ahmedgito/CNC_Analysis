from __future__ import annotations

import io

from pypdf import PdfReader

from app.domain.record import PartRecord, SourceStatus
from app.services.file_store import FileStore
from app.services.report import _clean, _header, _markdown, _Projections, build_report


def test_text_is_mapped_to_the_standard_font():
    assert _clean("⌀48 − 0.02 → ≈ 5 µm") == "Ø48 - 0.02 -> ~ 5 µm"
    assert _clean("Ø120 × 20 ± 0.1 › C2") == "Ø120 × 20 ± 0.1 › C2"  # already in Windows-1252
    assert _clean("零件") == "??"  # nothing outside the font reaches the PDF


def test_answer_markdown_becomes_markup():
    assert _markdown("**Material:** SS304 <b>\n- one\n* two") == (
        "<b>Material:</b> SS304 &lt;b&gt;<br/>• one<br/>• two"
    )


def test_header_unit_is_not_repeated():
    assert _header("Bore (mm)", "mm") == "Bore (mm)"
    assert _header("Est. Time (hr)", "h") == "Est. Time (hr)"
    assert _header("Stock OD", "mm") == "Stock OD (mm)"
    assert _header("Qty", None) == "Qty"


def test_projection_polylines_are_parsed():
    svg = (
        b'<svg viewBox="-1 -2 10 20"><path class="visible" d="M0.000 0.000 L1.000 0.000 '
        b'L1.000 1.000 M2.000 2.000 L3.000 3.000" stroke-width="0.4"/></svg>'
    )
    box, paths = _Projections._parse(svg)
    assert box == [-1.0, -2.0, 10.0, 20.0]
    assert paths == [("visible", [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], [(2.0, 2.0), (3.0, 3.0)]])]


def test_empty_record_builds(tmp_path):
    record = PartRecord(
        part_key="42",
        display_part_number="42",
        base_key="42",
        sources={
            "excel": SourceStatus(available=False),
            "pdf": SourceStatus(available=False),
            "iges": SourceStatus(available=False),
        },
        sheets=[],
        available_fields=[],
    )
    pdf = build_report(record, FileStore(tmp_path))
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Part 42" in text
    assert "No spreadsheet row names this part." in text
    assert "No spreadsheet for this part." in text
