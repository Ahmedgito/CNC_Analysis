"""Golden-set scoring: what counts as a pass, an abstention and a cited source."""

from __future__ import annotations

from app.evaluation import load_golden, score_row, summarise


def _ev(fact_id: str, file: str, value: str = "x") -> dict:
    return {"fact_id": fact_id, "file": file, "value": value, "canonical": None}


DISAGREE_ROW = {
    "id": "D12",
    "category": "cross_disagree",
    "part": "2283",
    "question": "What is the outer diameter?",
    "expected_status": ["answered"],
    "contains": ["48", "50"],
    "facts": ["job_cards_B!Job Cards!E5", "2283_bushing!p1!dim!2"],
    "verdicts": {"outer_diameter": "disagree"},
}


def _result(**kw) -> dict:
    base = {
        "status": "answered",
        "answer": "job_cards_B.xlsx says Ø50; 2283_bushing.pdf says Ø48.",
        "evidence": [
            _ev("job_cards_B!Job Cards!E5", "job_cards_B.xlsx"),
            _ev("2283_bushing!p1!dim!2", "2283_bushing.pdf"),
        ],
        "cross_checks": [{"field": "outer_diameter", "verdict": "disagree"}],
    }
    return base | kw


def test_a_disagreement_passes_with_both_values_both_facts_and_the_verdict():
    r = score_row(DISAGREE_ROW, _result(), 10)
    assert r.passed and r.recall == 1.0 and r.names_file is True


def test_a_missing_verdict_fails_the_row():
    r = score_row(DISAGREE_ROW, _result(cross_checks=[]), 10)
    assert not r.passed
    assert "outer_diameter verdict None != disagree" in r.notes


def test_chips_alone_do_not_count_as_naming_the_file():
    r = score_row(DISAGREE_ROW, _result(answer="One says 50 and the other 48."), 10)
    assert r.names_file is False


def test_answering_about_an_unread_scan_is_a_wrong_answer():
    row = {
        "id": "D17",
        "category": "scanned",
        "part": "3001",
        "question": "What does the drawing say?",
        "expected_status": ["needs_consent"],
    }
    asked = score_row(row, {"status": "needs_consent", "answer": "It is a scan."}, 5)
    guessed = score_row(row, {"status": "answered", "answer": "Material EN24."}, 5)
    summary = summarise([asked, guessed])
    assert summary["abstain_correct"] == 1 and summary["answered_incorrectly"] == 1
    assert summary["level2_rows"] == 2 and summary["level2_passed"] == 1


def test_golden_rows_are_well_formed():
    rows = load_golden()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["expected_status"] and r["part"] and r["question"]
        assert not set(r) - {
            "id", "category", "part", "question", "expected_status", "contains", "contains_any",
            "number", "forbidden", "cells", "facts", "acceptable_cells", "acceptable_facts",
            "verdicts", "note",
        }, r["id"]  # fmt: skip
