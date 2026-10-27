from __future__ import annotations

import pytest

from app.ingestion.canonical import CanonicalField, extract_unit, match_header
from app.ingestion.parts import normalize_part_key, split_part_key
from app.ingestion.pipeline import ingest_bytes, ingest_path, merge_fragments
from tests.fixtures.workbooks import conflicting_workbooks, csv_parts, drift_workbook

# ------------------------------------------------------------------------------- part keys


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (2280, "2280"),
        (2280.0, "2280"),
        ("2280", "2280"),
        (" 2280 ", "2280"),
        ("2280.0", "2280"),
        (" 2280 ", "2280"),
        ("2280-a", "2280-A"),
        ("0042", "0042"),
        ("", None),
        (None, None),
        (2280.5, None),
        (True, None),
    ],
)
def test_normalize_part_key(raw, expected):
    assert normalize_part_key(raw) == expected


@pytest.mark.parametrize(
    ("key", "base", "affix"),
    [
        ("2280", "2280", None),
        ("2280-A", "2280", "A"),
        ("P-2280", "2280", "P"),
        ("2280 REV B", "2280", "REV B"),
    ],
)
def test_split_part_key(key, base, affix):
    assert split_part_key(key) == (base, affix)


# --------------------------------------------------------------------------- header mapping


@pytest.mark.parametrize(
    ("header", "field"),
    [
        ("Part No", CanonicalField.PART_NUMBER),
        ("Item Code", CanonicalField.PART_NUMBER),
        ("P/N", CanonicalField.PART_NUMBER),
        ("Mat. Grade", CanonicalField.MATERIAL),
        ("Matl", CanonicalField.MATERIAL),
        ("Stock Size (mm)", CanonicalField.RAW_STOCK),
        ("Raw Stock", CanonicalField.RAW_STOCK),
        ("Final Dims", CanonicalField.FINISHED_SIZE),
        ("Hole Details", CanonicalField.HOLES),
        ("Work Center", CanonicalField.MACHINE),
        ("W/C", CanonicalField.MACHINE),
        ("Time/Pc (min)", CanonicalField.CYCLE_TIME),
        ("Cycle Time (min)", CanonicalField.CYCLE_TIME),
        ("Tol.", CanonicalField.TOLERANCE),
        ("Heat Tr.", CanonicalField.HEAT_TREATMENT),
        ("Lot Size", CanonicalField.BATCH_QTY),
        ("Op No", CanonicalField.OPERATION_NUMBER),
        ("Setup (min)", CanonicalField.SETUP_TIME),
        ("Run (min)", CanonicalField.RUN_TIME),
        ("Surface Finish Ra", CanonicalField.SURFACE_FINISH),
        ("Remarks", CanonicalField.REMARKS),
    ],
)
def test_header_synonyms(header, field):
    assert match_header(header).canonical == field


@pytest.mark.parametrize("header", ["Coating", "Customer PO", "Shift", "Inspector"])
def test_unknown_headers_stay_unmapped(header):
    assert match_header(header).canonical is None


@pytest.mark.parametrize(
    ("header", "label", "unit"),
    [
        ("Cycle Time (min)", "Cycle Time", "min"),
        ("Stock Size (mm)", "Stock Size", "mm"),
        ("Length [in]", "Length", "in"),
        ("Part No (customer)", "Part No (customer)", None),
    ],
)
def test_extract_unit(header, label, unit):
    assert extract_unit(header) == (label, unit)


# ----------------------------------------------------------------------- sample workbook A


def test_sample_a_layout_and_parts(sample_a):
    result = ingest_path(sample_a)
    assert sorted(result.fragments) == ["2280", "2281", "2282"]
    sheets = {s.sheet: s for s in result.sheets}
    assert sheets["Parts"].header_row == 1 and sheets["Parts"].kind == "attributes"
    assert sheets["Operations"].kind == "rows"
    assert result.warnings == []


def test_text_and_numeric_part_numbers_resolve_identically(sample_a):
    frags = ingest_path(sample_a).fragments
    assert frags["2280"].display_part_number == "2280"  # numeric cell
    assert frags["2282"].display_part_number == "2282"  # text cell


def test_operations_grouped_and_ordered(sample_a):
    rec = merge_fragments("2280", [ingest_path(sample_a).fragments["2280"]])
    ops = next(s for s in rec.sheets if s.sheet == "Operations")
    op_numbers = [
        next(c.value for c in r.cells if c.canonical == "operation_number") for r in ops.rows
    ]
    assert op_numbers == ["10", "20", "30"]
    setups = [next(c.value for c in r.cells if c.canonical == "setup_time") for r in ops.rows]
    assert setups == ["5", "3", "4"]


def test_cell_ids_and_engineering_symbols_preserved(sample_a):
    rec = merge_fragments("2280", [ingest_path(sample_a).fragments["2280"]])
    cells = rec.cell_index()
    assert cells["mfg_record_A!Parts!C2"].value == "SS304"
    assert cells["mfg_record_A!Parts!D2"].value == "Ø125 x 25 (round bar)"
    assert cells["mfg_record_A!Parts!I2"].value.startswith("±0.1")
    assert cells["mfg_record_A!Parts!H2"].unit == "min"
    assert cells["mfg_record_A!Parts!H2"].value == "28"


def test_literal_none_counts_as_present(sample_a):
    rec = merge_fragments("2281", [ingest_path(sample_a).fragments["2281"]])
    assert "hole details" in rec.available_fields
    assert rec.cell_index()["mfg_record_A!Parts!F3"].value == "None"


def test_other_sources_reported_unavailable(sample_a):
    rec = merge_fragments("2280", [ingest_path(sample_a).fragments["2280"]])
    assert rec.sources["excel"].available and rec.sources["excel"].files == ["mfg_record_A.xlsx"]
    assert not rec.sources["pdf"].available
    assert not rec.sources["iges"].available


# ----------------------------------------------------------------------- sample workbook B


def test_sample_b_banner_rows_and_renamed_headers(sample_b):
    result = ingest_path(sample_b)
    sheets = {s.sheet: s for s in result.sheets}
    assert sheets["Job Cards"].header_row == 4
    assert sheets["Job Cards"].mapped_columns["Mat. Grade"] == "material"
    assert sheets["Job Cards"].mapped_columns["Time/Pc (min)"] == "cycle_time"
    assert sorted(result.fragments) == ["2283", "2284"]
    rec = merge_fragments("2283", [result.fragments["2283"]])
    job = next(s for s in rec.sheets if s.sheet == "Job Cards")
    assert any("ACME PRECISION MACHINING" in b.value for b in job.banner)
    assert rec.cell_index()["job_cards_B!Job Cards!C5"].value == "C36000 Brass (free-cutting)"
    tools = next(s for s in rec.sheets if s.sheet == "Tooling")
    assert [r.row for r in tools.rows] == [2, 3]


def test_records_from_two_workbooks_merge(sample_a, sample_b):
    a, b = ingest_path(sample_a), ingest_path(sample_b)
    assert set(a.fragments).isdisjoint(b.fragments)


# ---------------------------------------------------------------------------- drift fixtures


def test_drift_workbook_is_understood_without_code_changes():
    result = ingest_bytes(drift_workbook(), "register_7.xlsx")
    assert set(result.fragments) >= {"3001", "3001-A", "0042"}
    reg = next(s for s in result.sheets if s.sheet == "Register")
    assert reg.header_row == 4
    assert reg.mapped_columns["P/N"] == "part_number"
    assert reg.mapped_columns["Matl"] == "material"
    assert reg.mapped_columns["W/C"] == "machine"
    assert reg.mapped_columns["Cyc (min)"] == "cycle_time"  # unit row joined into the header
    assert reg.mapped_columns["Coating"] is None  # unknown column kept, not dropped

    rec = merge_fragments("3001", [result.fragments["3001"]])
    register = next(s for s in rec.sheets if s.sheet == "Register")
    assert [r.row for r in register.rows] == [6, 7]  # continuation row attached to 3001
    assert any("blank part number" in w for w in result.warnings)
    assert any("hidden" in w for w in result.warnings)

    internal = next(s for s in rec.sheets if s.sheet == "Internal")
    assert internal.hidden
    assert all(c.hidden for r in internal.rows for c in r.cells)
    assert any("hidden" in w for w in rec.warnings)

    cells = rec.cell_index()
    assert cells["register_7!Register!F6"].comment == "Customer asked for nitric passivation"
    assert '"Coating" column' in rec.available_fields


def test_leading_zero_text_part_number_kept():
    result = ingest_bytes(drift_workbook(), "register_7.xlsx")
    assert result.fragments["0042"].display_part_number == "0042"


def test_csv_ingest():
    result = ingest_bytes(csv_parts(), "parts.csv")
    assert result.file_format == "csv"
    assert {"4100", "04101"} <= set(result.fragments)
    rec = merge_fragments("4100", [result.fragments["4100"]])
    assert rec.cell_index()["parts!parts!C2"].value == "Al 7075-T6"  # csv sheet = file stem
    nan_rows = [r for r in result.cells if r[0].value == "nan"]
    assert all(ref.value_type == "text" for ref, _ in nan_rows)


def test_conflicting_values_across_files_are_flagged():
    a, b = conflicting_workbooks()
    fa = ingest_bytes(a, "plant_a.xlsx").fragments["5000"]
    fb = ingest_bytes(b, "plant_b.xlsx").fragments["5000"]
    rec = merge_fragments("5000", [fa, fb])
    assert any("Conflict in material" in w and "EN8D" in w for w in rec.warnings)


def test_same_bytes_same_hash(sample_a):
    data = sample_a.read_bytes()
    assert ingest_bytes(data, "x.xlsx").sha256 == ingest_bytes(data, "y.xlsx").sha256


def test_unsupported_file_rejected():
    from app.ingestion.readers import UnsupportedFileError

    with pytest.raises(UnsupportedFileError):
        ingest_bytes(b"\x00\x01\x02binary", "drawing.pdf")
