"""Level 2 end to end: drawings ingested beside workbooks, cited in answers, cross-checked,
and scanned drawings read only after the user agrees."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm.vision import StaticVision, VisionNote, VisionPage, VisionReading, VisionTitleField
from app.main import create_app
from tests.conftest import _truncate, make_test_settings

DATA = Path(__file__).resolve().parents[3] / "data"
ALL_FILES = sorted(p for p in DATA.iterdir() if p.suffix in (".xlsx", ".pdf"))


def _ingest_all(client: TestClient) -> dict:
    files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in ALL_FILES]
    resp = client.post("/api/v1/ingest", files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ask(client: TestClient, part: str, question: str, conversation_id: str | None = None) -> dict:
    body = {"question": question, "conversation_id": conversation_id}
    resp = client.post(f"/api/v1/parts/{part}/ask", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


SCAN_READING = VisionReading(
    pages=[
        VisionPage(
            page=1,
            legible=True,
            title_block=[
                VisionTitleField(label="PART NO", value="3001"),
                VisionTitleField(label="MATERIAL", value="EN24"),
                VisionTitleField(label="UNITS", value="MM"),
            ],
            notes=[VisionNote(number=1, text="ALL DIMENSIONS IN MM.")],
            dimensions=["Ø80", "Ø25 BORE", "15"],
            other_text=[],
        )
    ],
    reason="clear scan",
)


@pytest.fixture(scope="module")
def full(db_url: str, tmp_path_factory) -> Iterator[tuple[TestClient, dict]]:
    """Both datasets (workbooks and drawings) ingested once. Read-only tests only."""
    _truncate(db_url)
    settings = make_test_settings(db_url, tmp_path_factory.mktemp("full"))
    with TestClient(create_app(settings)) as c:
        yield c, _ingest_all(c)


@pytest.fixture
def scan_client(settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, vision=StaticVision(SCAN_READING))) as c:
        _ingest_all(c)
        yield c


# ------------------------------------------------------------------------------- ingest


def test_ingest_reports_drawings(full):
    _, body = full
    by_name = {f["file_name"]: f for f in body["files"]}
    flange = by_name["2280_flange.pdf"]
    assert flange["kind"] == "drawing" and flange["status"] == "created"
    assert flange["drawing"]["linked_part"] == "2280"
    assert flange["drawing"]["part_number_source"] == "title_block"
    assert {"material", "units", "revision"} <= set(flange["drawing"]["title_block_fields"])
    scan = by_name["3001_gear_blank_scan.pdf"]["drawing"]
    assert scan["scanned"] is True and scan["readable"] is False


def test_parts_list_shows_both_datasets_and_pdf_status(full):
    client, _ = full
    parts = {p["part_key"]: p for p in client.get("/api/v1/parts").json()["parts"]}
    assert {"2280", "2283", "2284", "3001", "3002", "3003", "3004-A"} <= set(parts)
    assert not any("PLATES" in k or k == "MATERIAL" for k in parts)
    assert parts["2280"]["sources"]["pdf"]["available"] is True
    assert parts["2284"]["sources"]["pdf"]["available"] is False
    assert parts["3001"]["sources"]["pdf"]["scanned"] == ["3001_gear_blank_scan.pdf"]


@pytest.mark.parametrize(
    ("typed", "key"),
    [("P-3001", "3001"), ("3001", "3001"), ("003003", "3003"), ("3004", "3004-A")],
)
def test_every_spelling_of_a_part_resolves(full, typed, key):
    client, _ = full
    resp = client.get(f"/api/v1/parts/{typed}")
    assert resp.status_code == 200
    assert resp.json()["record"]["part_key"] == key


def test_record_carries_drawing_and_cross_checks(full):
    client, _ = full
    rec = client.get("/api/v1/parts/2283").json()["record"]
    assert rec["drawings"][0]["file"] == "2283_bushing.pdf"
    verdicts = {c["field"]: c["verdict"] for c in rec["cross_checks"]}
    assert verdicts["material"] == "disagree" and verdicts["outer_diameter"] == "disagree"


def test_drawing_page_renders_as_png(full):
    client, _ = full
    resp = client.get("/api/v1/parts/2280/drawings/2280_flange.pdf/pages/1.png?dpi=60")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")
    assert "immutable" in resp.headers["cache-control"]
    assert client.get("/api/v1/parts/2280/drawings/2280_flange.pdf/pages/9.png").status_code == 404
    assert client.get("/api/v1/parts/2280/drawings/other.pdf/pages/1.png").status_code == 404


# ------------------------------------------------------------------------------- answers


def test_answer_cites_both_files_and_reports_the_disagreement(full):
    client, _ = full
    r = _ask(client, "2283", "What is the outer diameter?")
    assert r["status"] == "answered"
    ids = {e["fact_id"] for e in r["evidence"]}
    assert "2283_bushing!p1!dim!2" in ids  # Ø48 on the drawing
    assert "job_cards_B!Job Cards!E5" in ids  # Ø50 x 40 in the job card
    pdf = next(e for e in r["evidence"] if e["source"] == "pdf")
    assert pdf["file"] == "2283_bushing.pdf" and pdf["page"] == 1 and pdf["bbox"]
    assert pdf["locator"].startswith("p1 › Dimension")
    assert "2283_bushing.pdf" in r["answer"] and "job_cards_B.xlsx" in r["answer"]
    assert any(
        c["field"] == "outer_diameter" and c["verdict"] == "disagree" for c in r["cross_checks"]
    )


def test_title_block_pointer_is_followed(full):
    client, _ = full
    r = _ask(client, "3003", "What material is it?")
    ids = {e["fact_id"] for e in r["evidence"]}
    assert "3003_base_plate!p1!note!3" in ids


def test_no_drawing_means_not_found(full):
    client, _ = full
    r = _ask(client, "2284", "What does the drawing title block say?")
    assert r["status"] == "not_found"
    assert "no PDF drawing" in r["answer"]
    assert r["sources"]["pdf"]["available"] is False


def test_superseded_revision_is_never_the_answer(full):
    client, _ = full
    r = _ask(client, "3002", "What is the bore?")
    assert r["status"] == "answered"
    assert "Ø20 BORE" in r["answer"]
    assert not any(e["stale"] for e in r["evidence"])


# ------------------------------------------------------------------------ scanned drawings


def test_scanned_drawing_needs_consent_with_an_action(full):
    client, _ = full
    r = _ask(client, "3001", "What does the drawing say?")
    assert r["status"] == "needs_consent"
    assert "scanned image" in r["answer"]
    assert r["actions"] == [
        {
            "id": "read_scan",
            "file": "3001_gear_blank_scan.pdf",
            "label": "Read 3001_gear_blank_scan.pdf with the vision model",
            "reply": "Yes, read the scanned drawing.",
        }
    ]


def test_spreadsheet_answers_still_offer_to_read_the_scan(full):
    client, _ = full
    r = _ask(client, "3001", "What material is it?")
    assert r["status"] == "answered" and "EN24" in r["answer"]
    assert not any(e["value"] == "EN19" for e in r["evidence"])  # the archive row is history
    assert r["actions"] and any("scanned image" in w for w in r["warnings"])


def test_yes_reads_the_scan_and_answers_the_original_question(scan_client):
    first = _ask(scan_client, "3001", "What does the drawing say?")
    assert first["status"] == "needs_consent"
    second = _ask(scan_client, "3001", "Yes, read the scanned drawing.", first["conversation_id"])
    assert second["status"] == "answered"
    vision = [e for e in second["evidence"] if e["confidence"] == "vision"]
    assert vision and all(e["source"] == "pdf" for e in vision)
    assert second["question"] == "Yes, read the scanned drawing."
    assert second["actions"] == []  # nothing left to read
    rec = scan_client.get("/api/v1/parts/3001").json()["record"]
    drawing = rec["drawings"][0]
    assert drawing["extraction"] == "vision" and drawing["readable"] is True
    assert drawing["scanned"] is True  # still a scan; its values stay labelled as vision-read
    calls = scan_client.get("/api/v1/admin/llm-calls").json()
    assert any(c["provider"] == "offline-vision:vision" for c in calls)


def test_no_without_a_pending_offer_is_just_a_question(scan_client):
    r = _ask(scan_client, "2280", "Yes")
    assert r["status"] in ("clarify", "not_found", "answered")
    assert r["actions"] == []


def test_read_scan_endpoint_without_a_vision_model_is_503(db_url, tmp_path):
    _truncate(db_url)
    settings = make_test_settings(db_url, tmp_path, llm_primary_provider="none")
    with TestClient(create_app(settings)) as c:
        _ingest_all(c)
        resp = c.post("/api/v1/parts/3001/drawings/3001_gear_blank_scan.pdf/read-scan")
    assert resp.status_code == 503
    assert resp.json()["title"] == "Vision model unavailable"


def test_read_scan_endpoint_rejects_a_drawing_that_is_not_a_scan(scan_client):
    resp = scan_client.post("/api/v1/parts/2280/drawings/2280_flange.pdf/read-scan")
    assert resp.status_code == 404
