"""Canonical manufacturing-record vocabulary and header matching.

Real shops name the same column many ways ("Part No", "Item Code", "P/N"). We map every header
to a ``CanonicalField`` when we are confident, and leave it unmapped otherwise. Unmapped headers
are never dropped: the LLM still sees them under their raw name, so new workbook layouts work
without code changes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz


class CanonicalField(StrEnum):
    PART_NUMBER = "part_number"
    DESCRIPTION = "description"
    MATERIAL = "material"
    RAW_STOCK = "raw_stock"
    FINISHED_SIZE = "finished_size"
    HOLES = "holes"
    MACHINE = "machine"
    CYCLE_TIME = "cycle_time"
    SETUP_TIME = "setup_time"
    RUN_TIME = "run_time"
    TOLERANCE = "tolerance"
    SURFACE_FINISH = "surface_finish"
    HEAT_TREATMENT = "heat_treatment"
    BATCH_QTY = "batch_qty"
    REVISION = "revision"
    DRAWING_NUMBER = "drawing_number"
    OPERATION_NUMBER = "operation_number"
    OPERATION = "operation"
    TOOL = "tool"
    REMARKS = "remarks"
    CUSTOMER = "customer"
    COST = "cost"
    DUE_DATE = "due_date"
    WEIGHT = "weight"
    STATUS = "status"
    LAST_UPDATED = "last_updated"


# Human-readable labels, used in prompts and "fields available" lists.
FIELD_LABELS: dict[CanonicalField, str] = {
    CanonicalField.PART_NUMBER: "part number",
    CanonicalField.DESCRIPTION: "description / part name",
    CanonicalField.MATERIAL: "material grade",
    CanonicalField.RAW_STOCK: "raw stock size",
    CanonicalField.FINISHED_SIZE: "finished size",
    CanonicalField.HOLES: "hole details",
    CanonicalField.MACHINE: "machine / work center",
    CanonicalField.CYCLE_TIME: "cycle time per piece",
    CanonicalField.SETUP_TIME: "setup time",
    CanonicalField.RUN_TIME: "run time",
    CanonicalField.TOLERANCE: "tolerance",
    CanonicalField.SURFACE_FINISH: "surface finish",
    CanonicalField.HEAT_TREATMENT: "heat treatment",
    CanonicalField.BATCH_QTY: "batch / lot quantity",
    CanonicalField.REVISION: "revision",
    CanonicalField.DRAWING_NUMBER: "drawing number",
    CanonicalField.OPERATION_NUMBER: "operation number",
    CanonicalField.OPERATION: "operation description",
    CanonicalField.TOOL: "tool",
    CanonicalField.REMARKS: "remarks / notes",
    CanonicalField.CUSTOMER: "customer",
    CanonicalField.COST: "cost / price",
    CanonicalField.DUE_DATE: "due / delivery date",
    CanonicalField.WEIGHT: "weight",
    CanonicalField.STATUS: "release status",
    CanonicalField.LAST_UPDATED: "last updated",
}

# Synonyms gathered from ERP exports, job cards, routers and travelers (see docs/PLAN.md).
# Keep entries lowercase and unit-free; they are normalised with the same function as headers.
_SYNONYMS: dict[CanonicalField, tuple[str, ...]] = {
    CanonicalField.PART_NUMBER: (
        "part no",
        "part number",
        "part #",
        "part",
        "p/n",
        "pn",
        "part num",
        "partnum",
        "item code",
        "item no",
        "item number",
        "item",
        "sku",
        "component no",
        "comp no",
        "article",
        "article no",
        "stock code",
        "product code",
        "drg part no",
        "part id",
        "component",
        "material no",
        "item id",
    ),
    CanonicalField.DESCRIPTION: (
        "description",
        "desc",
        "part name",
        "item name",
        "name",
        "title",
        "nomenclature",
        "component name",
        "part description",
        "item description",
        "material description",
    ),
    CanonicalField.MATERIAL: (
        "material",
        "mat",
        "matl",
        "mat'l",
        "mtl",
        "mat grade",
        "material grade",
        "material spec",
        "spec",
        "grade",
        "alloy",
        "raw material",
        "stock material",
        "basic material",
        "material type",
    ),
    CanonicalField.RAW_STOCK: (
        "stock size",
        "raw stock",
        "blank size",
        "billet",
        "bar size",
        "stock",
        "raw size",
        "cut length",
        "stock dims",
        "blank",
        "raw material size",
        "stock dimensions",
    ),
    CanonicalField.FINISHED_SIZE: (
        "finished size",
        "final dims",
        "finish size",
        "fin dims",
        "overall dims",
        "envelope",
        "size",
        "dimensions",
        "part size",
        "final size",
        "finished dims",
        "final dimensions",
        "finished dimensions",
    ),
    CanonicalField.HOLES: (
        "holes",
        "hole details",
        "hole spec",
        "hole pattern",
        "no of holes",
        "drilling",
        "tapped holes",
        "hole",
        "holes details",
        "feature notes",
        "features",
        "feature",
    ),
    CanonicalField.MACHINE: (
        "machine",
        "m/c",
        "mc",
        "work center",
        "work centre",
        "workcenter",
        "w/c",
        "wc",
        "resource",
        "resource group",
        "cell",
        "station",
        "equipment",
        "machine tool",
        "machines",
    ),
    CanonicalField.CYCLE_TIME: (
        "cycle time",
        "cyc",
        "cyc time",
        "ct",
        "time/pc",
        "time pc",
        "time per piece",
        "piece time",
        "unit time",
        "std time",
        "standard time",
        "process time",
        "time/piece",
        "est time",
        "estimated time",
        "est hrs",
        "est hours",
        "time est",
    ),
    CanonicalField.SETUP_TIME: (
        "setup",
        "set-up",
        "set up",
        "setup time",
        "set up time",
        "su",
        "setup hrs",
        "changeover",
        "setup mins",
    ),
    CanonicalField.RUN_TIME: (
        "run",
        "run time",
        "runtime",
        "machine time",
        "mach time",
        "op time",
        "labor time",
        "machining time",
        "run mins",
    ),
    CanonicalField.TOLERANCE: (
        "tolerance",
        "tol",
        "general tolerance",
        "gen tol",
        "dim tol",
        "tolerance class",
        "tolerances",
        "general tol",
    ),
    CanonicalField.SURFACE_FINISH: (
        "surface finish",
        "finish",
        "fin",
        "surf",
        "surf fin",
        "ra",
        "roughness",
        "surface roughness",
        "surface",
        "texture",
    ),
    CanonicalField.HEAT_TREATMENT: (
        "heat treatment",
        "heat tr",
        "ht",
        "h/t",
        "h&t",
        "treatment",
        "hardening",
        "heat treat",
        "hardness",
    ),
    CanonicalField.BATCH_QTY: (
        "batch qty",
        "lot size",
        "lot qty",
        "qty",
        "quantity",
        "order qty",
        "qty reqd",
        "run qty",
        "batch",
        "batch size",
        "prod qty",
        "lot",
    ),
    CanonicalField.REVISION: (
        "rev",
        "revision",
        "rev level",
        "issue",
        "version",
        "drg rev",
        "drawing rev",
    ),
    CanonicalField.DRAWING_NUMBER: (
        "drawing no",
        "drg no",
        "drg",
        "dwg",
        "dwg no",
        "drawing #",
        "drawing number",
        "doc no",
        "print no",
        "drawing",
    ),
    CanonicalField.OPERATION_NUMBER: (
        "op no",
        "op #",
        "op",
        "operation no",
        "operation number",
        "seq",
        "sequence",
        "step",
        "op seq",
        "oper no",
        "opr seq",
    ),
    CanonicalField.OPERATION: (
        "operation",
        "op desc",
        "operation description",
        "process",
        "activity",
        "task",
        "work description",
        "opcode",
        "op code",
        "process step",
    ),
    CanonicalField.TOOL: (
        "tool",
        "tooling",
        "cutter",
        "tool no",
        "insert",
        "tool list",
        "tools",
        "tool description",
    ),
    CanonicalField.REMARKS: (
        "remarks",
        "notes",
        "note",
        "comments",
        "comment",
        "special instructions",
        "instructions",
        "memo",
        "remark",
    ),
    CanonicalField.CUSTOMER: ("customer", "cust", "client", "customer name", "sold to"),
    CanonicalField.COST: (
        "cost",
        "price",
        "unit price",
        "unit cost",
        "rate",
        "std cost",
        "quote",
        "target price",
        "amount",
    ),
    CanonicalField.DUE_DATE: (
        "due date",
        "due",
        "delivery",
        "delivery date",
        "ship date",
        "required by",
        "need date",
        "promise date",
    ),
    CanonicalField.WEIGHT: ("weight", "wt", "mass", "net wt", "gross wt", "net weight"),
    CanonicalField.STATUS: (
        "status",
        "release status",
        "lifecycle",
        "lifecycle status",
        "part status",
        "drawing status",
    ),
    CanonicalField.LAST_UPDATED: (
        "last updated",
        "updated",
        "last modified",
        "modified",
        "date updated",
    ),
}

# Unit tokens recognised inside header parentheses: "Cycle Time (min)" -> unit "min".
_UNIT_ALIASES: dict[str, str] = {
    "mm": "mm",
    "millimetre": "mm",
    "millimeter": "mm",
    "millimetres": "mm",
    "cm": "cm",
    "m": "m",
    "in": "in",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "min": "min",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "seconds": "s",
    "µm": "µm",
    "um": "µm",
    "μm": "µm",
    "micron": "µm",
    "microns": "µm",
    "µin": "µin",
    "uin": "µin",
    "kg": "kg",
    "g": "g",
    "lb": "lb",
    "lbs": "lb",
    "pcs": "pcs",
    "pc": "pcs",
    "nos": "pcs",
    "ea": "pcs",
}

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_UNIT_TAIL_RE = re.compile(r"\[([^\]]*)\]")
_PUNCT_RE = re.compile(r"[._:;,\-]+")
_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace(" ", " ")
    text = _PAREN_RE.sub(" ", text)
    text = _UNIT_TAIL_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _norm_synonym(text: str) -> str:
    # Synonyms like "p/n" and "time/pc" keep the slash; headers are tried with and without it.
    return _norm(text)


_SYNONYM_INDEX: dict[str, CanonicalField] = {}
for _field, _names in _SYNONYMS.items():
    for _name in _names:
        _SYNONYM_INDEX.setdefault(_norm_synonym(_name), _field)
        _SYNONYM_INDEX.setdefault(_norm_synonym(_name).replace("/", " "), _field)
        _SYNONYM_INDEX.setdefault(_norm_synonym(_name).replace("/", ""), _field)


@dataclass(frozen=True, slots=True)
class HeaderMatch:
    raw: str
    label: str  # header without the unit suffix
    canonical: CanonicalField | None
    unit: str | None
    method: str  # exact | slash | fuzzy | none


def extract_unit(header: str) -> tuple[str, str | None]:
    """Split ``"Cycle Time (min)"`` into ``("Cycle Time", "min")``.

    Only recognised unit tokens count; ``"Part No (customer)"`` keeps its parenthetical.
    """
    for regex in (_PAREN_RE, _UNIT_TAIL_RE):
        for m in regex.finditer(header):
            token = m.group(1).strip().casefold()
            unit = _UNIT_ALIASES.get(token)
            if unit:
                label = (header[: m.start()] + header[m.end() :]).strip()
                return _WS_RE.sub(" ", label), unit
    return header.strip(), None


def match_header(header: str) -> HeaderMatch:
    label, unit = extract_unit(header)
    key = _norm(header)
    if not key:
        return HeaderMatch(header, label, None, unit, "none")
    if key in _SYNONYM_INDEX:
        return HeaderMatch(header, label, _SYNONYM_INDEX[key], unit, "exact")
    for variant in (key.replace("/", " "), key.replace("/", "")):
        variant = _WS_RE.sub(" ", variant).strip()
        if variant in _SYNONYM_INDEX:
            return HeaderMatch(header, label, _SYNONYM_INDEX[variant], unit, "slash")
    # Fuzzy only for reasonably long headers; short codes are too ambiguous to guess.
    if len(key) >= 5:
        best: tuple[float, CanonicalField | None] = (0.0, None)
        for syn, fld in _SYNONYM_INDEX.items():
            if len(syn) < 4:
                continue
            score = fuzz.token_sort_ratio(key, syn)
            if score > best[0]:
                best = (score, fld)
        if best[0] >= 90 and best[1] is not None:
            return HeaderMatch(header, label, best[1], unit, "fuzzy")
    return HeaderMatch(header, label, None, unit, "none")


def is_known_header(text: str) -> bool:
    return match_header(text).canonical is not None
