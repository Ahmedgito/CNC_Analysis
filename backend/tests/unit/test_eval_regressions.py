"""Regressions found by the real-model evaluation runs (2026-10-27)."""

from __future__ import annotations

import pytest

from app.domain.record import CellRef
from app.ingestion.cells import normalize_for_match
from app.llm.schemas import Computation, ComputationInput, EvidenceItem
from app.services.compute import ComputeError, compute
from app.services.verifier import verify_citations

CELL = CellRef(
    cell_id="A!Parts!E4",
    file="mfg_record_A.xlsx",
    sheet="Parts",
    row=4,
    col="E",
    header="Finished Size (mm)",
    unit="mm",
    value="101.6 x 63.5 x 9.525",
    value_type="text",
)
MATERIAL = CellRef(
    cell_id="A!Parts!C4",
    file="mfg_record_A.xlsx",
    sheet="Parts",
    row=4,
    col="C",
    header="Material",
    value="Aluminum 6061-T6",
    value_type="text",
)


@pytest.mark.parametrize("dash", ["‐", "‑", "–", "−"])
def test_unicode_hyphens_match_ascii(dash):
    # Groq wrote "6061‑T6" with U+2011; the scorer and the verifier must treat it as "6061-T6".
    assert normalize_for_match(f"Aluminum 6061{dash}T6") == normalize_for_match("Aluminum 6061-T6")
    v = verify_citations(
        [EvidenceItem(cell_id="A!Parts!C4", quoted_value=f"Aluminum 6061{dash}T6")],
        {"A!Parts!C4": MATERIAL},
    )
    assert len(v.evidence) == 1 and not v.dropped


def _conv(expr: str) -> Computation:
    return Computation(
        expression=expr,
        inputs=[ComputationInput(name="c1", cell_id="A!Parts!E4", number_index=0)],
        unit_in="mm",
        unit_out="in",
        label="length in inches",
    )


def test_double_unit_conversion_is_rejected():
    # Groq sent "c1 / 25.4" with unit_in=mm, unit_out=in: 101.6 mm became 0.157 in.
    with pytest.raises(ComputeError, match="factor"):
        compute(_conv("c1 / 25.4"), {"A!Parts!E4": CELL})
    with pytest.raises(ComputeError, match="factor"):
        compute(_conv("c1 * 0.0393701"), {"A!Parts!E4": CELL})


def test_single_conversion_is_correct():
    assert compute(_conv("c1"), {"A!Parts!E4": CELL}).value == pytest.approx(4.0)


def test_unrelated_constants_still_allowed_with_conversion():
    assert compute(_conv("c1 * 2"), {"A!Parts!E4": CELL}).value == pytest.approx(8.0)
