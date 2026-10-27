"""Spreadsheet-vs-drawing cross-check on the real datasets, plus the comparison rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.parts import identity_key
from app.ingestion.pdf import ingest_drawing_path
from app.ingestion.pipeline import PartFragment, ingest_path, merge_fragments
from app.services.crosscheck import compare_materials, values_agree

DATA = Path(__file__).resolve().parents[3] / "data"


def _record(workbook: str, key: str, drawing: str):
    frags = ingest_path(DATA / workbook).fragments
    mine = [f for k, f in frags.items() if identity_key(k) == identity_key(key)]
    return merge_fragments(
        identity_key(key), mine, drawings=[ingest_drawing_path(DATA / drawing).slice]
    )


def _verdicts(record) -> dict[str, str]:
    return {c.field: c.verdict for c in record.cross_checks}


def test_happy_path_agrees_everywhere():
    v = _verdicts(_record("mfg_record_A.xlsx", "2280", "2280_flange.pdf"))
    assert set(v.values()) == {"agree"}
    assert {"material", "outer_diameter", "bore", "holes", "tolerance", "surface_finish"} <= set(v)


def test_inch_drawing_against_mm_record_is_not_flagged():
    """2282: the drawing is in inches, the spreadsheet in mm. They agree after conversion."""
    rec = _record("mfg_record_A.xlsx", "2282", "2282_bracket.pdf")
    v = _verdicts(rec)
    assert "disagree" not in v.values()
    assert v["holes"] == v["thickness"] == v["tolerance"] == "agree_after_conversion"
    assert v["surface_finish"] == "equivalent_by_convention"  # Ra 3.2 vs 125 RMS
    finish = next(c for c in rec.cross_checks if c.field == "surface_finish")
    assert "not an exact conversion" in finish.detail


def test_planted_mismatch_is_flagged_with_both_sources():
    """2283: OD 50 (job card) vs 48 (drawing); brass C36000 vs bronze C93200."""
    rec = _record("job_cards_B.xlsx", "2283", "2283_bushing.pdf")
    v = _verdicts(rec)
    assert v["material"] == "disagree" and v["outer_diameter"] == "disagree"
    assert v["bore"] == "agree"
    od = next(c for c in rec.cross_checks if c.field == "outer_diameter")
    assert od.excel == ["job_cards_B!Job Cards!E5"] and od.pdf == ["2283_bushing!p1!dim!2"]
    # The job card states no unit; the app says how it read the number, never silently.
    assert "read as mm because the cell's other dimensions match the drawing in mm" in od.detail


def test_mm_drawing_against_inch_record_is_not_flagged():
    """3004: the register is in inches (inline), the drawing in mm."""
    v = _verdicts(_record("messy_workshop_export.xlsx", "3004-A", "3004_shaft_collar.pdf"))
    assert "disagree" not in v.values()
    assert v["outer_diameter"] == v["bore"] == "agree_after_conversion"


def test_hole_count_conflict_inside_the_spreadsheet_is_flagged():
    """3003: Master List 4 holes (agrees with the drawing), Part Card 6 holes (does not)."""
    rec = _record("messy_workshop_export.xlsx", "3003", "3003_base_plate.pdf")
    holes = next(c for c in rec.cross_checks if c.field == "holes")
    assert holes.verdict == "disagree"
    assert len(holes.excel) == 2 and "hole count differs" in holes.detail
    assert _verdicts(rec)["material"] == "agree"  # IS 2062 via the note the title block points to


def test_superseded_revision_is_not_compared():
    """3002: Rev A (bore 18, C45) is superseded; only Rev B is compared."""
    rec = _record("messy_workshop_export.xlsx", "P-3002", "3002_coupling_hub_RevB.pdf")
    v = _verdicts(rec)
    assert v["bore"] == "agree" and v["material"] == "agree" and v["thread"] == "agree"
    assert all("18" not in (c.excel_value or "") for c in rec.cross_checks)


def test_no_readable_drawing_means_no_cross_check():
    frags = ingest_path(DATA / "messy_workshop_export.xlsx").fragments
    mine = [f for k, f in frags.items() if identity_key(k) == "3001"]
    scan = ingest_drawing_path(DATA / "3001_gear_blank_scan.pdf").slice
    assert merge_fragments("3001", mine, drawings=[scan]).cross_checks == []
    assert merge_fragments("3001", mine).cross_checks == []


@pytest.mark.parametrize(
    ("a", "b", "verdict"),
    [
        ("SS304", "SS304 (AISI 304)", "agree"),
        ("SS304", "AISI 304", "agree"),
        ("EN8 (080M40)", "EN8 / 080M40", "agree"),
        ("Aluminum 6061-T6", "ALUMINUM 6061-T6", "agree"),
        ("Mild steel IS 2062", "MILD STEEL, IS 2062 E250", "agree"),
        ("C36000 Brass", "BRONZE C93200 (SAE 660)", "disagree"),
        ("Brass", "Bronze", "disagree"),
        ("EN8", "EN24", "disagree"),
        ("Plastic", "Delrin", "unknown"),
    ],
)
def test_material_comparison(a, b, verdict):
    assert compare_materials(a, b) == verdict


def test_spreadsheet_values_that_say_the_same_thing_are_not_conflicts():
    assert values_agree("finished_size", "200 x 120 x 15", "200 x 120 x 15 mm", "mm", None)
    assert values_agree("material", "Mild steel IS 2062", "IS 2062 E250 mild steel")
    assert values_agree("cycle_time", "0.5", "30 min", "h", None)
    assert not values_agree("cycle_time", "0.35", "22 min", "h", None)
    assert not values_agree("holes", "4 x Ø14 thru", "6 x Ø14 through")


def test_merge_without_drawings_keeps_level_one_shape():
    frags = ingest_path(DATA / "mfg_record_A.xlsx").fragments
    rec = merge_fragments("2280", [frags["2280"]])
    assert rec.drawings == [] and rec.cross_checks == []
    assert rec.sources["pdf"].available is False
    assert isinstance(frags["2280"], PartFragment)
