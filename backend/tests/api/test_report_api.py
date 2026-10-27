"""The part report: one PDF with every source, the cross-check, the record, drawings, models and
the conversation, each value naming the file and place it came from."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import create_app
from tests.conftest import _truncate, make_test_settings

pytestmark = pytest.mark.db

DATA = Path(__file__).resolve().parents[3] / "data"
ALL_FILES = sorted(p for p in DATA.iterdir() if p.suffix in (".xlsx", ".pdf", ".igs"))


@pytest.fixture(scope="module")
def full(db_url: str, tmp_path_factory) -> Iterator[TestClient]:
    _truncate(db_url)
    settings = make_test_settings(db_url, tmp_path_factory.mktemp("report"))
    with TestClient(create_app(settings)) as c:
        resp = c.post(
            "/api/v1/ingest",
            files=[
                ("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in ALL_FILES
            ],
        )
        assert resp.status_code == 200, resp.text
        yield c


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def test_report_is_a_pdf_download(full):
    resp = full.get("/api/v1/parts/2283/report.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == 'attachment; filename="part-2283-report.pdf"'
    assert resp.content.startswith(b"%PDF")


def test_report_covers_every_source_and_names_where_values_came_from(full):
    text = _text(full.get("/api/v1/parts/2283/report.pdf").content)
    for expected in (
        "Part 2283",
        "Bushing",
        # sources, by file
        "job_cards_B.xlsx",
        "2283_bushing.pdf",
        "2283_bushing.igs",
        # the planted disagreements, with the odd one out
        "Material disagrees",
        "Outer diameter disagrees",
        "odd one out",
        # exact places: a cell, a drawing region, a model feature
        "Job Cards › C5",
        "p1 › Title block › MATERIAL",
        "Model › Outer diameter",
        # drawing facts and measured features
        "BRONZE C93200",
        "Measured features",
        "How to read this report",
    ):
        assert expected in text, expected


def test_report_for_a_part_without_drawing_or_model(full):
    resp = full.get("/api/v1/parts/2284/report.pdf")
    assert resp.status_code == 200, resp.text
    text = _text(resp.content)
    assert "No drawing was found for this part." in text
    assert "No 3D model was found for this part." in text


def test_report_for_an_unread_scan_says_so(full):
    text = _text(full.get("/api/v1/parts/3001/report.pdf").content)
    assert "Scanned, not read" in text
    assert "has not been read" in text


def test_report_includes_the_conversation(full):
    answer = full.post(
        "/api/v1/parts/2280/ask", json={"question": "What material is it made of?"}
    ).json()
    conv = answer["conversation_id"]
    resp = full.get("/api/v1/parts/2280/report.pdf", params={"conversation": conv})
    assert resp.status_code == 200, resp.text
    text = _text(resp.content)
    assert "Questions and answers" in text
    assert "Q1. What material is it made of?" in text


def test_report_refuses_a_conversation_about_another_part(full):
    answer = full.post(
        "/api/v1/parts/2280/ask", json={"question": "What material is it made of?"}
    ).json()
    resp = full.get(
        "/api/v1/parts/2281/report.pdf", params={"conversation": answer["conversation_id"]}
    )
    assert resp.status_code == 404
    assert resp.json()["title"] == "Conversation not found"


def test_report_for_unknown_part_is_problem_json(full):
    resp = full.get("/api/v1/parts/9999/report.pdf")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
