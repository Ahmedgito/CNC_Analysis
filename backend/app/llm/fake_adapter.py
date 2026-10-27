"""Offline, deterministic provider: a keyword rules engine over the rendered prompt.

It exists so CI, the eval harness and keyless demos exercise the full pipeline (verifier,
compute engine, cross-check, persistence, UI) with predictable output. It reads only the prompt
text, the same input a real model gets, and follows the same rules: cite facts, name files,
never use stale history as current, report cross-check verdicts, ask before reading a scan.
It is labelled "offline-rules" everywhere it appears.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from app.llm.base import Prompt, ProviderResult, Usage
from app.llm.schemas import AnswerDraft, Computation, ComputationInput, EvidenceItem

_FACT_RE = re.compile(
    r"^\s+\[(?P<id>[^\]]+)\] (?P<label>.*?)(?: -> (?P<canon>\w+))?(?: unit=(?P<unit>\S+))?"
    r"(?P<flags>(?: (?:hidden|stale|inferred|vision))*) = (?P<val>\".*\")$"
)
_ROW_RE = re.compile(r"^  row (?P<row>\d+):")
_SHEET_RE = re.compile(r'^<sheet file=(?P<file>"[^"]*") sheet=(?P<sheet>"[^"]*")')
_DRAWING_RE = re.compile(r'^<drawing file=(?P<file>"[^"]*").*readable="(?P<readable>\w+)"')
_CHECK_RE = re.compile(r"^  - (?P<label>[^:]+): (?P<verdict>[A-Z_]+) — (?P<detail>\".*\")")
_QUESTION_RE = re.compile(r"<question>(?P<q>.*)</question>", re.S)
_INJECTION_RE = re.compile(
    r"ignore (all|any|the|your|previous)|disregard|system prompt|you are now|pretend|"
    r"jailbreak|reveal (your|the) (prompt|instructions)",
    re.I,
)
_OUT_OF_SCOPE = {
    "cost": ("price", "cost", "quote", "how much does", "unit price"),
    "customer": ("customer", "client", "who ordered", "buyer"),
    "due_date": ("delivery", "due date", "deadline", "ship date", "lead time"),
    "weight": ("weight", "weigh", "mass", "how heavy"),
    "colour": ("colour", "color"),
    "supplier": ("supplier", "vendor"),
}
_MODEL_WORDS = ("iges", "3d", "cad", "model file", "volume", "3-d")
_DRAWING_WORDS = ("drawing", "pdf", "title block", "drawn by", "scale")
_FIELD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("operation", "routing", "process steps", "ops", "sequence"), "operation"),
    (("tool", "insert", "cutter", "drill bit"), "tool"),
    (("material", "made of", "alloy", "grade", "steel", "brass", "bronze"), "material"),
    (("stock", "raw", "blank", "billet", "bar size"), "raw_stock"),
    (("outer diameter", "outside diameter", "od", "diameter"), "outer_diameter"),
    (("bore",), "bore"),
    (("thickness", "thick"), "thickness"),
    (("finished size", "final dim", "dimension", "overall size", "size"), "finished_size"),
    (("hole", "drilled"), "holes"),
    (("machine", "work center", "work centre", "lathe", "mill"), "machine"),
    (("cycle time", "time per piece", "time/pc", "how long"), "cycle_time"),
    (("tolerance", "tol"), "tolerance"),
    (("surface finish", "roughness", "finish", "ra"), "surface_finish"),
    (("heat", "treatment", "hardness"), "heat_treatment"),
    (("batch", "lot", "quantity", "qty", "how many parts"), "batch_qty"),
    (("revision", "rev"), "revision"),
    (("description", "what is", "name", "what part"), "description"),
    (("remark", "note"), "remarks"),
]
# Drawing facts that answer a field, by drawing field or dimension kind.
_DRAWING_FIELD = {
    "material": ("material",),
    "outer_diameter": ("diameter",),
    "bore": ("bore",),
    "thickness": ("thickness",),
    "holes": ("hole_pattern", "thread"),
    "tolerance": ("tolerance",),
    "surface_finish": ("surface_finish",),
    "heat_treatment": ("heat_treatment",),
    "revision": ("revision",),
    "description": ("description",),
}
_CHECK_FIELD = {
    "Material": "material",
    "Outer diameter": "outer_diameter",
    "Bore": "bore",
    "Thickness": "thickness",
    "Holes": "holes",
    "Threaded holes": "holes",
    "General tolerance": "tolerance",
    "Surface finish": "surface_finish",
}
_SIZE_FIELDS = {"outer_diameter", "bore", "thickness"}


@dataclass(frozen=True, slots=True)
class _Fact:
    fact_id: str
    label: str
    canonical: str | None
    unit: str | None
    value: str
    group: str  # sheet row, or drawing file
    file: str
    sheet: str | None
    drawing: bool
    stale: bool


@dataclass(frozen=True, slots=True)
class _Check:
    field: str
    verdict: str
    detail: str


@dataclass(slots=True)
class _Parsed:
    facts: list[_Fact]
    checks: list[_Check]
    drawings: dict[str, bool]  # file -> readable


def _parse(user: str) -> _Parsed:
    facts: list[_Fact] = []
    checks: list[_Check] = []
    drawings: dict[str, bool] = {}
    in_primary = False
    file, sheet, group, is_drawing = "", None, "", False
    for line in user.splitlines():
        if line.startswith('<part_record role="primary"'):
            in_primary = True
        elif line.startswith("</part_record>"):
            in_primary = False
        if not in_primary:
            continue
        if m := _SHEET_RE.match(line):
            file, sheet, is_drawing = (
                json.loads(m.group("file")),
                json.loads(m.group("sheet")),
                False,
            )
            group = f"{file}!{sheet}"
        elif m := _DRAWING_RE.match(line):
            file, sheet, is_drawing = json.loads(m.group("file")), None, True
            group = file
            drawings[file] = m.group("readable") == "true"
        elif (m := _ROW_RE.match(line)) and not is_drawing:
            group = f"{file}!{sheet}!r{m.group('row')}"
        elif m := _CHECK_RE.match(line):
            field = _CHECK_FIELD.get(m.group("label").strip())
            if field:
                checks.append(_Check(field, m.group("verdict"), json.loads(m.group("detail"))))
        elif m := _FACT_RE.match(line):
            facts.append(
                _Fact(
                    fact_id=m.group("id"),
                    label=m.group("label"),
                    canonical=m.group("canon"),
                    unit=m.group("unit"),
                    value=json.loads(m.group("val")),
                    group=group,
                    file=file,
                    sheet=sheet,
                    drawing=is_drawing,
                    stale="stale" in (m.group("flags") or ""),
                )
            )
    return _Parsed(facts, checks, drawings)


@lru_cache(maxsize=512)
def _word_re(word: str) -> re.Pattern[str]:
    # Whole words with an optional plural: "raw" must not match "drawing", "hole" matches "holes".
    return re.compile(rf"(?<![a-z0-9]){re.escape(word.strip())}s?(?![a-z0-9])")


def _has(q: str, words: tuple[str, ...]) -> bool:
    return any(_word_re(w).search(q) for w in words)


def _draft(status: str, answer: str, **kw) -> AnswerDraft:
    return AnswerDraft(
        status=status,  # type: ignore[arg-type]
        answer=answer,
        evidence=kw.get("evidence", []),
        computation=kw.get("computation"),
        general_knowledge=kw.get("general_knowledge", []),
        missing_information=kw.get("missing", []),
        confidence=kw.get("confidence", "high"),
        reason=kw.get("reason", "offline rules engine"),
    )


def _ev(facts: list[_Fact]) -> list[EvidenceItem]:
    return [EvidenceItem(fact_id=f.fact_id, quoted_value=f.value) for f in facts]


def _source(f: _Fact) -> str:
    return f"the drawing {f.file}" if f.drawing else f"the {f.sheet} sheet of {f.file}"


def rules_answer(user: str) -> AnswerDraft:
    m = _QUESTION_RE.search(user)
    question = json.loads(m.group("q")) if m else ""
    q = f" {question.lower()} "
    parsed = _parse(user)
    current = [f for f in parsed.facts if not f.stale]
    sheet_by: dict[str, list[_Fact]] = {}
    drawing_by: dict[str, list[_Fact]] = {}
    for f in current:
        if f.canonical:
            (drawing_by if f.drawing else sheet_by).setdefault(f.canonical, []).append(f)
    unread = [file for file, readable in parsed.drawings.items() if not readable]

    if _INJECTION_RE.search(question):
        return _draft(
            "refused_injection",
            "That request asks me to step outside the files. I can only answer from the "
            "manufacturing record and drawing.",
            reason="question contains instructions that conflict with answering from the files",
        )

    for canon, words in _OUT_OF_SCOPE.items():
        if _has(q, words) and canon not in sheet_by and canon not in drawing_by:
            present = ", ".join(sorted({f.label for f in current if f.canonical})[:8])
            label = canon.replace("_", " ")
            return _draft(
                "not_in_record",
                f"I can't find that in the provided files: the record has no {label} field. "
                f"It does contain: {present}.",
                missing=[label],
                reason="no matching field in the record",
            )

    if _has(q, _MODEL_WORDS):
        return _draft(
            "not_in_record",
            "I can't find that in the provided files: it needs the 3D (IGES) model, which is "
            "not available for this part.",
            missing=["3D model information"],
            reason="requires a source that is not ingested",
        )

    asks_drawing = _has(q, _DRAWING_WORDS)
    if asks_drawing and not parsed.drawings:
        return _draft(
            "not_in_record",
            "I can't find that in the provided files: there is no PDF drawing for this part, so "
            "only the spreadsheet was searched and it does not state this.",
            missing=["drawing information"],
            reason="no drawing ingested for this part",
        )

    # Totals over operation rows: computed in code, never here.
    if ("total" in q or "sum" in q or "altogether" in q) and ("setup" in q or "run" in q):
        canon = "setup_time" if "setup" in q else "run_time"
        rows = sheet_by.get(canon, [])
        if rows:
            inputs = [
                ComputationInput(name=f"c{i + 1}", fact_id=c.fact_id, number_index=0)
                for i, c in enumerate(rows)
            ]
            return _draft(
                "needs_computation",
                f"Total {canon.replace('_', ' ')} across {len(rows)} operations is {{result}} "
                f"(per {_source(rows[0])}).",
                evidence=_ev(rows),
                computation=Computation(
                    expression=" + ".join(i.name for i in inputs),
                    inputs=inputs,
                    unit_in=rows[0].unit,
                    unit_out=None,
                    label=f"total {canon.replace('_', ' ')}",
                ),
            )

    if (" inch" in q or " in inches" in q) and sheet_by.get("raw_stock"):
        stock = sheet_by["raw_stock"][0]
        return _draft(
            "needs_computation",
            "The stock diameter/first dimension converted to inches is {result} "
            f"(per {_source(stock)}).",
            evidence=_ev([stock]),
            computation=Computation(
                expression="c1",
                inputs=[ComputationInput(name="c1", fact_id=stock.fact_id, number_index=0)],
                unit_in=stock.unit or "mm",
                unit_out="in",
                label="stock size in inches",
            ),
        )

    for words, canon in _FIELD_KEYWORDS:
        if _has(q, words):
            return _field_answer(canon, parsed, sheet_by, drawing_by, unread)

    if asks_drawing:
        return _drawing_summary(parsed, unread)

    return _draft(
        "clarify",
        "Could you say which property you mean (for example material, stock size, operations, "
        "tools, cycle time or tolerance)?",
        confidence="low",
        reason="no rule matched",
    )


def _field_answer(
    canon: str,
    parsed: _Parsed,
    sheet_by: dict[str, list[_Fact]],
    drawing_by: dict[str, list[_Fact]],
    unread: list[str],
) -> AnswerDraft:
    label = canon.replace("_", " ")
    sheet_hits = sheet_by.get(canon, [])
    if canon in _SIZE_FIELDS:
        sheet_hits = sheet_by.get("finished_size", [])
        if canon == "bore":
            sheet_hits = [
                f for f in sheet_hits + sheet_by.get("holes", []) if "bore" in f.value.lower()
            ]
    drawing_hits = [f for key in _DRAWING_FIELD.get(canon, ()) for f in drawing_by.get(key, [])]
    if canon == "outer_diameter":
        drawing_hits = drawing_hits[:1]
    check = next((c for c in parsed.checks if c.field == canon), None)

    if not sheet_hits and not drawing_hits:
        if unread:
            return _draft(
                "needs_consent",
                f"The spreadsheet does not state the {label}, and the drawing {unread[0]} is a "
                "scanned image I have not read. Shall I read the scan with the vision model?",
                missing=[label],
                confidence="low",
                reason="the answer needs an unread scanned drawing",
            )
        return _draft(
            "not_in_record",
            f"I can't find that in the provided files: the record has no {label} for this part.",
            missing=[label],
            reason="field absent",
        )

    if canon == "operation":
        ops_by_row = {f.group: f for f in sheet_by.get("operation_number", [])}
        lines, ev = [], []
        for c in sheet_hits:
            op = ops_by_row.get(c.group)
            prefix = f"Op {op.value}: " if op else ""
            lines.append(f"- {prefix}{c.value}")
            ev.extend([op, c] if op else [c])
        return _draft(
            "answered",
            f"Operations in order (per {_source(sheet_hits[0])}):\n" + "\n".join(lines),
            evidence=_ev(ev),
        )

    unique: dict[str, _Fact] = {}
    for f in sheet_hits:
        unique.setdefault(f.value, f)
    parts = [
        f"{f.value}{f' {f.unit}' if f.unit else ''} ({f.label}, per {_source(f)})"
        for f in unique.values()
    ]
    parts += [f"{f.value} ({f.label}, per {_source(f)})" for f in drawing_hits]
    answer = f"{label.capitalize()}: " + "; ".join(parts) + "."
    confidence = "high"
    if check:
        answer += f"\n\nCross-check: {check.verdict.lower().replace('_', ' ')}. {check.detail}"
        if check.verdict == "DISAGREE":
            confidence = "medium"
    if unread:
        answer += (
            f"\n\nThe drawing {unread[0]} is a scanned image I have not read, so it was not "
            "checked."
        )
    return _draft(
        "answered", answer, evidence=_ev([*unique.values(), *drawing_hits]), confidence=confidence
    )


def _drawing_summary(parsed: _Parsed, unread: list[str]) -> AnswerDraft:
    if unread and len(unread) == len(parsed.drawings):
        return _draft(
            "needs_consent",
            f"The drawing {unread[0]} is a scanned image with no text layer, so I have not read "
            "it. Shall I read the scan with the vision model?",
            confidence="low",
            reason="the answer needs an unread scanned drawing",
        )
    tb = [f for f in parsed.facts if f.drawing and "!tb!" in f.fact_id and not f.stale]
    if not tb:
        return _draft(
            "not_in_record",
            "I can't find that in the provided files: the drawing has no readable title block.",
            missing=["title block"],
        )
    lines = [f"- {f.label}: {f.value}" for f in tb]
    return _draft(
        "answered",
        f"The title block of the drawing {tb[0].file} states:\n" + "\n".join(lines),
        evidence=_ev(tb),
    )


class FakeProvider:
    name = "offline-rules"
    model = "offline-rules-v1"

    async def answer(self, prompt: Prompt) -> ProviderResult:
        return ProviderResult(
            draft=rules_answer(prompt.user), model=self.model, usage=Usage(0, 0, 0)
        )
