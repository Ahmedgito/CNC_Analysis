"""Read-only API tests against a database seeded once per module with both sample workbooks."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.db


def test_ingest_and_list(seeded_client):
    body = seeded_client.get("/api/v1/parts").json()
    assert [p["part_key"] for p in body["parts"]] == ["2280", "2281", "2282", "2283", "2284"]
    flange = body["parts"][0]
    assert flange["description"] == "Flange"
    assert flange["sources"]["excel"]["available"] is True
    assert flange["sources"]["pdf"]["available"] is False


def test_search(seeded_client):
    body = seeded_client.get("/api/v1/parts", params={"q": "bush"}).json()
    assert [p["part_key"] for p in body["parts"]] == ["2283"]


@pytest.mark.parametrize("pn", ["2280", "2280.0", " 2280 ", "2280%20"])
def test_tolerant_lookup(seeded_client, pn):
    resp = seeded_client.get(f"/api/v1/parts/{pn}")
    assert resp.status_code == 200, resp.text
    rec = resp.json()["record"]
    assert rec["part_key"] == "2280"
    assert {s["sheet"] for s in rec["sheets"]} == {"Parts", "Operations"}


def test_unknown_part_is_problem_json_with_suggestions(seeded_client):
    resp = seeded_client.get("/api/v1/parts/2289")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["title"] == "Part not found"
    assert {"2280", "2281", "2282", "2283", "2284"} & set(body["suggestions"])
    assert body["request_id"]


def test_record_from_second_workbook(seeded_client):
    rec = seeded_client.get("/api/v1/parts/2284").json()["record"]
    assert rec["sources"]["excel"]["files"] == ["job_cards_B.xlsx"]
    assert {s["sheet"] for s in rec["sheets"]} == {"Job Cards", "Tooling"}
