"""IGES structure and Global section, read as text (no kernel)."""

from __future__ import annotations

import pytest

from app.geometry.header import (
    NotIgesError,
    entity_count,
    looks_like_iges,
    parse_global,
    read_header,
)
from app.ingestion.readers import UnsupportedFileError, sniff_format
from tests.fixtures.models import DATA, sample


def _record(text: str, section: str, n: int) -> str:
    return f"{text:<72}{section}{n:>7}\n"


def _iges(global_text: str, start: str = "test model") -> bytes:
    g = [global_text[i : i + 72] for i in range(0, len(global_text), 72)]
    out = _record(start, "S", 1)
    out += "".join(_record(chunk, "G", i + 1) for i, chunk in enumerate(g))
    out += _record(
        "     110       1       0       0       0       0       0       000000000", "D", 1
    )
    out += _record(
        "     110       0       0       1       0                               0", "D", 2
    )
    out += _record("110,0.,0.,0.,1.,0.,0.;", "P", 1)
    out += _record("S      1G      2D      2P      1", "T", 1)
    return out.encode("latin-1")


def test_sample_header():
    h = read_header(sample("2280_flange.igs"))
    assert h.units == "mm" and h.units_flag == 2 and h.units_declared
    assert h.sending_system == "Open CASCADE 8.0"
    assert h.resolution == pytest.approx(1e-7)
    assert entity_count(sample("2280_flange.igs")) == 194


def test_hollerith_strings_may_contain_delimiters():
    fields = parse_global("1H,,1H;,7HA,B;C D,8Hpart.igs,,,,,,,,,1.,2,2HMM;")
    assert fields[3] == "A,B;C D" and fields[4] == "part.igs"
    assert fields[14] == "2" and fields[15] == "MM"


def test_redefined_delimiters():
    fields = parse_global("1H/,1H#,4HPROD/8Hfile.igs/////////1./1/4HINCH#")
    assert fields[3] == "PROD" and fields[4] == "file.igs"
    assert fields[14] == "1"


@pytest.mark.parametrize(
    ("flag_and_name", "units", "declared"),
    [("1,4HINCH", "in", True), ("2,2HMM", "mm", True), ("3,2HCM", "cm", True), (",", "in", False)],
)
def test_units(flag_and_name, units, declared):
    h = read_header(
        _iges(f",,4HPROD,8Hpart.igs,3HSYS,3HPRE,32,38,6,308,15,,1.,{flag_and_name},1,0.01,;")
    )
    assert h.units == units and h.units_declared is declared


def test_sniffing_uses_content_not_the_name():
    data = sample("2281_shaft.igs")
    assert looks_like_iges(data)
    assert sniff_format(data, "renamed.txt") == "iges"  # not mistaken for CSV text
    assert sniff_format((DATA / "2280_flange.pdf").read_bytes(), "x.igs") == "pdf"
    with pytest.raises(UnsupportedFileError, match="not ASCII IGES"):
        sniff_format(b"hello,world\n1,2\n", "part.igs")
    with pytest.raises(UnsupportedFileError, match="STEP"):
        sniff_format(b"ISO-10303-21;\nHEADER;\n", "part.step")


def test_not_iges():
    with pytest.raises(NotIgesError):
        read_header(b"%PDF-1.7 nonsense")
