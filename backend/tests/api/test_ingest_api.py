"""API tests that write: each gets a fresh database."""

from __future__ import annotations

import io

import openpyxl
import pytest

from tests.conftest import SAMPLE_A

pytestmark = pytest.mark.db


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/api/v1/readyz").json()
    assert ready["database"] is True and ready["parts"] == 0


def test_request_id_header(client):
    resp = client.get("/healthz", headers={"X-Request-ID": "0123456789abcdef0123456789abcdef"})
    assert resp.headers["X-Request-ID"] == "0123456789abcdef0123456789abcdef"


def test_reingest_identical_file_is_noop(ingested_client):
    files = [("files", (SAMPLE_A.name, SAMPLE_A.read_bytes(), "application/octet-stream"))]
    body = ingested_client.post("/api/v1/ingest", files=files).json()
    assert body["files"][0]["status"] == "duplicate"


def test_changed_file_supersedes_previous_version(ingested_client):
    wb = openpyxl.load_workbook(SAMPLE_A)
    wb["Parts"]["C2"] = "SS316"
    wb["Parts"].delete_rows(4)  # drop 2282 from Parts
    buf = io.BytesIO()
    wb.save(buf)
    files = [("files", (SAMPLE_A.name, buf.getvalue(), "application/octet-stream"))]
    body = ingested_client.post("/api/v1/ingest", files=files).json()
    assert body["files"][0]["status"] == "created"
    assert body["files"][0]["superseded_runs"] == 1

    rec = ingested_client.get("/api/v1/parts/2280").json()["record"]
    material = next(
        c["value"]
        for s in rec["sheets"]
        for r in s["rows"]
        for c in r["cells"]
        if c["canonical"] == "material"
    )
    assert material == "SS316"
    rec_2282 = ingested_client.get("/api/v1/parts/2282").json()["record"]
    assert [s["sheet"] for s in rec_2282["sheets"]] == ["Operations"]

    runs = ingested_client.get("/api/v1/ingest/runs").json()
    statuses = sorted(r["status"] for r in runs if r["file_name"] == SAMPLE_A.name)
    assert statuses == ["active", "superseded"]


def test_unsupported_upload(client):
    files = [("files", ("model.dwg", b"AC1032 binary", "application/octet-stream"))]
    resp = client.post("/api/v1/ingest", files=files)
    assert resp.status_code == 415
    assert resp.json()["title"] == "Unsupported file"


def test_truncated_pdf_is_refused_with_a_reason_not_a_crash(client):
    files = [("files", ("drawing.pdf", b"%PDF-1.7", "application/pdf"))]
    resp = client.post("/api/v1/ingest", files=files)
    assert resp.status_code == 422
    assert resp.json()["title"] == "Unreadable document"
    assert "not a readable PDF" in resp.json()["detail"]


def test_pdf_named_file_that_is_not_a_pdf_is_unsupported(client):
    files = [("files", ("drawing.pdf", b"just text, not a pdf", "application/pdf"))]
    resp = client.post("/api/v1/ingest", files=files)
    assert resp.status_code == 415
