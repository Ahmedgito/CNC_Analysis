"""PDF bytes -> ``DrawingSlice``: every fact a drawing states, with page, region and position.

Guards run first and fail with a specific reason rather than a partial result: password
protection, damaged files, too many pages, and too much text for an engineering drawing.
Active content (JavaScript, embedded files) is never executed; its presence is reported.
"""

from __future__ import annotations

import io
import re

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect

from app.domain.drawing import DrawingFact, DrawingPage, DrawingSlice, make_drawing_fact_id
from app.ingestion.parts import identity_key, normalize_part_key
from app.ingestion.pdf.dimensions import KIND_LABEL, find_dimensions, is_view_title
from app.ingestion.pdf.layout import PageText, Segment, Table, read_page
from app.ingestion.pdf.notes import Note, declared_unit, find_notes, unit_word
from app.ingestion.pdf.revisions import RevisionInfo, find_revisions, rev_rank
from app.ingestion.pdf.title_block import TitleBlock, find_title_block

MAX_PAGES = 20
_MIN_CHARS_FOR_ORIENTATION = 20
_UPRIGHT_ENOUGH = 0.5
MAX_CHARS = 200_000
_TEXT_PART_RE = re.compile(
    r"\bPART\s*(?:NO\.?|NUMBER|#)?\s*[:#]?\s*([A-Z]{0,3}-?\d{3,}[\w-]*)", re.I
)
_FILE_PART_RE = re.compile(r"^(?:[A-Za-z]{1,4}[-_ ]?)?(\d{3,}(?:-[A-Za-z0-9]{1,3})?)(?=[_\-. ]|$)")
_TOLERANCE_KEYS = {"general_tolerance"}


class UnreadableDocumentError(ValueError):
    """The PDF cannot be read at all (encrypted, damaged, or outside the size limits)."""


def _is_password_error(exc: BaseException) -> bool:
    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, PDFPasswordIncorrect | PDFEncryptionError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


def _unreadable(exc: BaseException, what: str) -> UnreadableDocumentError:
    """Any parser failure on untrusted input becomes a clear, specific refusal (never a 500)."""
    if _is_password_error(exc):
        return UnreadableDocumentError("the PDF is password-protected")
    return UnreadableDocumentError(what)


def _open(data: bytes):
    try:
        return pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfplumber wraps pdfminer's many error types
        raise _unreadable(exc, "the file is not a readable PDF") from exc


def _read_pages(data: bytes, max_pages: int, max_chars: int) -> list[PageText]:
    pdf = _open(data)
    with pdf:
        try:
            count = len(pdf.pages)
        except Exception as exc:
            raise _unreadable(exc, "the PDF's page tree could not be read") from exc
        if count == 0:
            raise UnreadableDocumentError("the PDF has no pages")
        if count > max_pages:
            raise UnreadableDocumentError(
                f"the PDF has {count} pages; drawings over {max_pages} pages are not accepted"
            )
        try:
            pages = [read_page(p, i + 1) for i, p in enumerate(pdf.pages)]
        except Exception as exc:
            raise _unreadable(exc, "the PDF is damaged and could not be read") from exc
    pages = [_orient(data, p) for p in pages]
    if sum(p.char_count for p in pages) > max_chars:
        raise UnreadableDocumentError("the PDF holds far more text than an engineering drawing")
    return pages


def _turned(data: bytes, page_number: int, degrees: int) -> bytes:
    """The same PDF with one page turned clockwise by ``degrees``."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.pages[page_number - 1].rotate(degrees)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _orient(data: bytes, page: PageText) -> PageText:
    """Re-read a page whose text is mostly sideways, turned so that it reads upright.

    A drawing saved in portrait with landscape content, or rotated by mistake, reads as vertical
    text: no title block, no notes. The page is tried at 90, 270 and 180 degrees and the turn with
    the most upright text wins. The viewer renders the page with the same turn, so highlight
    boxes stay aligned with the image.
    """
    if page.char_count < _MIN_CHARS_FOR_ORIENTATION or page.upright_ratio >= _UPRIGHT_ENOUGH:
        return page
    best = page
    for degrees in (90, 270, 180):
        try:
            with pdfplumber.open(io.BytesIO(_turned(data, page.number, degrees))) as pdf:
                candidate = read_page(pdf.pages[page.number - 1], page.number)
        except Exception:  # noqa: S112 - a turn that cannot be read is simply not used
            continue
        if candidate.upright_ratio > best.upright_ratio:
            candidate.correction = degrees
            candidate.rotation = page.rotation  # keep the file's own /Rotate for reference
            best = candidate
    return best


def _page_units(tb: TitleBlock | None, notes: list[Note]) -> str | None:
    if tb and (f := tb.get("units")):
        u = unit_word(f.value) or declared_unit(f"UNITS: {f.value}")
        if u:
            return u
    for n in notes:
        if n.canonical == "units":
            return n.parsed.get("unit")
    return None


def _part_number(
    file_name: str, title_blocks: list[TitleBlock], text_facts: list[DrawingFact]
) -> tuple[str | None, str | None, str | None, list[str]]:
    """(printed number, normalised key, source, warnings)."""
    warnings: list[str] = []
    from_file = _FILE_PART_RE.match(file_name)
    file_key = normalize_part_key(from_file.group(1)) if from_file else None
    for tb in title_blocks:
        if (f := tb.get("part_number")) and (key := normalize_part_key(f.value)):
            if file_key and identity_key(file_key).split("-")[0] != identity_key(key).split("-")[0]:
                warnings.append(
                    f"the title block says part {f.value} but the file name suggests {file_key}; "
                    "the title block was used"
                )
            return f.value, key, "title_block", warnings
    for t in text_facts:
        m = _TEXT_PART_RE.search(t.value)
        if m and (key := normalize_part_key(m.group(1))):
            return m.group(1), key, "text", warnings
    if file_key:
        warnings.append(
            f"no part number found inside the drawing; linked by its file name ({file_key})"
        )
        return file_key, file_key, "filename", warnings
    warnings.append("no part number found in the drawing or its file name; it is not linked")
    return None, None, None, warnings


def _current_revision(
    rev: RevisionInfo, title_blocks: list[TitleBlock], warnings: list[str]
) -> str | None:
    tb_revs = [f.value.strip().upper() for tb in title_blocks if (f := tb.get("revision"))]
    if rev.current_statement:
        stated = rev.current_statement[0]
        if tb_revs and stated not in tb_revs:
            warnings.append(
                f"the drawing states current revision {stated} but its title block says "
                f"{', '.join(tb_revs)}"
            )
        return stated
    if tb_revs:
        return max(tb_revs, key=rev_rank)
    if rev.rows:
        return max((r.rev for r in rev.rows), key=rev_rank)
    return None


def read_drawing(
    data: bytes, file_name: str, sha256: str, max_pages: int = MAX_PAGES, max_chars: int = MAX_CHARS
) -> tuple[DrawingSlice, str | None]:
    """The drawing's facts and the part key it belongs to (None when unidentifiable)."""
    stem = file_name.rsplit(".", 1)[0]
    warnings: list[str] = []
    if b"/JavaScript" in data or re.search(rb"/JS\s*[(<]", data):
        warnings.append("the PDF contains JavaScript, which was never run")
    if b"/EmbeddedFile" in data:
        warnings.append("the PDF contains embedded files, which were ignored")

    pages = _read_pages(data, max_pages, max_chars)
    rev = find_revisions(pages)
    facts: list[DrawingFact] = []
    page_meta: list[DrawingPage] = []
    title_blocks: list[TitleBlock] = []
    text_facts: list[DrawingFact] = []
    notes_by_page: dict[int, list[Note]] = {}
    units_by_page: dict[int, str | None] = {}

    for page in pages:
        tb = find_title_block(page)
        if tb:
            title_blocks.append(tb)
        exclude: list[Table] = [t for p, t in rev.tables if p == page.number]
        if tb:
            exclude.append(Table(tb.bbox, []))
        notes, _ = find_notes(page, exclude)
        notes_by_page[page.number] = notes
        units_by_page[page.number] = _page_units(tb, notes)
        if page.hybrid:
            warnings.append(f"page {page.number} contains image content that was not read")
        if page.unmapped_glyphs:
            warnings.append(
                f"page {page.number}: {page.unmapped_glyphs} characters use a font without a "
                "text mapping and could not be read"
            )

    doc_units = next((u for u in units_by_page.values() if u), None)

    for page in pages:
        units = units_by_page[page.number] or doc_units
        tb = next((t for t in title_blocks if t.page == page.number), None)
        notes = notes_by_page[page.number]
        exclude = [t for p, t in rev.tables if p == page.number]
        if tb:
            exclude.append(Table(tb.bbox, []))
        note_ids = {
            n.number: make_drawing_fact_id(stem, n.page, "note", str(n.number)) for n in notes
        }

        if tb:
            for f in tb.fields:
                points_to = None
                if f.pointer_note is not None:
                    points_to = note_ids.get(f.pointer_note)
                    if points_to is None:
                        warnings.append(
                            f"the title block says '{f.value}' but page {page.number} has no "
                            f"note {f.pointer_note}"
                        )
                facts.append(
                    DrawingFact(
                        fact_id=make_drawing_fact_id(stem, page.number, "title_block", f.key),
                        page=page.number,
                        region="title_block",
                        key=f.key,
                        label=f.label,
                        canonical=f.canonical,
                        value=f.value,
                        unit=units if f.key in _TOLERANCE_KEYS else None,
                        bboxes=[f.bbox],
                        points_to=points_to,
                    )
                )
        for n in notes:
            facts.append(
                DrawingFact(
                    fact_id=note_ids[n.number],
                    page=page.number,
                    region="note",
                    key=str(n.number),
                    label=f"Note {n.number}",
                    canonical=n.canonical,
                    value=n.text,
                    unit=units if n.canonical == "tolerance" else None,
                    bboxes=[n.bbox],
                    parsed=n.parsed,
                )
            )

        consumed = {id(s) for s in _consumed(page, notes, rev, exclude)}
        view_segs = [s for s in page.segments if id(s) not in consumed]
        dims = find_dimensions(view_segs)
        dim_texts = {d.text for d in dims}
        for i, d in enumerate(dims, start=1):
            facts.append(
                DrawingFact(
                    fact_id=make_drawing_fact_id(stem, page.number, "dimension", str(i)),
                    page=page.number,
                    region="dimension",
                    key=str(i),
                    kind=d.kind,
                    label=KIND_LABEL[d.kind],
                    value=d.text,
                    unit=units if d.kind not in ("angle", "thread") else None,
                    confidence="inferred" if d.inferred else "exact",
                    bboxes=d.bboxes,
                    parsed=d.parsed,
                )
            )
        n_text = 0
        for s in view_segs:
            text = s.text.strip()
            if (
                text in dim_texts
                or is_view_title(text)
                or not re.search(r"[A-Za-z]{3,}", text)
                or len(text) < 4
            ):
                continue
            n_text += 1
            fact = DrawingFact(
                fact_id=make_drawing_fact_id(stem, page.number, "text", str(n_text)),
                page=page.number,
                region="text",
                key=str(n_text),
                label="Text",
                value=text,
                bboxes=[s.bbox],
            )
            facts.append(fact)
            text_facts.append(fact)

    current = _current_revision(rev, title_blocks, warnings)
    if rev.current_statement:
        rv, seg, pno = rev.current_statement
        facts.append(
            DrawingFact(
                fact_id=make_drawing_fact_id(stem, pno, "revision", "current"),
                page=pno,
                region="revision",
                key="current",
                label="Current revision",
                canonical="revision",
                value=rv,
                bboxes=[seg.bbox],
            )
        )
    for r in rev.rows:
        stale = current is not None and r.rev != current
        facts.append(
            DrawingFact(
                fact_id=make_drawing_fact_id(stem, r.page, "revision", r.rev),
                page=r.page,
                region="revision",
                key=r.rev,
                label=f"Rev {r.rev}" + (f" ({r.date})" if r.date else ""),
                value=r.description,
                stale=stale,
                stale_reason=f"superseded by Rev {current}" if stale else None,
                bboxes=[r.bbox],
                parsed={"rev": r.rev, "date": r.date},
            )
        )

    for page in pages:
        tb = next((t for t in title_blocks if t.page == page.number), None)
        role = (
            "scanned"
            if page.scanned
            else "drawing"
            if tb
            else "revision_history"
            if page.number in rev.history_pages
            else "blank"
            if page.char_count == 0
            else "text"
        )
        page_meta.append(
            DrawingPage(
                page=page.number,
                width=page.width,
                height=page.height,
                rotation=page.rotation,
                correction=page.correction,
                role=role,  # type: ignore[arg-type]
                char_count=page.char_count,
                image_count=page.image_count,
                units=units_by_page[page.number],
            )
        )

    readable = any(p.char_count > 0 for p in pages)
    scanned = not readable and any(p.scanned for p in pages)
    if scanned:
        warnings.append(
            "scanned image with no text layer: nothing could be read without OCR or a vision model"
        )
    elif not readable:
        warnings.append("the PDF has no text and no images; nothing could be read")
    if readable and not title_blocks:
        warnings.append("no title block was found")
    if readable and doc_units is None:
        warnings.append("the drawing does not state its units")

    printed, key, source, link_warnings = _part_number(file_name, title_blocks, text_facts)
    warnings.extend(link_warnings)
    title = next((f.value for tb in title_blocks if (f := tb.get("title"))), None)
    return (
        DrawingSlice(
            file=file_name,
            file_stem=stem,
            sha256=sha256,
            page_count=len(pages),
            pages=page_meta,
            facts=facts,
            part_number=printed,
            part_number_source=source,  # type: ignore[arg-type]
            title=title,
            current_revision=current,
            units=doc_units,
            readable=readable,
            scanned=scanned,
            extraction="text" if readable else "none",
            warnings=warnings,
        ),
        key,
    )


def _consumed(
    page: PageText, notes: list[Note], rev: RevisionInfo, exclude: list[Table]
) -> list[Segment]:
    """Segments already read as title block, notes, revision table or current-revision line."""
    out = [s for s in page.segments if any(t.contains(s) for t in exclude)]
    note_boxes = [n.bbox for n in notes]
    for s in page.segments:
        cx, cy = (s.x0 + s.x1) / 2, (s.top + s.bottom) / 2
        if any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b in note_boxes):
            out.append(s)
        if s.text.strip().upper().startswith(("NOTES", "GENERAL NOTES")):
            out.append(s)
    if rev.current_statement and rev.current_statement[2] == page.number:
        out.append(rev.current_statement[1])
    return out
