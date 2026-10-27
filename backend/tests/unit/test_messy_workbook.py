"""Level 1 hardening for messy exports: identity keys, separators, cards, archives, revisions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.parts import base_of, identity_key
from app.ingestion.pipeline import ingest_path, merge_fragments

MESSY = Path(__file__).resolve().parents[3] / "data" / "messy_workshop_export.xlsx"


@pytest.fixture(scope="module")
def result():
    return ingest_path(MESSY)


@pytest.mark.parametrize(
    ("key", "identity"),
    [
        ("P-3001", "3001"),
        ("003003", "3003"),
        ("DWG 2281", "2281"),
        ("3004-A", "3004-A"),  # a revision suffix is not a spelling
        ("2280", "2280"),
        ("0042", "0042"),  # too short to be sure it is zero padding
        ("PN-77", "PN-77"),  # prefixes are only stripped before 3+ digit numbers
    ],
)
def test_identity_key(key, identity):
    assert identity_key(key) == identity


def test_base_of_groups_spellings_and_revisions():
    assert base_of("P-3001") == base_of("3001") == "3001"
    assert base_of("003003") == "3003"
    assert base_of("3004-A") == "3004"


def test_separator_rows_are_not_parts(result):
    assert not any("PLATES" in k or "TURNED" in k for k in result.fragments)
    assert any("separator row" in w for w in result.warnings)


def test_vertical_part_card_becomes_one_record(result):
    """'Part Card 3003' lists labels down column A and one part's values down column B."""
    assert not ({"MATERIAL", "HOLES", "CYCLE TIME"} & set(result.fragments))
    card = next(s for s in result.fragments["003003"].sheets if s.sheet == "Part Card 3003")
    assert card.layout == "card" and len(card.rows) == 1
    by_canon = {c.canonical: c for c in card.rows[0].cells}
    assert by_canon["holes"].value == "6 x Ø14 through"
    assert by_canon["holes"].cell_id == "messy_workshop_export!Part Card 3003!B7"
    assert by_canon["material"].header == "Material"


def test_archive_sheet_is_history(result):
    archive = result.fragments["3001"].sheets[0]
    assert archive.sheet == "Archive_2025" and archive.stale
    assert "archived or obsolete" in (archive.stale_reason or "")


def test_superseded_revision_row_is_history_and_newest_is_current(result):
    rows = result.fragments["P-3002"].sheets[0].rows
    assert [(r.row, r.stale) for r in rows] == [(9, True), (10, False)]
    assert "SUPERSEDED" in (rows[0].stale_reason or "")


def test_sheet_banner_unit_statement(result):
    master = result.fragments["3004-A"].sheets[0]
    assert master.default_unit == "mm"  # "Units: mm unless stated."


def test_hours_column_maps_to_cycle_time(result):
    cells = result.fragments["P-3001"].sheets[0].rows[0].cells
    est = next(c for c in cells if c.header.startswith("Est. Time"))
    assert est.canonical == "cycle_time" and est.unit == "h"


def test_identity_merge_keeps_history_out_of_current_values(result):
    frags = [f for k, f in result.fragments.items() if identity_key(k) == "3001"]
    rec = merge_fragments("3001", frags)
    assert rec.display_part_number == "P-3001"  # the live register's spelling, not the archive's
    assert set(rec.aliases) == {"3001"}
    current = {f.fact_id: f for f in rec.facts() if f.canonical == "material" and not f.stale}
    assert [f.value for f in current.values()] == ["EN24"]
    assert any(f.value == "EN19" and f.stale for f in rec.facts())


def test_older_revision_without_status_column_is_marked_stale():
    from app.domain.record import CellRef, RecordRow
    from app.ingestion.pipeline import _mark_older_revisions

    def row(n: int, rev: str) -> RecordRow:
        cell = CellRef(
            cell_id=f"f!S!C{n}", file="f", sheet="S", row=n, col="C", header="Rev",
            canonical="revision", value=rev, value_type="text",
        )  # fmt: skip
        return RecordRow(row=n, cells=[cell])

    rows = [row(2, "A"), row(3, "C"), row(4, "B")]
    _mark_older_revisions(rows)
    assert [r.stale for r in rows] == [True, False, True]
    assert rows[0].stale_reason == "older revision (Rev A; Rev C is current)"
