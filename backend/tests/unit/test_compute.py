from __future__ import annotations

import pytest

from app.domain.evidence import Fact
from app.domain.record import CellRef
from app.llm.schemas import Computation, ComputationInput
from app.services.compute import ComputeError, compute, convert, extract_numbers


def _cell(cid: str, value: str, unit: str | None = None) -> Fact:
    return CellRef(
        cell_id=cid,
        file="f.xlsx",
        sheet="S",
        row=1,
        col="A",
        header="h",
        value=value,
        value_type="text",
        unit=unit,
    ).to_fact(group="g")


CELLS = {
    "f!S!F2": _cell("f!S!F2", "5", "min"),
    "f!S!F3": _cell("f!S!F3", "3", "min"),
    "f!S!F4": _cell("f!S!F4", "4", "min"),
    "f!S!D2": _cell("f!S!D2", "Ø125 x 25 (round bar)", "mm"),
    "f!S!C2": _cell("f!S!C2", "SS304"),
    "f!S!L2": _cell("f!S!L2", "50"),
}


def _comp(expr: str, *inputs: tuple[str, str, int], unit_in=None, unit_out=None) -> Computation:
    return Computation(
        expression=expr,
        inputs=[ComputationInput(name=n, fact_id=c, number_index=i) for n, c, i in inputs],
        unit_in=unit_in,
        unit_out=unit_out,
        label="x",
    )


@pytest.mark.parametrize(
    ("text", "numbers"),
    [
        ("Ø125 x 25 (round bar)", [125.0, 25.0]),
        ("6 x Ø10 through on Ø90 PCD; centre bore Ø40", [6.0, 10.0, 90.0, 40.0]),
        ("±0.1 mm (ISO 2768-m)", [0.1, 2768.0]),
        ("SS304", []),
        ("M10 x 1.5", [1.5]),
        ("Ra 1.6", [1.6]),
        ("1,000", [1.0, 0.0]),  # thousands separators are not decimals; documented limitation
    ],
)
def test_extract_numbers(text, numbers):
    assert extract_numbers(text) == numbers


def test_sum_of_setup_times_shows_working():
    r = compute(
        _comp(
            "c1 + c2 + c3",
            ("c1", "f!S!F2", 0),
            ("c2", "f!S!F3", 0),
            ("c3", "f!S!F4", 0),
            unit_in="min",
        ),
        CELLS,
    )
    assert r.value == 12
    assert r.display == "12 min"
    assert r.working == "5 + 3 + 4 = 12 min"


def test_pick_second_number_from_dimension_string():
    r = compute(_comp("c1", ("c1", "f!S!D2", 1), unit_in="mm"), CELLS)
    assert r.value == 25


def test_unit_conversion_mm_to_inch():
    r = compute(_comp("c1", ("c1", "f!S!D2", 0), unit_in="mm", unit_out="in"), CELLS)
    assert r.value == pytest.approx(4.92126, rel=1e-5)
    assert r.unit == "in"
    assert "= 125 mm = 4.9213 in" in r.working


def test_batch_time_with_function():
    r = compute(
        _comp(
            "sum(c1, c2, c3) * c4",
            ("c1", "f!S!F2", 0),
            ("c2", "f!S!F3", 0),
            ("c3", "f!S!F4", 0),
            ("c4", "f!S!L2", 0),
        ),
        CELLS,
    )
    assert r.value == 600


def test_constants_are_reported():
    r = compute(_comp("c1 / 60", ("c1", "f!S!F2", 0)), CELLS)
    assert r.constants == [60.0]


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo hi')",
        "c1.__class__",
        "[c1 for x in range(10)]",
        "c1 ** 99999",
        "lambda: 1",
        "open('x')",
        "",
    ],
)
def test_rejects_unsafe_expressions(expr):
    with pytest.raises(ComputeError):
        compute(_comp(expr, ("c1", "f!S!F2", 0)), CELLS)


def test_rejects_unknown_cell_and_missing_number():
    with pytest.raises(ComputeError, match="unknown fact"):
        compute(_comp("c1", ("c1", "f!S!Z99", 0)), CELLS)
    with pytest.raises(ComputeError, match="no number"):
        compute(_comp("c1", ("c1", "f!S!C2", 0)), CELLS)


def test_conversion_requires_known_input_unit():
    with pytest.raises(ComputeError, match="input unit is not stated"):
        compute(_comp("c1", ("c1", "f!S!L2", 0), unit_out="in"), CELLS)


def test_incompatible_units():
    with pytest.raises(ComputeError):
        convert(5, "min", "mm")


def test_surface_finish_conversion():
    assert convert(1.6, "µm", "µin") == pytest.approx(62.99, rel=1e-3)
