"""Three-way cross-check: the 3D model joins the spreadsheet-vs-drawing comparison.

Each field is reduced to *statements*: what one cell, one drawing callout or one measured model
feature says, in millimetres when its unit is known. Every pair of sources is compared, the
field's verdict is the worst pairwise verdict, and the explanation groups the statements that
agree, so it can say "the drawing and the model both give Ø48; the job card says Ø50" without
ever deciding which file is right (ADR 0010). Two-source comparisons from Level 2 are kept
unchanged and gain their model side here.

Tolerances. A model is nominal geometry, so two values are the same when they differ by no more
than ``EPS_MM`` (0.005 mm, or 1e-4 of the value; inch values written to three decimals also allow
half a thousandth of an inch). A larger difference inside the drawing's general tolerance is
``within_tolerance``: someone should look, but it is not reported as a clean match.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.drawing import CheckSide, CrossCheck, DrawingSlice
from app.domain.model import ModelFeature, ModelSlice, make_model_fact_id
from app.domain.record import PartRecord
from app.services import crosscheck as cc
from app.services.units import fmt, inline_length_unit, normalize_unit, to_mm

EPS_MM = 0.005
AGREEING = {"agree", "agree_after_conversion", "equivalent_by_convention", "consistent"}
# ISO 261 coarse threads: nominal size -> standard tap drill (mm).
TAP_DRILL = {
    2.0: 1.6,
    2.5: 2.05,
    3.0: 2.5,
    4.0: 3.3,
    5.0: 4.2,
    6.0: 5.0,
    8.0: 6.8,
    10.0: 8.5,
    12.0: 10.2,
    14.0: 12.0,
    16.0: 14.0,
    20.0: 17.5,
    24.0: 21.0,
}
_SEVERITY = [
    "disagree",
    "within_tolerance",
    "not_comparable",
    "not_modelled",
    "excel_only",
    "pdf_only",
    "iges_only",
    "agree_after_conversion",
    "equivalent_by_convention",
    "consistent",
    "agree",
]
_SOURCE_NAME = {"excel": "spreadsheet", "pdf": "drawing", "iges": "model"}
_NOT_IN_MODEL = {
    "material": "a 3D model does not record the material",
    "tolerance": "a 3D model is nominal geometry; it holds no tolerance",
    "surface_finish": "a 3D model does not record surface finish",
}


def worst(verdicts: list[str]) -> str:
    present = [v for v in verdicts if v]
    if not present:
        return "not_comparable"
    return min(present, key=lambda v: _SEVERITY.index(v) if v in _SEVERITY else 0)


@dataclass(slots=True)
class St:
    """One source's statement about a field."""

    source: str  # excel | pdf | iges
    ids: list[str]
    who: str  # "Job Cards › E5 (job_cards_B.xlsx)", "the drawing", "the model"
    value: str  # as written or measured
    nums: tuple[float, ...]  # numbers as written (count first for holes)
    unit: str | None  # unit of nums (lengths); None = not stated
    note: str | None = None
    count: int | None = None  # hole count, when the statement is about holes
    confirm_only: bool = False  # unlabelled drawing numbers: can confirm, never contradict
    pool: tuple[float, ...] = ()  # for confirm-only statements: every number shown, in mm

    def mm(self) -> tuple[float, ...] | None:
        if self.unit not in ("mm", "in", "cm"):
            return None
        return tuple(to_mm(n, self.unit) for n in self.nums)

    def text(self) -> str:
        if self.count is not None:
            if self.count == 0:
                return "no holes"
            dia = self.nums[0] if self.nums else None
            unit = f" {self.unit}" if self.unit else ""
            return f"{self.count} × Ø{fmt(dia)}{unit}" if dia is not None else f"{self.count} holes"
        unit = f" {self.unit}" if self.unit else " (unit not stated)"
        return " × ".join(fmt(n) for n in self.nums) + unit


def _eps(a_mm: float, b_mm: float, a: St, b: St) -> float:
    eps = max(EPS_MM, 1e-4 * max(abs(a_mm), abs(b_mm)))
    if "in" in (a.unit, b.unit):
        eps = max(eps, 0.0005 * 25.4)  # inch values are written to three decimals
    return eps


def compare(a: St, b: St, tol_mm: float | None) -> str:
    """Verdict for one pair of statements."""
    if a.count is not None or b.count is not None:
        if a.count != b.count:
            return "disagree"
        if a.count == 0:
            return "agree"
        if not a.nums or not b.nums:
            return "agree"
    if a.confirm_only or b.confirm_only:
        conf, other = (a, b) if a.confirm_only else (b, a)
        om = other.mm()
        if om is None:
            return "not_comparable"
        hits = all(any(abs(v - p) <= _eps(v, p, other, conf) for p in conf.pool) for v in om)
        if not hits:
            return "not_comparable"  # unlabelled numbers never contradict
        return "agree_after_conversion" if (conf.unit and conf.unit != other.unit) else "agree"
    am, bm = a.mm(), b.mm()
    if am is None or bm is None:
        if len(a.nums) == len(b.nums) and all(
            abs(x - y) <= 1e-6 + 1e-3 * abs(x) for x, y in zip(a.nums, b.nums, strict=True)
        ):
            return "agree"  # same numbers; one side states no unit
        if am is None and bm is not None and len(a.nums) == len(bm):
            return "not_comparable"
        return "not_comparable"
    if len(am) != len(bm):
        return "not_comparable"
    diffs = [abs(x - y) for x, y in zip(am, bm, strict=True)]
    if all(d <= _eps(x, y, a, b) for d, x, y in zip(diffs, am, bm, strict=True)):
        converted = a.unit != b.unit and "in" in (a.unit, b.unit)
        return "agree_after_conversion" if converted else "agree"
    if tol_mm is not None and all(d <= tol_mm + 1e-9 for d in diffs):
        return "within_tolerance"
    return "disagree"


# -------------------------------------------------------------------------- statements


def _cell_who(x) -> str:
    return f"{x.where} ({x.ref.file})"


def _model_who(m: ModelSlice) -> str:
    return f"the model ({m.file})"


def _drawing_who(d: DrawingSlice) -> str:
    return f"the drawing ({d.file})"


def _feature(m: ModelSlice, fid: str) -> ModelFeature | None:
    f = m.feature(fid)
    return f if f is not None and not f.stale else None


def _mid(m: ModelSlice, f: ModelFeature) -> str:
    return make_model_fact_id(m.file_stem, f.feature_id)


def _model_pool(m: ModelSlice | None) -> list[float]:
    if m is None:
        return []
    out: list[float] = []
    for f in m.features:
        if f.stale:
            continue
        for k, v in f.numbers.items():
            if k.endswith("_mm"):
                out.append(float(v))
    return out


def _drawing_by_id(drawings: list[DrawingSlice]):
    return {f.fact_id: (d, f) for d in drawings for f in d.facts}


def _statements(record: PartRecord, drawings: list[DrawingSlice], model: ModelSlice | None):
    pool = cc._pool_mm(drawings) + _model_pool(model)
    sizes = cc._excel_cells(record.sheets, "finished_size", pool)
    holes_cells = cc._excel_cells(record.sheets, "holes", pool)
    by_id = _drawing_by_id(drawings)
    out: dict[str, list[St]] = {}

    def add(fld: str, st: St) -> None:
        out.setdefault(fld, []).append(st)

    def pdf_len(kind: str):
        return [(f, ln) for _, f in cc._pdf_kind(drawings, kind) if (ln := cc._dlen(f))]

    def pdf_st(f, ln) -> St:
        d, _ = by_id[f.fact_id]
        return St("pdf", [f.fact_id], _drawing_who(d), f.value, (ln.raw,), ln.unit)

    # Outer diameter --------------------------------------------------------------------------
    for x in sizes:
        if (v := cc._outer_diameter(x.ref.value)) is not None:
            add(
                "outer_diameter",
                St("excel", [x.ref.cell_id], _cell_who(x), x.ref.value, (v,), x.unit, x.unit_note),
            )
    p_dia = sorted(pdf_len("diameter"), key=lambda t: -(t[1].mm or t[1].raw))[:1]
    for f, ln in p_dia:
        add("outer_diameter", pdf_st(f, ln))
    # Bore ------------------------------------------------------------------------------------
    for x in sizes + holes_cells:
        if (v := cc._bore(x.ref.value)) is not None:
            add(
                "bore",
                St("excel", [x.ref.cell_id], _cell_who(x), x.ref.value, (v,), x.unit, x.unit_note),
            )
            break
    for f, ln in pdf_len("bore")[:1]:
        add("bore", pdf_st(f, ln))
    # Thickness ---------------------------------------------------------------------------------
    for x in sizes:
        dims = cc._plate_dims(x.ref.value)
        if len(dims) >= 3:
            add(
                "thickness",
                St(
                    "excel",
                    [x.ref.cell_id],
                    _cell_who(x),
                    x.ref.value,
                    (dims[2],),
                    x.unit,
                    x.unit_note,
                ),
            )
    for f, ln in pdf_len("thickness")[:1]:
        add("thickness", pdf_st(f, ln))
    # Length / overall size -------------------------------------------------------------------
    for x in sizes:
        dims = cc._plate_dims(x.ref.value)[:2]
        turned = cc._turned_length(x.ref.value)
        wanted = (
            tuple(sorted(dims, reverse=True)) if len(dims) == 2 else ((turned,) if turned else ())
        )
        if wanted:
            add(
                "length",
                St(
                    "excel", [x.ref.cell_id], _cell_who(x), x.ref.value, wanted, x.unit, x.unit_note
                ),
            )
            break
    shown = [(f, ln) for kind in ("linear", "thickness", "diameter") for f, ln in pdf_len(kind)]
    if shown and drawings:
        units = {ln.unit for _, ln in shown}
        add(
            "length",
            St(
                "pdf",
                [f.fact_id for f, _ in shown],
                _drawing_who(drawings[0]),
                ", ".join(f.value for f, _ in shown[:6]),
                (),
                next(iter(units)) if len(units) == 1 else None,
                confirm_only=True,
                pool=tuple(ln.mm for _, ln in shown if ln.mm is not None),
            ),
        )
    # Holes -------------------------------------------------------------------------------------
    for x in holes_cells:
        pats = cc._holes(x.ref.value)
        if cc._says_none(x.ref.value):
            add("holes", St("excel", [x.ref.cell_id], _cell_who(x), x.ref.value, (), None, count=0))
        elif pats:
            count, dia = pats[0]
            add(
                "holes",
                St(
                    "excel",
                    [x.ref.cell_id],
                    _cell_who(x),
                    x.ref.value,
                    (dia,),
                    x.unit,
                    x.unit_note,
                    count=count,
                ),
            )
    pd = [
        (f, int(f.parsed["count"]), float(f.parsed["diameter"]))
        for _, f in cc._pdf_kind(drawings, "hole_pattern")
        if "count" in f.parsed and "diameter" in f.parsed
    ]
    if pd:
        f, count, dia = pd[0]
        d, _ = by_id[f.fact_id]
        add(
            "holes",
            St(
                "pdf",
                [f.fact_id],
                _drawing_who(d),
                f.value,
                (dia,),
                normalize_unit(f.unit),
                count=count,
            ),
        )
    elif drawings and any(s.source == "excel" and s.count == 0 for s in out.get("holes", [])):
        add(
            "holes",
            St("pdf", [], _drawing_who(drawings[0]), "no hole-pattern callout", (), None, count=0),
        )

    # Model ---------------------------------------------------------------------------------------
    if model is not None and model.topology != "wireframe":
        who = _model_who(model)
        sizes_ok = model.topology != "multi_solid"
        if sizes_ok and (f := _feature(model, "od_1")):
            add(
                "outer_diameter",
                St("iges", [_mid(model, f)], who, f.value, (f.numbers["diameter_mm"],), "mm"),
            )
        if f := _feature(model, "bore"):
            add(
                "bore",
                St("iges", [_mid(model, f)], who, f.value, (f.numbers["diameter_mm"],), "mm"),
            )
        if sizes_ok and (f := _feature(model, "thickness")):
            add(
                "thickness",
                St("iges", [_mid(model, f)], who, f.value, (f.numbers["thickness_mm"],), "mm"),
            )
        env = _feature(model, "envelope")
        if sizes_ok and env is not None:
            if model.form == "turned":
                add(
                    "length",
                    St(
                        "iges",
                        [_mid(model, env)],
                        who,
                        env.value,
                        (env.numbers["length_mm"],),
                        "mm",
                    ),
                )
            elif "l_mm" in env.numbers:
                add(
                    "length",
                    St(
                        "iges",
                        [_mid(model, env)],
                        who,
                        env.value,
                        (env.numbers["l_mm"], env.numbers["w_mm"]),
                        "mm",
                    ),
                )
        holes = [
            f
            for f in model.features
            if f.kind in ("hole", "hole_pattern") and f.feature_id != "holes" and not f.stale
        ]
        summary = _feature(model, "holes")
        if summary is not None and out.get("holes"):
            if not holes:
                add("holes", St("iges", [_mid(model, summary)], who, "none", (), None, count=0))
            else:
                # The pattern the other sources describe, else the largest one.
                wanted = next((s.nums[0] for s in out["holes"] if s.count and s.nums), None)
                pick = sorted(
                    holes, key=lambda h: (-(h.numbers.get("count", 1)), -h.numbers["diameter_mm"])
                )
                if wanted is not None:
                    pick.sort(key=lambda h: abs(h.numbers["diameter_mm"] - wanted))
                h = pick[0]
                add(
                    "holes",
                    St(
                        "iges",
                        [_mid(model, h)],
                        who,
                        h.value,
                        (h.numbers["diameter_mm"],),
                        "mm",
                        count=int(h.numbers.get("count", 1)),
                    ),
                )
    return out


def _tolerance_mm(record: PartRecord, drawings: list[DrawingSlice]) -> float | None:
    """The drawing's general tolerance in mm (else the spreadsheet's), for within_tolerance."""
    for f in cc._pdf_field(drawings, "tolerance"):
        v = cc._tolerance(f.value)
        unit = (
            inline_length_unit(f.value)
            or normalize_unit(f.unit)
            or next((d.units for d in drawings if d.units), None)
        )
        if v is not None and unit in ("mm", "in"):
            return to_mm(v, unit)
    for x in cc._excel_cells(record.sheets, "tolerance"):
        v = cc._tolerance(x.ref.value)
        if v is not None and x.unit in ("mm", "in"):
            return to_mm(v, x.unit)
    return None


# -------------------------------------------------------------------------- assembling


def _pairs(sts: list[St], tol: float | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for a_src, b_src in (("excel", "pdf"), ("excel", "iges"), ("pdf", "iges")):
        a = [s for s in sts if s.source == a_src]
        b = [s for s in sts if s.source == b_src]
        if a and b:
            out[f"{a_src}~{b_src}"] = worst([compare(x, y, tol) for x in a for y in b])
    return out


def _groups(sts: list[St], tol: float | None) -> list[list[St]]:
    groups: list[list[St]] = []
    for s in sts:
        if s.confirm_only:
            continue
        for g in groups:
            if compare(g[0], s, tol) in AGREEING:
                g.append(s)
                break
        else:
            groups.append([s])
    groups.sort(key=lambda g: (-len({s.source for s in g}), -len(g)))
    return groups


def _names(group: list[St]) -> str:
    whos = [s.who for s in group]
    return whos[0] if len(whos) == 1 else ", ".join(whos[:-1]) + " and " + whos[-1]


def _explain(sts: list[St], groups: list[list[St]], pairs: dict[str, str], tol: float | None):
    """(detail, odd_one_out, dissent)."""
    notes = [f"{s.who}: {s.note}" for s in sts if s.note]
    confirm = [s for s in sts if s.confirm_only]
    odd, dissent = None, []
    if len(groups) <= 1:
        g = groups[0] if groups else []
        head = (
            f"{_names(g)} agree: {g[0].text()}"
            if len(g) > 1
            else (f"Only {g[0].who} states it: {g[0].text()}" if g else "")
        )
        if any(v == "agree_after_conversion" for v in pairs.values()) and g and g[0].unit != "mm":
            mm = g[0].mm()
            if mm:
                head += f" (= {' × '.join(fmt(v) for v in mm)} mm)"
    else:
        major, rest = groups[0], [s for g in groups[1:] for s in g]
        dissent = [i for s in rest for i in s.ids]
        rest_sources = {s.source for s in rest}
        major_sources = {s.source for s in major}
        if (
            len(major_sources) >= 2
            and len(rest_sources) == 1
            and not (rest_sources & major_sources)
        ):
            odd = next(iter(rest_sources))
        if len(major) >= 2:
            head = f"{_names(major)} agree on {major[0].text()}; " + "; ".join(
                f"{s.who} says {s.text()}" for s in rest
            )
        else:
            head = "The files differ: " + "; ".join(
                f"{s.who} says {s.text()}" for s in sts if not s.confirm_only
            )
        if "within_tolerance" in pairs.values() and tol is not None:
            head += (
                f" (the difference is inside the general tolerance of ±{fmt(tol)} mm, so it "
                "needs a look rather than a correction)"
            )
    parts = [head] if head else []
    for c in confirm:
        verdicts = {k: v for k, v in pairs.items() if "pdf" in k}
        if any(v in AGREEING for v in verdicts.values()):
            parts.append(f"{c.who} shows matching dimensions ({c.value})")
        elif verdicts:
            parts.append(
                f"{c.who}'s unlabelled dimensions ({c.value}) do not include these values, "
                "which is not treated as a disagreement"
            )
    parts += notes
    text = ". ".join(_sentence(p) for p in parts).rstrip(".") + "."
    return text, odd, dissent


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _normalised(s: St) -> str | None:
    """The statement in millimetres, for the side-by-side table."""
    if s.count == 0:
        return "no holes"
    mm = s.mm()
    if mm is None:
        return None
    if s.count:
        return f"{s.count} × Ø{fmt(mm[0])} mm"
    return " × ".join(fmt(v) for v in mm) + " mm"


def _sides(sts: list[St]) -> list[CheckSide]:
    out: list[CheckSide] = []
    for src in ("excel", "pdf", "iges"):
        mine = [s for s in sts if s.source == src]
        if not mine:
            continue
        norm = [n for s in mine if (n := _normalised(s))]
        out.append(
            CheckSide(
                source=src,  # type: ignore[arg-type]
                facts=[i for s in mine for i in s.ids],
                value="; ".join(s.value for s in mine),
                normalised="; ".join(norm) or None,
                note="; ".join(s.note for s in mine if s.note) or None,
            )
        )
    return out


def _check(
    fld: str, label: str, sts: list[St], tol: float | None, base: CrossCheck | None
) -> CrossCheck | None:
    sources = {s.source for s in sts}
    if len(sources) < 2:
        return base
    pairs = _pairs(sts, tol)
    if base is not None and "excel~pdf" in pairs:
        pairs["excel~pdf"] = base.verdict  # Level 2 rules stay authoritative for that pair
    groups = _groups(sts, tol)
    detail, odd, dissent = _explain(sts, groups, pairs, tol)
    if "iges" not in sources and base is not None:
        detail = base.detail  # nothing new to say; keep the Level 2 wording
    ids = {
        src: [i for s in sts if s.source == src for i in s.ids] for src in ("excel", "pdf", "iges")
    }
    vals = {
        src: "; ".join(s.value for s in sts if s.source == src) or None
        for src in ("excel", "pdf", "iges")
    }
    return CrossCheck(
        field=fld,
        label=label,
        verdict=worst(list(pairs.values())),  # type: ignore[arg-type]
        excel=base.excel if base else ids["excel"],
        pdf=base.pdf if base else ids["pdf"],
        iges=ids["iges"],
        excel_value=base.excel_value if base else vals["excel"],
        pdf_value=base.pdf_value if base else vals["pdf"],
        iges_value=vals["iges"],
        sides=_sides(sts),
        pairs=pairs,  # type: ignore[arg-type]
        odd_one_out=odd,  # type: ignore[arg-type]
        dissent=dissent,
        detail=detail,
    )


def _with_sides(c: CrossCheck, model: ModelSlice | None) -> CrossCheck:
    """A Level 2 check the model has nothing to add to: fill sides and pairs for the UI."""
    sides: list[CheckSide] = []
    if c.excel:
        sides.append(CheckSide(source="excel", facts=c.excel, value=c.excel_value))
    if c.pdf:
        sides.append(CheckSide(source="pdf", facts=c.pdf, value=c.pdf_value))
    c.sides = sides
    if c.excel and c.pdf:
        c.pairs = {"excel~pdf": c.verdict}
    if model is not None and c.field in _NOT_IN_MODEL:
        c.sides.append(CheckSide(source="iges", note=_NOT_IN_MODEL[c.field]))
    return c


def _stock_check(record: PartRecord, model: ModelSlice) -> CrossCheck | None:
    env = _feature(model, "envelope")
    if env is None or model.topology == "multi_solid":
        return None
    for x in cc._excel_cells(record.sheets, "raw_stock", _model_pool(model)):
        text = x.ref.value
        unit = x.unit
        if unit not in ("mm", "in", "cm"):
            continue
        dia = cc._outer_diameter(text)
        mid = _mid(model, env)
        if dia is not None and model.form == "turned":
            length = cc._turned_length(text)
            need = [("diameter", env.numbers["diameter_mm"], to_mm(dia, unit))]
            if length is not None:
                need.append(("length", env.numbers["length_mm"], to_mm(length, unit)))
        elif dia is None and model.form == "prismatic":
            dims = sorted((to_mm(n, unit) for n in cc._plate_dims(text)), reverse=True)
            if len(dims) < 3:
                continue
            part = [env.numbers["l_mm"], env.numbers["w_mm"], env.numbers["t_mm"]]
            need = [
                (n, p, s)
                for n, p, s in zip(("length", "width", "thickness"), part, dims, strict=True)
            ]
        else:
            return CrossCheck(
                field="stock",
                label="Raw stock vs model",
                verdict="not_comparable",
                excel=[x.ref.cell_id],
                iges=[mid],
                excel_value=text,
                iges_value=env.value,
                sides=[
                    CheckSide(source="excel", facts=[x.ref.cell_id], value=text),
                    CheckSide(source="iges", facts=[mid], value=env.value),
                ],
                pairs={"excel~iges": "not_comparable"},
                detail=f"{_cell_who(x)} gives {text}, but the stock shape and the part's shape "
                "differ (round against prismatic), so they are not compared.",
            )
        short = [(n, p, s) for n, p, s in need if s + EPS_MM < p]
        allowance = ", ".join(
            f"{fmt((s - p) / (2 if n == 'diameter' else 1))} mm "
            + ("per side on the diameter" if n == "diameter" else f"on the {n}")
            for n, p, s in need
        )
        verdict = "disagree" if short else "consistent"
        detail = (
            f"The raw stock {text} ({_cell_who(x)}) covers the model's envelope "
            f"{env.value.split(';')[0]}: {allowance}."
            if not short
            else f"The raw stock {text} ({_cell_who(x)}) is smaller than the model's envelope "
            f"{env.value.split(';')[0]} on the "
            + ", ".join(n for n, _, _ in short)
            + "; the part does not fit in the stock."
        )
        return CrossCheck(
            field="stock",
            label="Raw stock vs model",
            verdict=verdict,  # type: ignore[arg-type]
            excel=[x.ref.cell_id],
            iges=[mid],
            excel_value=text,
            iges_value=env.value,
            sides=[
                CheckSide(source="excel", facts=[x.ref.cell_id], value=text, note=x.unit_note),
                CheckSide(source="iges", facts=[mid], value=env.value),
            ],
            pairs={"excel~iges": verdict},  # type: ignore[dict-item]
            dissent=[x.ref.cell_id] if short else [],
            detail=detail,
        )
    return None


def _thread_with_model(
    base: CrossCheck | None, record: PartRecord, drawings, model: ModelSlice
) -> CrossCheck | None:
    sizes: list[tuple[str, float, list[str], str]] = []
    for x in cc._excel_cells(record.sheets, "holes"):
        for size in cc._threads(x.ref.value):
            sizes.append(("excel", size, [x.ref.cell_id], x.ref.value))
    for _, f in cc._pdf_kind(drawings, "thread"):
        if "size" in f.parsed:
            sizes.append(("pdf", float(f.parsed["size"]), [f.fact_id], f.value))
    if not sizes:
        return base
    size = sizes[0][1]
    holes = [
        f
        for f in model.features
        if f.kind in ("hole", "hole_pattern") and f.feature_id != "holes" and not f.stale
    ]
    tap = TAP_DRILL.get(size)
    match, how = None, ""
    for h in holes:
        d = h.numbers["diameter_mm"]
        if tap is not None and abs(d - tap) <= 0.05:
            match, how = h, f"Ø{fmt(d)} is the ISO 261 coarse tap drill for M{fmt(size)}"
            break
        if abs(d - size) <= 0.05:
            match, how = (
                h,
                f"Ø{fmt(d)} is the nominal M{fmt(size)} size (thread modelled cosmetically)",
            )
            break
    model_verdict = (
        "equivalent_by_convention" if match else ("disagree" if holes else "not_comparable")
    )
    pairs: dict[str, str] = {}
    if base is not None:
        pairs["excel~pdf"] = base.verdict
    srcs = {s for s, *_ in sizes}
    for s in srcs:
        pairs[f"{s}~iges"] = model_verdict
    mids = [_mid(model, match)] if match else [_mid(model, h) for h in holes[:1]]
    model_text = (
        f"{_model_who(model)} has {match.value}; {how}, so it matches by convention (a model "
        "shows the drilled hole, not the thread)"
        if match
        else (
            f"{_model_who(model)} has no hole matching an M{fmt(size)} thread (holes: "
            + ", ".join(h.value for h in holes)
            + ")"
            if holes
            else f"{_model_who(model)} has no hole where the thread should be"
        )
    )
    detail = (base.detail.rstrip(".") + ". " if base else "") + model_text + "."
    sides = [
        CheckSide(source=s, facts=ids, value=v)  # type: ignore[arg-type]
        for s, _, ids, v in sizes
    ] + [
        CheckSide(
            source="iges",
            facts=mids,
            value=match.value if match else None,
            note=None if match else "no matching hole",
        )
    ]
    return CrossCheck(
        field="thread",
        label=cc.FIELD_TITLES["thread"],
        verdict=worst(list(pairs.values())),  # type: ignore[arg-type]
        excel=base.excel if base else [i for s, _, ids, _ in sizes if s == "excel" for i in ids],
        pdf=base.pdf if base else [i for s, _, ids, _ in sizes if s == "pdf" for i in ids],
        iges=mids,
        excel_value=base.excel_value if base else None,
        pdf_value=base.pdf_value if base else None,
        iges_value=match.value if match else None,
        sides=sides,
        pairs=pairs,  # type: ignore[arg-type]
        dissent=[] if match else mids,
        detail=detail,
    )


def _chamfer_check(drawings: list[DrawingSlice], model: ModelSlice) -> CrossCheck | None:
    notes = [
        (d, f)
        for d in drawings
        for f in d.facts
        if not f.stale
        and (f.kind == "chamfer" or (f.region == "note" and "CHAMFER" in f.value.upper()))
    ]
    if not notes:
        return None
    d, f = notes[0]
    chamfers = model.by_kind("chamfer")
    mids = [_mid(model, c) for c in chamfers]
    if chamfers:
        verdict = "agree"
        detail = (
            f"{_drawing_who(d)} calls for '{f.value}' and {_model_who(model)} has "
            + ", ".join(c.value for c in chamfers)
            + "."
        )
    else:
        verdict = "not_modelled"
        detail = (
            f"{_drawing_who(d)} calls for '{f.value}'; {_model_who(model)} has no chamfer "
            "faces. Models "
            "often leave chamfers out, so this is noted, not treated as a disagreement."
        )
    return CrossCheck(
        field="chamfer",
        label="Chamfers",
        verdict=verdict,  # type: ignore[arg-type]
        pdf=[f.fact_id],
        iges=mids,
        pdf_value=f.value,
        iges_value=", ".join(c.value for c in chamfers) or None,
        sides=[
            CheckSide(source="pdf", facts=[f.fact_id], value=f.value),
            CheckSide(
                source="iges",
                facts=mids,
                value=", ".join(c.value for c in chamfers) or None,
                note=None if chamfers else "no chamfer faces",
            ),
        ],
        pairs={"pdf~iges": verdict},  # type: ignore[dict-item]
        detail=detail,
    )


def three_way(
    record: PartRecord, drawings: list[DrawingSlice], two_way: list[CrossCheck]
) -> list[CrossCheck]:
    model = next((m for m in record.models if not all(f.stale for f in m.features)), None)
    by_field = {c.field: c for c in two_way}
    if model is None:
        return [_with_sides(c, None) for c in two_way]
    tol = _tolerance_mm(record, drawings)
    statements = _statements(record, drawings, model)
    out: list[CrossCheck] = []
    for fld in (
        "material",
        "outer_diameter",
        "bore",
        "length",
        "thickness",
        "holes",
        "thread",
        "tolerance",
        "surface_finish",
    ):
        base = by_field.pop(fld, None)
        if fld == "thread":
            c = _thread_with_model(base, record, drawings, model)
        elif fld in _NOT_IN_MODEL:
            c = _with_sides(base, model) if base else None
        else:
            c = _check(fld, cc.FIELD_TITLES[fld], statements.get(fld, []), tol, base)
            if c is base and c is not None:
                c = _with_sides(c, model)
        if c is not None:
            out.append(c)
    out += [_with_sides(c, model) for c in by_field.values()]  # any field added later in Level 2
    if (stock := _stock_check(record, model)) is not None:
        out.append(stock)
    if (chamfer := _chamfer_check(drawings, model)) is not None:
        out.append(chamfer)
    return out
