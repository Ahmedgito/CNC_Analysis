"""Offline, deterministic provider: a keyword rules engine over the rendered prompt.

It exists so CI, the eval harness and keyless demos exercise the full pipeline (verifier,
compute engine, persistence, UI) with predictable output. It reads only the prompt text, the
same input a real model gets. It is labelled "offline-rules" everywhere it appears.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.base import Prompt, ProviderResult, Usage
from app.llm.schemas import AnswerDraft, Computation, ComputationInput, EvidenceItem

_CELL_RE = re.compile(
    r"^\s+\[(?P<id>[^\]]+)\] (?P<label>.*?)(?: -> (?P<canon>\w+))?(?: unit=(?P<unit>\S+))?"
    r'(?: hidden)? = (?P<val>".*")$'
)
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
_OTHER_SOURCE = ("drawing", "pdf", "iges", "3d", "cad", "model file", "title block", "volume")
_FIELD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("operation", "routing", "process steps", "ops", "sequence"), "operation"),
    (("tool", "insert", "cutter", "drill bit"), "tool"),
    (("material", "made of", "alloy", "grade", "steel", "brass", "bronze"), "material"),
    (("stock", "raw", "blank", "billet", "bar size"), "raw_stock"),
    (("finished size", "final dim", "dimension", "overall size", "size"), "finished_size"),
    (("hole", "drilled", "bore"), "holes"),
    (("machine", "work center", "work centre", "lathe", "mill"), "machine"),
    (("cycle time", "time per piece", "time/pc", "how long"), "cycle_time"),
    (("tolerance", "tol"), "tolerance"),
    (("surface finish", "roughness", "finish", "ra "), "surface_finish"),
    (("heat", "treatment", "hardness"), "heat_treatment"),
    (("batch", "lot", "quantity", "qty", "how many parts"), "batch_qty"),
    (("description", "what is", "name", "what part"), "description"),
    (("remark", "note"), "remarks"),
]


@dataclass(frozen=True, slots=True)
class _Cell:
    cell_id: str
    label: str
    canonical: str | None
    unit: str | None
    value: str
    row_key: str  # file!sheet!row


def _parse_cells(user: str) -> list[_Cell]:
    cells: list[_Cell] = []
    in_primary = False
    for line in user.splitlines():
        if line.startswith('<part_record role="primary"'):
            in_primary = True
        elif line.startswith("</part_record>"):
            in_primary = False
        elif in_primary:
            m = _CELL_RE.match(line)
            if m:
                cid = m.group("id")
                file_sheet, coord = cid.rsplit("!", 1)
                row = re.sub(r"^[A-Z]+", "", coord)
                cells.append(
                    _Cell(
                        cell_id=cid,
                        label=m.group("label"),
                        canonical=m.group("canon"),
                        unit=m.group("unit"),
                        value=json.loads(m.group("val")),
                        row_key=f"{file_sheet}!{row}",
                    )
                )
    return cells


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


def _ev(cells: list[_Cell]) -> list[EvidenceItem]:
    return [EvidenceItem(cell_id=c.cell_id, quoted_value=c.value) for c in cells]


def rules_answer(user: str) -> AnswerDraft:
    m = _QUESTION_RE.search(user)
    question = json.loads(m.group("q")) if m else ""
    q = f" {question.lower()} "
    cells = _parse_cells(user)
    by_canon: dict[str, list[_Cell]] = {}
    for c in cells:
        if c.canonical:
            by_canon.setdefault(c.canonical, []).append(c)

    if _INJECTION_RE.search(question):
        return _draft(
            "refused_injection",
            "That request asks me to step outside the files. I can only answer from the "
            "manufacturing record.",
            reason="question contains instructions that conflict with answering from the files",
        )

    for canon, words in _OUT_OF_SCOPE.items():
        if any(w in q for w in words) and canon not in by_canon:
            present = ", ".join(sorted({c.label for c in cells if c.canonical})[:8])
            label = canon.replace("_", " ")
            return _draft(
                "not_in_record",
                f"I can't find that in the provided files: the record has no {label} field. "
                f"It does contain: {present}.",
                missing=[canon.replace("_", " ")],
                reason="no matching field in the record",
            )

    if any(w in q for w in _OTHER_SOURCE):
        return _draft(
            "not_in_record",
            "I can't find that in the provided files: it needs the PDF drawing or the 3D model, "
            "which are not available for this part. Only the Excel record was searched.",
            missing=["drawing / 3D model information"],
            reason="requires a source that is not ingested",
        )

    # Totals over operation rows: computed in code, never here.
    if ("total" in q or "sum" in q or "altogether" in q) and ("setup" in q or "run" in q):
        canon = "setup_time" if "setup" in q else "run_time"
        rows = by_canon.get(canon, [])
        if rows:
            inputs = [
                ComputationInput(name=f"c{i + 1}", cell_id=c.cell_id, number_index=0)
                for i, c in enumerate(rows)
            ]
            return _draft(
                "needs_computation",
                f"Total {canon.replace('_', ' ')} across {len(rows)} operations is {{result}}.",
                evidence=_ev(rows),
                computation=Computation(
                    expression=" + ".join(i.name for i in inputs),
                    inputs=inputs,
                    unit_in=rows[0].unit,
                    unit_out=None,
                    label=f"total {canon.replace('_', ' ')}",
                ),
            )

    if (" inch" in q or " in inches" in q) and by_canon.get("raw_stock"):
        stock = by_canon["raw_stock"][0]
        return _draft(
            "needs_computation",
            "The stock diameter/first dimension converted to inches is {result}.",
            evidence=_ev([stock]),
            computation=Computation(
                expression="c1",
                inputs=[ComputationInput(name="c1", cell_id=stock.cell_id, number_index=0)],
                unit_in=stock.unit or "mm",
                unit_out="in",
                label="stock size in inches",
            ),
        )

    for words, canon in _FIELD_KEYWORDS:
        if not any(w in q for w in words):
            continue
        hits = by_canon.get(canon, [])
        if not hits:
            return _draft(
                "not_in_record",
                f"I can't find that in the provided files: the record has no "
                f"{canon.replace('_', ' ')} for this part.",
                missing=[canon.replace("_", " ")],
                reason="field absent",
            )
        if canon == "operation":
            ops_by_row = {c.row_key: c for c in by_canon.get("operation_number", [])}
            lines, ev = [], []
            for c in hits:
                op = ops_by_row.get(c.row_key)
                prefix = f"Op {op.value}: " if op else ""
                lines.append(f"- {prefix}{c.value}")
                ev.extend([op, c] if op else [c])
            return _draft("answered", "Operations in order:\n" + "\n".join(lines), evidence=_ev(ev))
        unique: dict[str, _Cell] = {}
        for c in hits:
            unique.setdefault(c.value, c)
        values = "; ".join(
            f"{c.value}{f' {c.unit}' if c.unit else ''} ({c.label})" for c in unique.values()
        )
        return _draft(
            "answered",
            f"{canon.replace('_', ' ').capitalize()}: {values}.",
            evidence=_ev(list(unique.values())),
        )

    return _draft(
        "clarify",
        "Could you say which property you mean (for example material, stock size, operations, "
        "tools, cycle time or tolerance)?",
        confidence="low",
        reason="no rule matched",
    )


class FakeProvider:
    name = "offline-rules"
    model = "offline-rules-v1"

    async def answer(self, prompt: Prompt) -> ProviderResult:
        return ProviderResult(
            draft=rules_answer(prompt.user), model=self.model, usage=Usage(0, 0, 0)
        )
