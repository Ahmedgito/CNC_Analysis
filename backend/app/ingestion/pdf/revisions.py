"""Revision history and the current revision.

A drawing package can carry a revision table (REV | DATE | DESCRIPTION) whose old rows quote
values that no longer apply ("BORE D18, MATERIAL C45"). Those rows are kept as facts so the app
can say what changed, but they are marked stale; only the current revision's values are current.
The current revision is, in order of trust: an explicit "CURRENT REVISION: B" statement, the
revision in the drawing page's title block, the highest revision in the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.pdf.layout import PageText, Segment, Table

_CURRENT_RE = re.compile(r"\bCURRENT\s+REV(?:ISION)?\s*[:=]?\s*([A-Z0-9]{1,3})\b", re.I)
_HISTORY_HEADING_RE = re.compile(r"^REVISION\s+(HISTORY|RECORD|TABLE|BLOCK)$", re.I)


@dataclass(slots=True)
class RevisionRow:
    page: int
    rev: str
    date: str | None
    description: str
    bbox: list[float]


@dataclass(slots=True)
class RevisionInfo:
    rows: list[RevisionRow]
    current_statement: tuple[str, Segment, int] | None  # (rev, segment, page)
    tables: list[tuple[int, Table]]  # (page, table) so their text is not re-read
    history_pages: set[int]


def _header_index(cells: list[str]) -> dict[str, int] | None:
    upper = [c.upper().strip() for c in cells]
    rev = next((i for i, c in enumerate(upper) if c in ("REV", "REV.", "REVISION", "ISSUE")), None)
    desc = next(
        (i for i, c in enumerate(upper) if c.startswith(("DESCRIPTION", "CHANGE", "DETAILS"))),
        None,
    )
    if rev is None or desc is None:
        return None
    date = next((i for i, c in enumerate(upper) if c.startswith("DATE")), None)
    return {"rev": rev, "desc": desc, "date": date if date is not None else -1}


def find_revisions(pages: list[PageText]) -> RevisionInfo:
    rows: list[RevisionRow] = []
    tables: list[tuple[int, Table]] = []
    history_pages: set[int] = set()
    current: tuple[str, Segment, int] | None = None
    for page in pages:
        for table in page.tables:
            if not table.rows:
                continue
            header = [c.text if c else "" for c in table.rows[0]]
            idx = _header_index(header)
            if idx is None:
                continue
            tables.append((page.number, table))
            history_pages.add(page.number)
            for row in table.rows[1:]:
                cells = [c.text if c else "" for c in row]
                if len(cells) <= max(idx["rev"], idx["desc"]) or not cells[idx["rev"]]:
                    continue
                bbox = next((c.bbox for c in row if c), table.bbox)
                rows.append(
                    RevisionRow(
                        page=page.number,
                        rev=cells[idx["rev"]].strip().upper(),
                        date=cells[idx["date"]].strip() if idx["date"] >= 0 else None,
                        description=cells[idx["desc"]].strip(),
                        bbox=bbox,
                    )
                )
        for s in page.segments:
            m = _CURRENT_RE.search(s.text)
            if m and current is None:
                current = (m.group(1).upper(), s, page.number)
            if _HISTORY_HEADING_RE.match(s.text.strip()):
                history_pages.add(page.number)
    return RevisionInfo(rows, current, tables, history_pages)


def rev_rank(rev: str) -> tuple[int, float, str]:
    try:
        return (1, float(rev), rev)
    except ValueError:
        return (0, 0.0, rev)
