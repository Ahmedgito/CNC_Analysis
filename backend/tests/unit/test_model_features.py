"""Geometry facts measured from IGES models: the samples, and exports in other shapes.

Expected values come from the answer keys (bounding boxes) and the drawings, never from the
app's own output.
"""

from __future__ import annotations

import hashlib

import pytest

from app.domain.model import ModelSlice
from app.geometry.errors import ModelLimitError, UnreadableModelError
from app.geometry.kernel import process_model, revision_from_name
from tests.fixtures import models as fx


def measure(data: bytes, name: str = "part.igs", artifacts: bool = False) -> ModelSlice:
    return process_model(data, name, hashlib.sha256(data).hexdigest(), artifacts=artifacts).slice


def nums(m: ModelSlice, fid: str) -> dict[str, float]:
    f = m.feature(fid)
    assert f is not None, f"{fid} missing; features: {[x.feature_id for x in m.features]}"
    return f.numbers


@pytest.fixture(scope="module")
def samples() -> dict[str, ModelSlice]:
    return {p.name: measure(p.read_bytes(), p.name) for p in sorted(fx.DATA.glob("*.igs"))}


# --------------------------------------------------------------------------- the samples


@pytest.mark.parametrize(
    ("name", "bbox"),
    [
        ("2280_flange.igs", (120, 120, 20)),
        ("2281_shaft.igs", (30, 30, 200)),
        ("2282_bracket.igs", (101.6, 63.5, 9.525)),
        ("2283_bushing.igs", (48, 48, 40)),
        ("3001_gear_blank.igs", (80, 80, 15)),
        ("3002_coupling_hub_RevB.igs", (55, 55, 40)),
        ("3003_base_plate.igs", (200, 120, 15)),
        ("3004_shaft_collar.igs", (50.8, 50.8, 19.05)),
    ],
)
def test_envelope_matches_the_answer_key(samples, name, bbox):
    m = samples[name]
    assert m.topology == "solid" and m.valid and m.bodies == 1
    env = nums(m, "envelope")
    got = (
        (env["diameter_mm"], env["diameter_mm"], env["length_mm"])
        if m.form == "turned"
        else (env["l_mm"], env["w_mm"], env["t_mm"])
    )
    assert sorted(got) == pytest.approx(sorted(bbox), abs=1e-3)


def test_flange_features(samples):
    m = samples["2280_flange.igs"]
    assert m.form == "turned"
    assert nums(m, "od_1")["diameter_mm"] == pytest.approx(120)
    assert nums(m, "bore")["diameter_mm"] == pytest.approx(40)
    pattern = nums(m, "hole_pattern_1")
    assert pattern["count"] == 6 and pattern["diameter_mm"] == pytest.approx(10)
    assert pattern["pcd_mm"] == pytest.approx(90)
    assert m.feature("hole_pattern_1").value == "6 × Ø10 through on Ø90 PCD"
    # π·20·(60² − 20²) − 6·π·5²·20
    assert nums(m, "volume")["volume_mm3"] == pytest.approx(191637.15, abs=0.05)


def test_stepped_shaft(samples):
    m = samples["2281_shaft.igs"]
    assert nums(m, "od_1") == pytest.approx({"diameter_mm": 30, "length_mm": 160})
    assert nums(m, "step_1") == pytest.approx({"diameter_mm": 25, "length_mm": 40})
    assert m.feature("holes").value == "none"


def test_rectangular_holes_are_a_grid_not_a_pcd(samples):
    m = samples["3003_base_plate.igs"]
    p = nums(m, "hole_pattern_1")
    assert p["count"] == 4 and p["diameter_mm"] == pytest.approx(14)
    assert "pcd_mm" not in p
    assert (p["pitch_x_mm"], p["pitch_y_mm"]) == pytest.approx((160, 80))


def test_radial_hole_into_the_bore_is_through(samples):
    m = samples["3002_coupling_hub_RevB.igs"]
    hole = m.feature("hole_1")
    assert hole.value == "Ø5 radial through"
    assert "depth_mm" not in hole.numbers
    assert m.revision == "B"


def test_inch_part_is_measured_in_mm(samples):
    m = samples["2282_bracket.igs"]
    assert nums(m, "thickness")["thickness_mm"] == pytest.approx(9.525)
    assert nums(m, "hole_pattern_1")["diameter_mm"] == pytest.approx(6.35)


def test_part_number_from_the_file_name(samples):
    m = samples["3001_gear_blank.igs"]
    assert m.part_number == "3001" and m.part_number_source == "filename"


def test_header_facts_are_exact(samples):
    units = samples["2280_flange.igs"].feature("hdr.units")
    assert units.value == "mm" and units.confidence == "exact"


# ---------------------------------------------------------------- other exporter shapes


def test_exact_solid_export_gives_the_same_facts(samples):
    m = measure(fx.write_iges(fx.flange(), brep=True), "2280_flange.igs")
    a, b = samples["2280_flange.igs"], m
    for fid in ("od_1", "bore", "hole_pattern_1", "volume"):
        assert nums(b, fid) == pytest.approx(nums(a, fid), rel=1e-6)


def test_inch_file_is_converted():
    m = measure(fx.write_iges(fx.flange(), unit="IN"))
    assert m.header.units == "in"
    assert nums(m, "od_1")["diameter_mm"] == pytest.approx(120, abs=1e-3)
    assert nums(m, "hole_pattern_1")["pcd_mm"] == pytest.approx(90, abs=1e-3)


def test_rotated_and_moved_model_is_measured_in_its_own_frame():
    m = measure(fx.write_iges(fx.rotated(fx.flange())))
    assert m.form == "turned"
    env = nums(m, "envelope")
    assert (env["diameter_mm"], env["length_mm"]) == pytest.approx((120, 20), abs=1e-3)
    assert nums(m, "hole_pattern_1")["pcd_mm"] == pytest.approx(90, abs=1e-3)


def test_rotated_plate_is_measured_exactly():
    """The kernel's 'optimal' oriented box is approximate (0.2 mm long on this plate); the frame
    comes from the flat faces instead."""
    m = measure(fx.write_iges(fx.rotated(fx.plate_with_features()), brep=True))
    env = nums(m, "envelope")
    assert (env["l_mm"], env["w_mm"], env["t_mm"]) == pytest.approx((200, 100, 20), abs=1e-3)
    row = next(f for f in m.features if f.kind == "hole_pattern" and f.numbers.get("count") == 3)
    assert "in a row at 30 mm pitch" in row.value


def test_nurbs_surfaces_are_recognised_and_labelled_inferred():
    m = measure(fx.write_iges(fx.nurbs(fx.bushing()), brep=True))
    od = m.feature("od_1")
    assert od is not None and od.numbers["diameter_mm"] == pytest.approx(48, abs=1e-3)
    assert od.confidence == "inferred" and "recognised" in od.method
    assert nums(m, "bore")["diameter_mm"] == pytest.approx(30, abs=1e-3)


def test_blind_hole_row_and_counterbore():
    m = measure(fx.write_iges(fx.plate_with_features(), brep=True))
    values = {f.feature_id: f.value for f in m.features}
    row = next(f for f in m.features if f.kind == "hole_pattern" and f.numbers.get("count") == 3)
    assert row.numbers["pitch_x_mm"] == pytest.approx(30) or row.numbers[
        "pitch_y_mm"
    ] == pytest.approx(30)
    assert "in a row at 30 mm pitch" in row.value
    blind = next(f for f in m.features if f.kind == "hole" and "blind" in f.value)
    assert blind.numbers["depth_mm"] == pytest.approx(12) and blind.numbers[
        "diameter_mm"
    ] == pytest.approx(10)
    cb = next(f for f in m.features if "counterbored" in f.value)
    assert cb.numbers["cbore_diameter_mm"] == pytest.approx(15) and cb.numbers[
        "cbore_depth_mm"
    ] == pytest.approx(6)
    assert m.form == "prismatic", values


def test_chamfers_are_reported():
    m = measure(fx.write_iges(fx.chamfered_shaft(), brep=True))
    chamfer = m.feature("chamfer_1")
    assert chamfer is not None and chamfer.numbers["count"] == 2
    assert chamfer.numbers["length_mm"] == pytest.approx(1, abs=1e-3)
    assert chamfer.numbers["angle_deg"] == pytest.approx(45, abs=0.01)


def test_off_axis_boss_on_a_plate():
    m = measure(fx.write_iges(fx.fused_pin_plate(), brep=True))
    boss = m.feature("boss_1")
    assert boss is not None and boss.numbers["diameter_mm"] == pytest.approx(12)
    assert m.form == "prismatic"


def test_several_solids_are_flagged():
    m = measure(fx.write_iges(fx.two_blocks(), brep=True))
    assert m.topology == "multi_solid" and m.bodies == 2 and not m.valid
    assert any("separate solids" in w for w in m.warnings)


def test_open_shell_has_no_volume():
    m = measure(fx.write_iges(fx.open_box()))
    assert m.topology == "open_shell"
    assert m.feature("volume") is None
    assert m.feature("envelope").confidence == "inferred"
    assert any("do not close" in w for w in m.warnings)


def test_curves_only():
    m = measure(fx.write_iges(fx.wire_frame()))
    assert m.topology == "wireframe"
    assert m.feature("envelope").confidence == "inferred"
    assert sorted(nums(m, "envelope").values()) == pytest.approx([10, 60, 80], abs=1e-3)


def test_artifacts_are_built():
    r = process_model(fx.sample("2280_flange.igs"), "2280_flange.igs", "0" * 64)
    assert set(r.views) == {"front", "top", "right"}
    assert r.meshes[0][:4] == b"glTF" and r.meshes[1][:4] == b"glTF"
    assert 'data-fact-id="2280_flange!m!hole_pattern_1"' in r.views["right"]
    assert r.slice.mesh is not None and r.slice.mesh.face_feature


# ------------------------------------------------------------------------- hostile files


def test_truncated_file_is_unreadable():
    with pytest.raises(UnreadableModelError):
        measure(fx.sample("2280_flange.igs")[:3000])


def test_not_iges_is_unreadable():
    with pytest.raises(UnreadableModelError, match="not an ASCII IGES"):
        measure(b"just some text\n")


def test_size_and_entity_limits():
    data = fx.sample("2280_flange.igs")
    with pytest.raises(ModelLimitError, match="MB"):
        process_model(data, "big.igs", "0" * 64, max_bytes=1000)
    with pytest.raises(ModelLimitError, match="entities"):
        process_model(data, "many.igs", "0" * 64, max_entities=10)


def test_start_section_is_data():
    m = measure(fx.poisoned_start(fx.sample("2283_bushing.igs")), "2283_bushing.igs")
    assert "IGNORE ALL PREVIOUS" in (m.header.start_text or "")
    assert nums(m, "bore")["diameter_mm"] == pytest.approx(30)  # geometry unaffected


@pytest.mark.parametrize(
    ("name", "rev"),
    [
        ("3002_coupling_hub_RevB.igs", "B"),
        ("part-rev-c.igs", "C"),
        ("p_REV2.igs", "2"),
        ("revolver.igs", None),
    ],
)
def test_revision_from_file_name(name, rev):
    assert revision_from_name(name) == rev
