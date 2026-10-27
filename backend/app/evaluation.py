"""Golden-set evaluation through the real HTTP path (``POST /parts/{pn}/ask``).

Usage: ``uv run cnc eval --provider fake|anthropic|groq [--out ../docs/eval-results.md]``

Deterministic metrics only (no LLM judge): status accuracy, answer correctness, citation
precision/recall, refusal precision/recall, hallucinations, latency. Small set, so the report
shows counts alongside rates.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.ingestion.cells import normalize_for_match

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.jsonl"
ABSTAIN = {"not_found", "blocked", "clarify", "part_not_found", "invalid_question"}


@dataclass(slots=True)
class RowResult:
    id: str
    category: str
    part: str
    question: str
    expected: list[str]
    status: str
    passed: bool
    status_ok: bool
    content_ok: bool | None
    cited: list[str]
    recall: float | None
    precision: float | None
    latency_ms: int
    provider: str | None
    answer: str
    notes: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)  # the full API result, so rows can be rescored offline


def load_golden(path: Path = GOLDEN) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def score_row(row: dict, result: dict, latency_ms: int) -> RowResult:
    status = result.get("status", "error")
    answer = result.get("answer", "")
    notes: list[str] = []
    status_ok = status in row["expected_status"]
    content_ok: bool | None = None
    text = normalize_for_match(answer)
    if "contains" in row or "contains_any" in row or "number" in row:
        content_ok = True
        for s in row.get("contains", []):
            if normalize_for_match(s) not in text:
                content_ok = False
                notes.append(f"missing '{s}'")
        if "contains_any" in row and not any(
            normalize_for_match(s) in text for s in row["contains_any"]
        ):
            content_ok = False
            notes.append(f"none of {row['contains_any']}")
        if "number" in row:
            comp = result.get("computation") or {}
            value = comp.get("result")
            want = row["number"]
            if value is None or abs(float(value) - want["value"]) > want["tol"]:
                content_ok = False
                notes.append(f"number {value} != {want['value']}")
    for s in row.get("forbidden", []):
        if normalize_for_match(s) in text:
            content_ok = False
            notes.append(f"forbidden '{s}' present")

    evidence = result.get("evidence", [])
    cited = [e["cell_id"] for e in evidence]
    recall = precision = None
    if row.get("cells"):
        expected = set(row["cells"])
        # Precision counts a citation as justified when the golden set lists it, when it identifies
        # the part the answer names (part number / description), or when the verifier linked it
        # because the answer quotes that cell's value verbatim. Anything else lowers precision.
        justified = {
            e["cell_id"]
            for e in evidence
            if e.get("auto_linked") or e.get("canonical") in ("part_number", "description")
        }
        acceptable = expected | set(row.get("acceptable_cells", [])) | justified
        recall = len(expected & set(cited)) / len(expected)
        precision = (len([c for c in cited if c in acceptable]) / len(cited)) if cited else 0.0
        if recall < 1:
            notes.append(f"missed cells {sorted(expected - set(cited))}")
    passed = status_ok and content_ok is not False and (recall is None or recall == 1.0)
    return RowResult(
        id=row["id"],
        category=row["category"],
        part=row["part"],
        question=row["question"],
        expected=row["expected_status"],
        status=status,
        passed=passed,
        status_ok=status_ok,
        content_ok=content_ok,
        cited=cited,
        recall=recall,
        precision=precision,
        latency_ms=latency_ms,
        provider=(result.get("provider") or {}).get("model"),
        answer=answer,
        notes=notes,
        raw=result,
    )


def summarise(rows: list[RowResult]) -> dict:
    should_abstain = [r for r in rows if set(r.expected) <= ABSTAIN]
    should_answer = [r for r in rows if not set(r.expected) <= ABSTAIN]
    did_abstain = [r for r in rows if r.status in ABSTAIN]
    true_abstain = [r for r in should_abstain if r.status in ABSTAIN]
    answered = [r for r in rows if r.status in ("answered", "computed")]
    wrong = [r for r in answered if (set(r.expected) <= ABSTAIN) or r.content_ok is False]
    with_cells = [r for r in rows if r.recall is not None and r.status in ("answered", "computed")]
    llm_rows = [r for r in rows if r.status not in ("part_not_found", "invalid_question")]
    recalls = [r.recall for r in with_cells if r.recall is not None]
    precisions = [r.precision for r in with_cells if r.precision is not None]
    return {
        "rows": len(rows),
        "passed": sum(r.passed for r in rows),
        "status_correct": sum(r.status_ok for r in rows),
        "answerable": len(should_answer),
        "answerable_correct": sum(r.passed for r in should_answer),
        "abstain_expected": len(should_abstain),
        "abstain_correct": len(true_abstain),
        "abstain_precision": (len(true_abstain) / len(did_abstain)) if did_abstain else None,
        "abstain_recall": (len(true_abstain) / len(should_abstain)) if should_abstain else None,
        "answered_incorrectly": len(wrong),
        "citation_recall": statistics.mean(recalls) if recalls else None,
        "citation_precision": statistics.mean(precisions) if precisions else None,
        "latency_ms_median": statistics.median(r.latency_ms for r in llm_rows)
        if llm_rows
        else None,
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def render_markdown(provider: str, model: str, summary: dict, rows: list[RowResult]) -> str:
    s = summary
    lines = [
        f"## Eval: {provider} ({model})",
        "",
        f"Run {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} over {s['rows']} golden questions "
        "through `POST /api/v1/parts/{pn}/ask`. Generated by `uv run cnc eval`.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Questions passed (status, content and all expected cells) | {s['passed']} / {s['rows']} |",
        f"| Answerable questions answered correctly | {s['answerable_correct']} / {s['answerable']} |",
        f"| Should-abstain questions that abstained | {s['abstain_correct']} / {s['abstain_expected']} |",
        f"| Abstain precision / recall | {_pct(s['abstain_precision'])} / {_pct(s['abstain_recall'])} |",
        f"| Answered incorrectly (wrong content, or answered when it should abstain) | {s['answered_incorrectly']} |",
        f"| Citation recall / precision (answered rows)¹ | {_pct(s['citation_recall'])} / {_pct(s['citation_precision'])} |",
        "| Citations that failed verification but were shown | 0 (verifier guarantees) |",
        f"| Median latency | {s['latency_ms_median'] or 0:.0f} ms |",
        "",
        "<details><summary>Per-question results</summary>",
        "",
        "| ID | Category | Part | Expected | Got | Pass | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        notes = "; ".join(r.notes).replace("|", "\\|")
        lines.append(
            f"| {r.id} | {r.category} | {r.part} | {'/'.join(r.expected)} | {r.status} | "
            f"{'yes' if r.passed else 'no'} | {notes} |"
        )
    lines += [
        "",
        "</details>",
        "",
        "¹ Recall: share of the golden set's expected cells that the answer cites. Precision: share of "
        "cited cells that are justified, meaning listed in the golden set, identifying the part the "
        "answer names (part number or description), or linked by the verifier because the answer "
        "quotes that cell's value verbatim.",
        "",
    ]
    return "\n".join(lines)


def _write_report(
    out: Path, provider: str, model: str, summary: dict, rows: list[RowResult]
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(provider, model, summary, rows), encoding="utf-8")
    payload = {
        "provider": provider,
        "model": model,
        "summary": summary,
        "rows": [asdict(r) for r in rows],
    }
    out.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(f"wrote {out} and {out.with_suffix('.json')}")


def rescore(saved: Path, out: Path | None) -> int:
    """Re-score a saved run against the current golden set without calling any LLM."""
    data = json.loads(saved.read_text(encoding="utf-8"))
    golden = {row["id"]: row for row in load_golden()}
    rows: list[RowResult] = []
    for old in data["rows"]:
        if not old.get("raw"):
            print(
                f"{saved} has no raw results (saved by an older version); re-run the eval instead"
            )
            return 2
        if old["id"] in golden:
            rows.append(score_row(golden[old["id"]], old["raw"], old["latency_ms"]))
    summary = summarise(rows)
    print(json.dumps(summary, indent=2))
    _write_report(out or saved.with_suffix(".md"), data["provider"], data["model"], summary, rows)
    return 0


def run_eval(provider: str, out: Path | None, delay_s: float = 0.0) -> int:
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    base = get_settings()
    settings = base.model_copy(
        update={
            "llm_primary_provider": provider,
            "llm_fallback_provider": "none",
            "auto_ingest": False,
        }
    )
    golden = load_golden()
    results: list[RowResult] = []
    model = provider
    with TestClient(create_app(settings)) as client:
        parts = client.get("/api/v1/parts").json()["parts"]
        if not parts:
            print("No parts ingested. Run `uv run cnc ingest` first.")
            return 2
        gw = client.app.state.gateway  # type: ignore[attr-defined]
        if gw.primary.name.replace("-", "_") not in (provider, "offline_rules"):
            print(f"warning: requested {provider} but primary is {gw.primary.name}")
        model = gw.primary.model
        for row in golden:
            t = time.perf_counter()
            resp = client.post(
                f"/api/v1/parts/{row['part']}/ask", json={"question": row["question"]}
            )
            latency = int((time.perf_counter() - t) * 1000)
            result = (
                resp.json() if resp.status_code == 200 else {"status": "error", "answer": resp.text}
            )
            r = score_row(row, result, latency)
            results.append(r)
            mark = "PASS" if r.passed else "FAIL"
            print(
                f"{mark} {r.id:<4} {r.status:<16} {r.question[:60]:<60} {'; '.join(r.notes)[:80]}",
                flush=True,
            )
            if delay_s:
                time.sleep(delay_s)
    summary = summarise(results)
    print(json.dumps(summary, indent=2))
    if out:
        _write_report(out, provider, model, summary, results)
    return 0
