from __future__ import annotations

import pytest

from app.services.ask_service import fill_result
from app.services.compute import ComputeResult


def _comp(value: float, unit: str | None) -> ComputeResult:
    display = f"{value:g}" + (f" {unit}" if unit else "")
    return ComputeResult(value=value, display=display, unit=unit, working="", inputs=[])


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Total setup is {result}.", "Total setup is 12 min."),
        ("Total setup is {result} minutes.", "Total setup is 12 minutes."),
        ("It takes {result} min in total.", "It takes 12 min in total."),
        ("{result} (sum of three operations)", "12 min (sum of three operations)"),
    ],
)
def test_unit_not_duplicated(answer, expected):
    assert fill_result(answer, _comp(12, "min")) == expected


def test_inch_conversion():
    assert fill_result("That is {result} inches.", _comp(4.9213, "in")) == "That is 4.9213 inches."
