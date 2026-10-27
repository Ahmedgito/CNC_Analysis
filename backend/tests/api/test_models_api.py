"""Level 3 end to end: IGES models ingested beside workbooks and drawings, measured, served to
the viewer, and cross-checked three ways."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import _truncate, make_test_settings
from tests.fixtures.models import poisoned_start

DATA = Path(__file__).resolve().parents[3] / "data"
ALL_FILES = sorted(p for p in DATA.iterdir() if p.suffix in (".xlsx", ".pdf", ".igs"))


def _upload(client: TestClient, files: list[tuple[str, bytes]]):
    return client.post(
        "/api/v1/ingest",
        files=[("files", (n, b, "application/octet-stream")) for n, b in files],
    )


@pytest.fixture(scope="module")
def full(db_url: str, tmp_path_factory) -> Iterator[tuple[TestClient, dict]]:
    _truncate(db_url)
    settings = make_test_settings(db_url, tmp_path_factory.mktemp("models"))
    with TestClient(create_app(settings)) as c:
        resp = _upload(c, [(p.name, p.read_bytes()) for p in ALL_FILES])
        assert resp.status_code == 200, resp.text
        yield c, resp.json()


def _record(client: TestClient, part: str) -> dict:
    resp = client.get(f"/api/v1/parts/{part}")
    assert resp.status_code == 200, resp.text
    return resp.json()["record"]


def _check(rec: dict, field: str) -> dict:
    return next(c for c in rec["cross_checks"] if c["field"] == field)


# ------------------------------------------------------------------------------- ingest


def test_ingest_reports_models(full):
    _, body = full
    by_name = {f["file_name"]: f for f in body["files"]}
    m = by_name["2280_flange.igs"]
    assert m["kind"] == "model" and m["status"] == "created"
    assert m["model"]["linked_part"] == "2280" and m["model"]["topology"] == "solid"
    assert m["model"]["valid"] is True and m["model"]["units"] == "mm"
    assert set(m["model"]["views"]) == {"front", "top", "right"}


def test_sources_show_the_model(full):
    client, _ = full
    parts = {p["part_key"]: p for p in client.get("/api/v1/parts").json()["parts"]}
    for key in ("2280", "2281", "2282", "2283", "3001", "3002", "3003", "3004-A"):
        assert parts[key]["sources"]["iges"]["available"] is True, key
    assert parts["2284"]["sources"]["iges"]["available"] is False
    assert "2280_flange.igs" in parts["2280"]["files"]


def test_record_carries_measured_features(full):
    client, _ = full
    rec = _record(client, "2280")
    model = rec["models"][0]
    assert model["file"] == "2280_flange.igs" and model["form"] == "turned"
    values = {f["feature_id"]: f["value"] for f in model["features"]}
    assert values["hole_pattern_1"] == "6 × Ø10 through on Ø90 PCD"
    assert values["od_1"].startswith("Ø120")


# ------------------------------------------------------------------------ three-way checks


def test_2283_job_card_is_the_odd_one_out(full):
    client, _ = full
    od = _check(_record(client, "2283"), "outer_diameter")
    assert od["verdict"] == "disagree"
    assert od["pairs"] == {"excel~pdf": "disagree", "excel~iges": "disagree", "pdf~iges": "agree"}
    assert od["odd_one_out"] == "excel" and od["dissent"] == ["job_cards_B!Job Cards!E5"]
    assert od["iges"] == ["2283_bushing!m!od_1"]
    assert "48" in od["detail"] and "50" in od["detail"]
    assert {s["source"] for s in od["sides"]} == {"excel", "pdf", "iges"}


def test_3003_part_card_dissents_alone(full):
    client, _ = full
    holes = _check(_record(client, "3003"), "holes")
    assert holes["verdict"] == "disagree" and holes["pairs"]["pdf~iges"] == "agree"
    assert holes["dissent"] == ["messy_workshop_export!Part Card 3003!B7"]
    assert holes["odd_one_out"] is None  # another spreadsheet cell agrees with the drawing


def test_3002_thread_matches_the_tap_drill(full):
    client, _ = full
    thread = _check(_record(client, "3002"), "thread")
    assert thread["verdict"] == "equivalent_by_convention"
    assert "tap drill for M6" in thread["detail"]


@pytest.mark.parametrize(
    ("part", "field", "verdict"),
    [
        ("2282", "thickness", "agree_after_conversion"),
        ("2282", "holes", "agree_after_conversion"),
        ("3004", "outer_diameter", "agree_after_conversion"),
        ("2280", "holes", "agree"),
        ("2280", "stock", "consistent"),
        ("2281", "chamfer", "not_modelled"),
        ("3001", "outer_diameter", "agree"),  # the drawing is an unread scan; sheet and model agree
    ],
)
def test_planted_verdicts(full, part, field, verdict):
    client, _ = full
    assert _check(_record(client, part), field)["verdict"] == verdict


def test_no_false_disagreements(full):
    client, _ = full
    planted = {("2283", "material"), ("2283", "outer_diameter"), ("3003", "holes")}
    for part in ("2280", "2281", "2282", "2283", "3001", "3002", "3003", "3004"):
        for c in _record(client, part)["cross_checks"]:
            if c["verdict"] == "disagree":
                assert (part, c["field"]) in planted, (part, c["field"], c["detail"])


def test_material_says_the_model_holds_none(full):
    client, _ = full
    mat = _check(_record(client, "2280"), "material")
    iges = next(s for s in mat["sides"] if s["source"] == "iges")
    assert iges["facts"] == [] and "does not record the material" in iges["note"]


# ------------------------------------------------------------------------------ artifacts


def test_mesh_is_served(full):
    client, _ = full
    for lod in (0, 1):
        resp = client.get(f"/api/v1/parts/2280/models/2280_flange.igs/mesh.glb?lod={lod}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "model/gltf-binary"
        assert resp.content[:4] == b"glTF" and "immutable" in resp.headers["cache-control"]
    assert client.get("/api/v1/parts/2280/models/2280_flange.igs/mesh.glb?lod=5").status_code == 422
    assert client.get("/api/v1/parts/2280/models/other.igs/mesh.glb").status_code == 404


def test_projection_is_served_safely(full):
    client, _ = full
    resp = client.get("/api/v1/parts/2280/models/2280_flange.igs/views/right.svg")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("image/svg+xml")
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert 'data-fact-id="2280_flange!m!hole_pattern_1"' in resp.text
    assert client.get("/api/v1/parts/2280/models/2280_flange.igs/views/iso.svg").status_code == 422


# ---------------------------------------------------------------------------- edge cases


def test_bad_model_files(full):
    client, _ = full
    truncated = (DATA / "2280_flange.igs").read_bytes()[:3000]
    resp = _upload(client, [("cut.igs", truncated)])
    assert resp.status_code == 422 and resp.json()["title"] == "Unreadable model"
    resp = _upload(client, [("notes.igs", b"just text, not a model\n")])
    assert resp.status_code == 415
    resp = _upload(client, [("part.step", b"ISO-10303-21;\nHEADER;\n")])
    assert resp.status_code == 415 and "STEP" in resp.json()["detail"]


def test_same_bytes_again_is_a_duplicate(full):
    client, _ = full
    resp = _upload(client, [("2283_bushing.igs", (DATA / "2283_bushing.igs").read_bytes())])
    assert resp.json()["files"][0]["status"] == "duplicate"


def test_model_without_a_part_number_is_kept_unlinked(full):
    client, _ = full
    data = poisoned_start((DATA / "2281_shaft.igs").read_bytes())  # new bytes, new sha
    resp = _upload(client, [("shaft_model.igs", data)])
    assert resp.status_code == 200
    assert resp.json()["files"][0]["model"]["linked_part"] is None
    unlinked = client.get("/api/v1/models/unlinked").json()
    assert [m["file"] for m in unlinked] == ["shaft_model.igs"]


def test_older_model_revision_is_history(db_url, tmp_path):
    _truncate(db_url)
    hub = (DATA / "3002_coupling_hub_RevB.igs").read_bytes()
    with TestClient(create_app(make_test_settings(db_url, tmp_path))) as c:
        files = [
            ("3002_coupling_hub_RevB.igs", hub),
            ("3002_coupling_hub_RevA.igs", poisoned_start(hub)),
            ("messy_workshop_export.xlsx", (DATA / "messy_workshop_export.xlsx").read_bytes()),
        ]
        assert _upload(c, files).status_code == 200
        rec = _record(c, "3002")
    assert [m["file"] for m in rec["models"]] == [
        "3002_coupling_hub_RevB.igs",
        "3002_coupling_hub_RevA.igs",
    ]
    assert all(f["stale"] for f in rec["models"][1]["features"])
    assert rec["sources"]["iges"]["current_revision"] == "B"
    assert _check(rec, "bore")["iges"] == ["3002_coupling_hub_RevB!m!bore"]
