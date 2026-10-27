"""Spreadsheet-vs-drawing cross-check. Deterministic, no LLM.

For each field both sources can state (material, outer diameter, bore, length, thickness, holes,
thread, tolerance, surface finish) the current spreadsheet values are compared with the current
drawing values after unit reconciliation, and every comparison is stored with the fact ids on
both sides so the UI and the answer can cite them.

Policy (see docs/adr/0007-crosscheck-policy.md): a false "mismatch" costs more trust than a
missed one, so only values that are typed and comparable are compared. Anything ambiguous (a
unit stated on neither side, an unlabelled drawing number) is ``not_comparable``, never
``disagree``. Archived rows, superseded revisions and revision-history pages are excluded.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.drawing import CrossCheck, DrawingFact, DrawingSlice
from app.domain.record import CellRef, PartRecord, RecordRow, SheetSlice
from app.ingestion.cells import normalize_for_match
from app.services.units import (
    MIN_PER,
    NUM,
    close,
    finish_equivalent,
    fmt,
    inline_length_unit,
    normalize_unit,
    parse_number,
    to_mm,
)

_DIA_CHARS = "Ø⌀∅"
_DIA_RE = re.compile(rf"[{_DIA_CHARS}]\s*({NUM})")
_BORE_RE = re.compile(
    rf"\bbore\s*(?:dia(?:meter)?\.?\s*)?[{_DIA_CHARS}]?\s*({NUM})|[{_DIA_CHARS}]\s*({NUM})\s*bore",
    re.IGNORECASE,
)
_HOLES_RE = re.compile(rf"(\d+)\s*[xX×]\s*[{_DIA_CHARS}]\s*({NUM})")
_THREAD_RE = re.compile(r"(?:(\d+)\s*[xX×]\s*)?\bM(\d+(?:\.\d+)?)(?:\s*[xX×]\s*(\d*\.?\d+))?\b")
_TURNED_LEN_RE = re.compile(rf"[{_DIA_CHARS}]\s*{NUM}\s*[xX×]\s*({NUM})")
_NUM_RE = re.compile(rf"(?<![\w.]){NUM}")
# Numbers anywhere in a size string, including after "Ø" (a letter to \w), but not "M6".
_ANY_NUM_RE = re.compile(rf"(?<![A-Za-z0-9.]){NUM}")
_TOL_RE = re.compile(rf"(?:±|\+/-|\+-)\s*({NUM})")
_RA_RE = re.compile(rf"\bRa\s*({NUM})", re.IGNORECASE)
_RMS_RE = re.compile(rf"({NUM})\s*(?:RMS|µin|uin|microinch)", re.IGNORECASE)
_ROW_UNIT_RE = re.compile(
    r"\b(?:dims?|dimensions?|sizes?)\s+(?:are\s+)?in\s+(inch(?:es)?|mm|millimet\w*)",
    re.IGNORECASE,
)
_NONE_WORDS = {"none", "nil", "no holes", "n/a", "na", "-"}
_TIME_FIELDS = {"cycle_time", "setup_time", "run_time"}
_LENGTH_FIELDS = {"finished_size", "raw_stock"}

FIELD_TITLES = {
    "material": "Material",
    "outer_diameter": "Outer diameter",
    "bore": "Bore",
    "length": "Length / overall size",
    "thickness": "Thickness",
    "holes": "Holes",
    "thread": "Threaded holes",
    "tolerance": "General tolerance",
    "surface_finish": "Surface finish",
}


# ------------------------------------------------------------------------------- materials

_FAMILIES = {
    "brass": "brass",
    "bronze": "bronze",
    "steel": "steel",
    "stainless": "stainless steel",
    "aluminum": "aluminium",
    "aluminium": "aluminium",
    "copper": "copper",
    "titanium": "titanium",
    "iron": "cast iron",
    "nylon": "nylon",
    "acetal": "acetal",
    "delrin": "acetal",
    "ptfe": "ptfe",
    "peek": "peek",
}
_STANDARD_PREFIX = re.compile(r"^(SS|AISI|SUS|UNS|SAE)(?=\d{3})")


def _designations(text: str) -> set[str]:
    tokens = re.findall(r"[A-Z0-9]+", text.upper())
    out: set[str] = set()
    for t in tokens:
        if any(ch.isdigit() for ch in t) and len(t) >= 2:
            out.add(t)
            core = _STANDARD_PREFIX.sub("", t)
            if core != t:
                out.add(core)
    return out


def _families(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.casefold())
    return {_FAMILIES[w] for w in words if w in _FAMILIES}


def compare_materials(a: str, b: str) -> str:
    """agree | disagree | unknown."""
    da, db = _designations(a), _designations(b)
    fa, fb = _families(a), _families(b)
    if fa and fb and not fa & fb:
        return "disagree"
    if da and db:
        return "agree" if da & db else "disagree"
    if fa and fb:
        return "agree"
    if normalize_for_match(a) == normalize_for_match(b):
        return "agree"
    return "unknown"


# ------------------------------------------------------------------------- value parsing


@dataclass(slots=True)
class _Length:
    raw: float
    unit: str | None
    prefix: str = ""  # "±" for tolerances

    @property
    def mm(self) -> float | None:
        return to_mm(self.raw, self.unit) if self.unit in ("mm", "in", "cm") else None

    def text(self) -> str:
        number = f"{self.prefix}{fmt(self.raw)}"
        return f"{number} {self.unit}" if self.unit else f"{number} (unit not stated)"


def _num(text: str) -> float | None:
    return parse_number(text)


def _outer_diameter(text: str) -> float | None:
    for m in _DIA_RE.finditer(text):
        before = text[max(0, m.start() - 14) : m.start()].casefold()
        after = text[m.end() : m.end() + 8].casefold()
        if "bore" in before or "bore" in after or "pcd" in after or "bcd" in after:
            continue
        if re.search(r"\d\s*[xX×]\s*$", text[: m.start()]):  # "6 x Ø10" is a hole, not the OD
            continue
        return _num(m.group(1))
    return None


def _bore(text: str) -> float | None:
    m = _BORE_RE.search(text)
    if not m:
        return None
    return _num(m.group(1) or m.group(2))


def _plate_dims(text: str) -> list[float]:
    if any(ch in text for ch in _DIA_CHARS):
        return []
    head = re.split(r"\bbore\b", text, flags=re.IGNORECASE)[0]
    return [n for n in (_num(t) for t in _NUM_RE.findall(head)) if n is not None]


def _turned_length(text: str) -> float | None:
    m = _TURNED_LEN_RE.search(text)
    return _num(m.group(1)) if m else None


def _tolerance(text: str) -> float | None:
    m = _TOL_RE.search(text)
    return _num(m.group(1)) if m else None


def _finish(text: str) -> tuple[str, float] | None:
    m = _RA_RE.search(text)
    if m and (v := _num(m.group(1))) is not None:
        return ("ra", v)
    m = _RMS_RE.search(text)
    if m and (v := _num(m.group(1))) is not None:
        return ("rms", v)
    return None


def _holes(text: str) -> list[tuple[int, float]]:
    return [(int(c), d) for c, ds in _HOLES_RE.findall(text) if (d := _num(ds)) is not None]


def _threads(text: str) -> list[float]:
    return [float(m.group(2)) for m in _THREAD_RE.finditer(text)]


def _says_none(text: str) -> bool:
    return normalize_for_match(text) in _NONE_WORDS


# --------------------------------------------------------------------- spreadsheet side


@dataclass(slots=True)
class _XCell:
    ref: CellRef
    unit: str | None  # length unit of the value
    where: str  # "Parts › C2"
    unit_note: str | None = None  # how the unit was established when the cell does not say


def _row_unit(row: RecordRow) -> str | None:
    for c in row.cells:
        m = _ROW_UNIT_RE.search(c.value)
        if m:
            return "in" if m.group(1).casefold().startswith("inch") else "mm"
    return None


def _row_header_unit(row: RecordRow) -> tuple[str, str] | None:
    """A size column in the same row whose header states a unit ("Finished Size (mm)")."""
    for c in row.cells:
        if c.canonical in _LENGTH_FIELDS and c.unit in ("mm", "in", "cm"):
            return c.unit, c.header
    return None


def _corroborated_unit(text: str, pool_mm: list[float]) -> str | None:
    """The only unit under which several of the cell's numbers match the drawing's dimensions."""
    nums = [n for n in (_num(t) for t in _ANY_NUM_RE.findall(text)) if n]
    if not nums or not pool_mm:
        return None
    scores = {
        u: sum(any(close(to_mm(n, u), p) for p in pool_mm) for n in nums) for u in ("mm", "in")
    }
    best, other = ("mm", "in") if scores["mm"] >= scores["in"] else ("in", "mm")
    return best if scores[best] >= 2 and scores[other] == 0 else None


def _excel_cells(
    sheets: Iterable[SheetSlice], canonical: str, pool_mm: list[float] | None = None
) -> list[_XCell]:
    out: list[_XCell] = []
    for s in sheets:
        if s.stale:
            continue
        for row in s.rows:
            if row.stale:
                continue
            for c in row.cells:
                if c.canonical != canonical:
                    continue
                unit = inline_length_unit(c.value) or (
                    c.unit if c.unit in ("mm", "in", "cm") else None
                )
                note = None
                if unit is None and (u := _row_unit(row)):
                    unit, note = u, "unit from a remark in the same row"
                if unit is None and (hu := _row_header_unit(row)):
                    unit, note = hu[0], f"unit from the row's '{hu[1]}' column"
                if unit is None and s.default_unit:
                    unit, note = s.default_unit, "unit from the sheet's heading"
                if unit is None and pool_mm and (cu := _corroborated_unit(c.value, pool_mm)):
                    unit = cu
                    note = (
                        f"no unit stated; read as {cu} because the cell's other dimensions "
                        f"match the drawing in {cu}"
                    )
                out.append(_XCell(c, unit, f"{s.sheet} › {c.col}{c.row}", note))
    return out


# ------------------------------------------------------------------------- drawing side


def _dfacts(drawings: list[DrawingSlice]) -> list[tuple[DrawingSlice, DrawingFact]]:
    return [(d, f) for d in drawings for f in d.facts if not f.stale]


def _pdf_kind(drawings: list[DrawingSlice], kind: str) -> list[tuple[DrawingSlice, DrawingFact]]:
    return [(d, f) for d, f in _dfacts(drawings) if f.region == "dimension" and f.kind == kind]


def _pdf_field(drawings: list[DrawingSlice], canonical: str) -> list[DrawingFact]:
    """Title-block value for a field, following 'SEE NOTE n' pointers; else a note stating it."""
    facts = _dfacts(drawings)
    by_id = {f.fact_id: f for _, f in facts}
    out: list[DrawingFact] = []
    for _, f in facts:
        if f.region == "title_block" and f.canonical == canonical:
            if f.points_to and f.points_to in by_id:
                out.append(by_id[f.points_to])
            elif not f.points_to:
                out.append(f)
    if not out:
        out = [f for _, f in facts if f.region == "note" and f.canonical == canonical]
    return out


def _pool_mm(drawings: list[DrawingSlice]) -> list[float]:
    """Every dimension the drawing states, in mm (for unit corroboration)."""
    out: list[float] = []
    for _, f in _dfacts(drawings):
        unit = normalize_unit(f.unit)
        if f.region != "dimension" or unit not in ("mm", "in"):
            continue
        for key in ("value", "diameter"):
            if (v := f.parsed.get(key)) is not None:
                out.append(to_mm(float(v), unit))
    return out


def _dlen(f: DrawingFact, key: str = "value") -> _Length | None:
    v = f.parsed.get(key)
    return _Length(float(v), normalize_unit(f.unit) or f.unit) if v is not None else None


# --------------------------------------------------------------------------- comparisons


def _cmp_lengths(
    field: str, xs: list[tuple[_XCell, _Length]], ps: list[tuple[DrawingFact, _Length]]
) -> CrossCheck | None:
    if not xs and not ps:
        return None
    label = FIELD_TITLES[field]
    if not ps:
        x, xl = xs[0]
        return CrossCheck(
            field=field,
            label=label,
            verdict="excel_only",
            excel=[x.ref.cell_id for x, _ in xs],
            excel_value=x.ref.value,
            detail=f"Only the spreadsheet states this ({x.where}: {xl.text()}).",
        )
    if not xs:
        p, pl = ps[0]
        return CrossCheck(
            field=field,
            label=label,
            verdict="pdf_only",
            pdf=[p.fact_id for p, _ in ps],
            pdf_value=p.value,
            detail=f"Only the drawing states this ({p.label}: {pl.text()}).",
        )
    p, pl = ps[0]
    verdicts: list[str] = []
    parts: list[str] = []
    for x, xl in xs:
        if xl.mm is not None and pl.mm is not None:
            same = close(xl.mm, pl.mm)
            converted = xl.unit != pl.unit
            verdicts.append(
                ("agree_after_conversion" if converted else "agree") if same else "disagree"
            )
            conv = f" (= {fmt(xl.mm)} mm)" if xl.unit == "in" else ""
            pconv = f" (= {fmt(pl.mm)} mm)" if pl.unit == "in" else ""
            parts.append(
                f"{x.where} says {xl.text()}{conv}; the drawing says {pl.text()}{pconv}"
                + (
                    " — the same" + (" after converting units" if converted else "")
                    if same
                    else " — they differ"
                )
                + (f" ({x.unit_note})" if x.unit_note else "")
            )
        elif close(xl.raw, pl.raw, rel=0.001, abs_tol=1e-6):
            verdicts.append("agree")
            parts.append(
                f"{x.where} says {fmt(xl.raw)} with no unit stated; the drawing says {pl.text()}; "
                "the numbers match"
            )
        else:
            verdicts.append("not_comparable")
            parts.append(
                f"{x.where} says {xl.text()} and the drawing says {pl.text()}; without a unit on "
                "both sides they cannot be compared"
            )
    verdict = _worst(verdicts)
    return CrossCheck(
        field=field,
        label=label,
        verdict=verdict,  # type: ignore[arg-type]
        excel=[x.ref.cell_id for x, _ in xs],
        pdf=[p.fact_id],
        excel_value="; ".join(x.ref.value for x, _ in xs),
        pdf_value=p.value,
        detail=". ".join(parts) + ".",
    )


def _worst(verdicts: list[str]) -> str:
    for v in (
        "disagree",
        "not_comparable",
        "excel_only",
        "agree_after_conversion",
        "equivalent_by_convention",
    ):
        if v in verdicts:
            return v
    return "agree"


def _material_check(record: PartRecord, drawings: list[DrawingSlice]) -> CrossCheck | None:
    xs = _excel_cells(record.sheets, "material")
    ps = _pdf_field(drawings, "material")
    if not xs and not ps:
        return None
    label = FIELD_TITLES["material"]
    if not ps or not xs:
        only = "spreadsheet" if xs else "drawing"
        value = xs[0].ref.value if xs else ps[0].value
        return CrossCheck(
            field="material",
            label=label,
            verdict="excel_only" if xs else "pdf_only",
            excel=[x.ref.cell_id for x in xs],
            pdf=[p.fact_id for p in ps],
            excel_value=xs[0].ref.value if xs else None,
            pdf_value=ps[0].value if ps else None,
            detail=f"Only the {only} states the material ({value}).",
        )
    p = ps[0]
    verdicts, parts = [], []
    for x in xs:
        v = compare_materials(x.ref.value, p.value)
        verdicts.append({"agree": "agree", "disagree": "disagree"}.get(v, "not_comparable"))
        parts.append(
            f"{x.where} says '{x.ref.value}', the drawing says '{p.value}'"
            + {"agree": " — the same material", "disagree": " — different materials"}.get(
                v, " — not clearly the same"
            )
        )
    return CrossCheck(
        field="material",
        label=label,
        verdict=_worst(verdicts),  # type: ignore[arg-type]
        excel=[x.ref.cell_id for x in xs],
        pdf=[p.fact_id],
        excel_value="; ".join(x.ref.value for x in xs),
        pdf_value=p.value,
        detail=". ".join(parts) + ".",
    )


def _holes_check(record: PartRecord, drawings: list[DrawingSlice]) -> CrossCheck | None:
    xs = _excel_cells(record.sheets, "holes", _pool_mm(drawings))
    ps = _pdf_kind(drawings, "hole_pattern")
    if not xs and not ps:
        return None
    label = FIELD_TITLES["holes"]
    p_desc = [
        (f, int(f.parsed["count"]), _Length(float(f.parsed["diameter"]), normalize_unit(f.unit)))
        for _, f in ps
        if "count" in f.parsed and "diameter" in f.parsed
    ]
    verdicts, parts, excel_ids = [], [], []
    for x in xs:
        excel_ids.append(x.ref.cell_id)
        patterns = _holes(x.ref.value)
        if _says_none(x.ref.value) or (not patterns and "hole" not in x.ref.value.casefold()):
            if not _says_none(x.ref.value):
                continue  # free text such as "1 x M6 radial tapped" belongs to the thread check
            if p_desc:
                verdicts.append("disagree")
                parts.append(f"{x.where} says no holes; the drawing shows {p_desc[0][0].value}")
            else:
                verdicts.append("agree")
                parts.append(f"{x.where} says no holes and the drawing shows no hole pattern")
            continue
        if not patterns:
            continue
        if not p_desc:
            verdicts.append("excel_only")
            parts.append(f"{x.where} says {x.ref.value}; the drawing has no hole-pattern callout")
            continue
        count, dia = patterns[0]
        pf, pcount, pdia = p_desc[0]
        xdia = _Length(dia, x.unit)
        same_count = count == pcount
        same_dia = (
            close(xdia.mm, pdia.mm, abs_tol=0.02)
            if xdia.mm is not None and pdia.mm is not None
            else close(dia, pdia.raw, rel=0.001, abs_tol=1e-6)
        )
        if same_count and same_dia:
            conv = xdia.unit and pdia.unit and xdia.unit != pdia.unit
            verdicts.append("agree_after_conversion" if conv else "agree")
            parts.append(
                f"{x.where} says {count} x Ø{xdia.text()}; the drawing says {pf.value}"
                + (
                    f" (Ø{pdia.text()} = {fmt(pdia.mm or 0)} mm)"
                    if conv and pdia.unit == "in"
                    else ""
                )
                + " — the same"
            )
        elif same_count and (xdia.mm is None or pdia.mm is None):
            verdicts.append("not_comparable")
            parts.append(
                f"{x.where} says {count} x Ø{xdia.text()}; the drawing says {pf.value} — the "
                "count matches; the diameters cannot be compared without a unit on both sides"
            )
        else:
            verdicts.append("disagree")
            what = "hole count" if not same_count else "hole diameter"
            parts.append(
                f"{x.where} says {count} x Ø{xdia.text()}; the drawing says {pf.value} — the "
                f"{what} differs"
            )
    if not verdicts:
        if not p_desc:
            return None
        return CrossCheck(
            field="holes",
            label=label,
            verdict="pdf_only",
            pdf=[f.fact_id for f, _, _ in p_desc],
            pdf_value=p_desc[0][0].value,
            detail=f"Only the drawing gives a hole pattern ({p_desc[0][0].value}).",
        )
    return CrossCheck(
        field="holes",
        label=label,
        verdict=_worst(verdicts),  # type: ignore[arg-type]
        excel=excel_ids,
        pdf=[f.fact_id for f, _, _ in p_desc],
        excel_value="; ".join(x.ref.value for x in xs),
        pdf_value=p_desc[0][0].value if p_desc else None,
        detail=". ".join(parts) + ".",
    )


def _thread_check(record: PartRecord, drawings: list[DrawingSlice]) -> CrossCheck | None:
    xs = [x for x in _excel_cells(record.sheets, "holes") if _threads(x.ref.value)]
    ps = [(d, f) for d, f in _pdf_kind(drawings, "thread") if "size" in f.parsed]
    if not xs or not ps:
        return None
    x, (_, p) = xs[0], ps[0]
    xs_size, ps_size = _threads(x.ref.value)[0], float(p.parsed["size"])
    same = close(xs_size, ps_size, abs_tol=1e-6)
    return CrossCheck(
        field="thread",
        label=FIELD_TITLES["thread"],
        verdict="agree" if same else "disagree",
        excel=[x.ref.cell_id],
        pdf=[p.fact_id],
        excel_value=x.ref.value,
        pdf_value=p.value,
        detail=f"{x.where} says '{x.ref.value}'; the drawing says '{p.value}'"
        + (" — the same thread size." if same else " — the thread sizes differ."),
    )


def _size_checks(record: PartRecord, drawings: list[DrawingSlice]) -> list[CrossCheck]:
    pool = _pool_mm(drawings)
    sizes = _excel_cells(record.sheets, "finished_size", pool)
    holes_text = _excel_cells(record.sheets, "holes", pool)
    out: list[CrossCheck] = []

    def lengths(kind: str) -> list[tuple[DrawingFact, _Length]]:
        return [(f, ln) for _, f in _pdf_kind(drawings, kind) if (ln := _dlen(f))]

    # Outer diameter: the largest plain diameter on the drawing.
    p_dia = sorted(lengths("diameter"), key=lambda t: -(t[1].mm or t[1].raw))[:1]
    x_od = [(x, _Length(v, x.unit)) for x in sizes if (v := _outer_diameter(x.ref.value))]
    if (x_od or p_dia) and (check := _cmp_lengths("outer_diameter", x_od, p_dia)):
        out.append(check)

    x_bore = [(x, _Length(v, x.unit)) for x in sizes + holes_text if (v := _bore(x.ref.value))]
    p_bore = lengths("bore")
    if (x_bore or p_bore) and (check := _cmp_lengths("bore", x_bore[:1], p_bore[:1])):
        out.append(check)

    # Thickness of a plate: the last of three plain dimensions.
    x_thk = []
    for x in sizes:
        dims = _plate_dims(x.ref.value)
        if len(dims) >= 3:
            x_thk.append((x, _Length(dims[2], x.unit)))
    p_thk = lengths("thickness")
    if (x_thk or p_thk) and (check := _cmp_lengths("thickness", x_thk, p_thk[:1])):
        out.append(check)

    # Length / overall size: unlabelled drawing numbers can only confirm, never contradict.
    shown = [ln for kind in ("linear", "thickness", "diameter") for _, ln in lengths(kind)]
    for x in sizes:
        dims = _plate_dims(x.ref.value)[:2]
        turned = _turned_length(x.ref.value)
        wanted = dims or ([turned] if turned is not None else [])
        if not wanted or not shown:
            continue
        found, missing = [], []
        for w in wanted:
            xl = _Length(w, x.unit)
            hit = next(
                (
                    p
                    for p in shown
                    if (xl.mm is not None and p.mm is not None and close(xl.mm, p.mm))
                    or (xl.unit is None and close(xl.raw, p.raw, rel=0.001, abs_tol=1e-6))
                ),
                None,
            )
            (found if hit else missing).append((xl, hit))
        converted = any(h and xl.unit and h.unit and xl.unit != h.unit for xl, h in found)
        if missing:
            verdict, tail = (
                "not_comparable",
                "the drawing's dimension numbers do not include "
                + ", ".join(xl.text() for xl, _ in missing)
                + " (unlabelled drawing numbers are not treated as a disagreement)",
            )
        else:
            verdict = "agree_after_conversion" if converted else "agree"
            tail = "the drawing shows " + ", ".join(
                f"{h.text()}" + (f" (= {fmt(h.mm or 0)} mm)" if h and h.unit == "in" else "")
                for _, h in found
                if h
            )
        out.append(
            CrossCheck(
                field="length",
                label=FIELD_TITLES["length"],
                verdict=verdict,  # type: ignore[arg-type]
                excel=[x.ref.cell_id],
                pdf=[
                    f.fact_id
                    for kind in ("linear", "thickness", "diameter")
                    for f, ln in lengths(kind)
                    if any(h is ln for _, h in found)
                ],
                excel_value=x.ref.value,
                pdf_value=", ".join(h.text() for _, h in found if h) or None,
                detail=f"{x.where} says {x.ref.value}; {tail}.",
            )
        )
        break
    return out


def _tolerance_check(record: PartRecord, drawings: list[DrawingSlice]) -> CrossCheck | None:
    xs = [
        (x, _Length(v, x.unit, "±"))
        for x in _excel_cells(record.sheets, "tolerance")
        if (v := _tolerance(x.ref.value)) is not None
    ]
    ps = []
    for f in _pdf_field(drawings, "tolerance"):
        v = _tolerance(f.value)
        if v is not None:
            unit = inline_length_unit(f.value) or normalize_unit(f.unit)
            ps.append((f, _Length(v, unit, "±")))
    if not xs or not ps:
        return None
    return _cmp_lengths("tolerance", xs, ps[:1])


def _finish_check(record: PartRecord, drawings: list[DrawingSlice]) -> CrossCheck | None:
    xs = [
        (x, f) for x in _excel_cells(record.sheets, "surface_finish") if (f := _finish(x.ref.value))
    ]
    ps = [(p, f) for p in _pdf_field(drawings, "surface_finish") if (f := _finish(p.value))]
    if not xs or not ps:
        return None
    (x, (xk, xv)), (p, (pk, pv)) = xs[0], ps[0]
    if xk == pk:
        same = close(xv, pv, rel=0.01, abs_tol=1e-6)
        verdict, how = ("agree", "the same") if same else ("disagree", "different")
    else:
        ra, rms = (xv, pv) if xk == "ra" else (pv, xv)
        same = finish_equivalent(ra, rms)
        verdict = "equivalent_by_convention" if same else "disagree"
        how = (
            f"the same grade by the conventional Ra/RMS table (Ra {fmt(ra)} µm ≈ {fmt(rms)} µin), "
            "not an exact conversion"
            if same
            else "different grades"
        )
    return CrossCheck(
        field="surface_finish",
        label=FIELD_TITLES["surface_finish"],
        verdict=verdict,  # type: ignore[arg-type]
        excel=[x.ref.cell_id],
        pdf=[p.fact_id],
        excel_value=x.ref.value,
        pdf_value=p.value,
        detail=f"{x.where} says '{x.ref.value}'; the drawing says '{p.value}' — {how}.",
    )


def cross_check(record: PartRecord) -> list[CrossCheck]:
    drawings = [d for d in record.drawings if d.readable]
    if not drawings or not record.sheets:
        return []
    checks: list[CrossCheck | None] = [
        _material_check(record, drawings),
        *_size_checks(record, drawings),
        _holes_check(record, drawings),
        _thread_check(record, drawings),
        _tolerance_check(record, drawings),
        _finish_check(record, drawings),
    ]
    return [c for c in checks if c is not None]


# --------------------------------------------------------- spreadsheet-internal conflicts


def values_agree(
    canonical: str, a: str, b: str, unit_a: str | None = None, unit_b: str | None = None
) -> bool:
    """Whether two spreadsheet values for one field say the same thing in different words."""
    if canonical == "material":
        return compare_materials(a, b) == "agree"
    if canonical in _LENGTH_FIELDS:
        ua = inline_length_unit(a) or (unit_a if unit_a in ("mm", "in", "cm") else None)
        ub = inline_length_unit(b) or (unit_b if unit_b in ("mm", "in", "cm") else None)
        na = [n for n in (_num(t) for t in _NUM_RE.findall(a)) if n is not None]
        nb = [n for n in (_num(t) for t in _NUM_RE.findall(b)) if n is not None]
        if len(na) != len(nb) or not na:
            return False
        if ua and ub:
            return all(close(to_mm(x, ua), to_mm(y, ub)) for x, y in zip(na, nb, strict=True))
        return all(close(x, y, rel=0.001, abs_tol=1e-6) for x, y in zip(na, nb, strict=True))
    if canonical == "holes":
        return _holes(a) == _holes(b) and bool(_holes(a))
    if canonical == "tolerance":
        ta, tb = _tolerance(a), _tolerance(b)
        return ta is not None and tb is not None and close(ta, tb, abs_tol=1e-6)
    if canonical == "surface_finish":
        fa, fb = _finish(a), _finish(b)
        return fa is not None and fa == fb
    if canonical in _TIME_FIELDS:
        ta, tb = _minutes(a, unit_a), _minutes(b, unit_b)
        return ta is not None and tb is not None and close(ta, tb, rel=0.02, abs_tol=0.01)
    return normalize_for_match(a) == normalize_for_match(b)


def _minutes(text: str, unit: str | None) -> float | None:
    m = re.search(rf"({NUM})\s*([a-zA-Z]+)?", text)
    if not m or (n := _num(m.group(1))) is None:
        return None
    u = normalize_unit(m.group(2)) or normalize_unit(unit)
    return n * MIN_PER[u] if u in MIN_PER else None
