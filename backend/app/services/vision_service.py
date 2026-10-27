"""Read a scanned drawing with the vision model, after the user has agreed, and store the result.

The transcription goes through the same classifiers as text drawings (title-block vocabulary,
note classification, dimension callouts) so the record, the prompt and the cross-check treat it
uniformly. Every fact is stored with ``confidence="vision"`` and the drawing keeps
``scanned=True``; the UI and the answers say the values were read from a scan.
"""

from __future__ import annotations

import re
import time

from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from app.db.session import session_scope
from app.domain.drawing import DrawingFact, DrawingSlice, make_drawing_fact_id
from app.ingestion.parts import normalize_part_key
from app.ingestion.pdf.dimensions import KIND_LABEL, is_view_title, parse_callout
from app.ingestion.pdf.notes import classify, declared_unit, unit_word
from app.ingestion.pdf.title_block import _keys_for, canonical_for
from app.llm.base import ProviderError, Usage
from app.llm.gateway import CallRecord
from app.llm.vision import VisionProvider, VisionReading
from app.logging_setup import log
from app.repositories import conversations as conv_repo
from app.repositories.parts import get_part, replace_drawing
from app.services.file_store import FileStore

MAX_SCAN_PAGES = 4
SCAN_DPI = 130  # ~1520 px on the long edge of A4: inside the vision models' sweet spot


class VisionUnavailableError(RuntimeError):
    """No vision-capable provider is configured."""


class ScanNotFoundError(LookupError):
    """The part has no scanned drawing with that file name, or its bytes are missing."""


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")[:40] or "field"


def facts_from_reading(old: DrawingSlice, reading: VisionReading) -> DrawingSlice:
    stem = old.file_stem
    facts: list[DrawingFact] = []
    units: str | None = None
    revision: str | None = None
    title: str | None = None
    part_number: str | None = None
    for page in reading.pages:
        if not page.legible:
            continue
        p = page.page
        page_units = None
        for f in page.title_block:
            keys = _keys_for(f.label) or [_slug(f.label)]
            values = [v.strip() for v in f.value.split("/")] if len(keys) > 1 else [f.value]
            if len(values) != len(keys):
                keys, values = keys[:1], [f.value]
            for key, value in zip(keys, values, strict=True):
                if not value:
                    continue
                if key == "units":
                    page_units = unit_word(value) or declared_unit(f"UNITS: {value}")
                if key == "revision":
                    revision = revision or value.upper()
                if key == "title":
                    title = title or value
                if key == "part_number":
                    part_number = part_number or value
                facts.append(
                    DrawingFact(
                        fact_id=make_drawing_fact_id(stem, p, "title_block", key),
                        page=p,
                        region="title_block",
                        key=key,
                        label=f.label,
                        canonical=canonical_for(key),
                        value=value,
                        confidence="vision",
                    )
                )
        for n in page.notes:
            canonical, parsed = classify(n.text)
            if canonical == "units":
                page_units = page_units or parsed.get("unit")
            facts.append(
                DrawingFact(
                    fact_id=make_drawing_fact_id(stem, p, "note", str(n.number)),
                    page=p,
                    region="note",
                    key=str(n.number),
                    label=f"Note {n.number}",
                    canonical=canonical,
                    value=n.text,
                    confidence="vision",
                    parsed=parsed,
                )
            )
        units = units or page_units
        dim_index = 0
        for text in page.dimensions:
            parsed_callout = parse_callout(text)
            if parsed_callout is None:
                continue
            kind, values = parsed_callout
            dim_index += 1
            facts.append(
                DrawingFact(
                    fact_id=make_drawing_fact_id(stem, p, "dimension", str(dim_index)),
                    page=p,
                    region="dimension",
                    key=str(dim_index),
                    kind=kind,
                    label=KIND_LABEL[kind],
                    value=text,
                    unit=page_units if kind not in ("angle", "thread") else None,
                    confidence="vision",
                    parsed=values,
                )
            )
        for i, text in enumerate((t for t in page.other_text if not is_view_title(t)), start=1):
            facts.append(
                DrawingFact(
                    fact_id=make_drawing_fact_id(stem, p, "text", str(i)),
                    page=p,
                    region="text",
                    key=str(i),
                    label="Text",
                    value=text,
                    confidence="vision",
                )
            )
    # Dimensions read before the unit declaration was seen still get the drawing's unit.
    for f in facts:
        if f.region == "dimension" and f.unit is None and f.kind not in ("angle", "thread"):
            f.unit = units
    legible = any(p.legible for p in reading.pages)
    warnings = [w for w in old.warnings if not w.startswith("scanned image")]
    warnings.append(
        "read from a scanned image by the vision model; values are not verifiable against "
        f"text in the file ({reading.reason})"
        if legible
        else f"the vision model could not read the scan ({reading.reason})"
    )
    if (
        part_number
        and (key := normalize_part_key(part_number))
        and old.part_number
        and (normalize_part_key(old.part_number) != key)
    ):
        warnings.append(
            f"the scan's title block reads part {part_number}; the drawing was linked as "
            f"{old.part_number}"
        )
    return old.model_copy(
        update={
            "facts": facts,
            "readable": legible,
            "extraction": "vision" if legible else "none",
            "units": units,
            "current_revision": revision,
            "title": title,
            "warnings": warnings,
        }
    )


class VisionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        store: FileStore,
        provider: VisionProvider | None,
        prices: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._factory = session_factory
        self._store = store
        self._provider = provider
        self._prices = prices or {}

    @property
    def available(self) -> bool:
        return self._provider is not None

    def _load(self, part_key: str, file_name: str) -> DrawingSlice:
        with session_scope(self._factory) as session:
            record = get_part(session, part_key)
        drawing = next(
            (d for d in (record.drawings if record else []) if d.file == file_name), None
        )
        if drawing is None or not drawing.scanned:
            raise ScanNotFoundError(f"part {part_key} has no scanned drawing named {file_name}")
        return drawing

    async def read_scan(
        self,
        part_key: str,
        file_name: str,
        request_id: str | None = None,
        conversation_id=None,
    ) -> DrawingSlice:
        drawing = await run_in_threadpool(self._load, part_key, file_name)
        if drawing.extraction == "vision":
            return drawing  # already read; idempotent
        if self._provider is None:
            raise VisionUnavailableError(
                "no vision-capable model is configured (Claude is needed; the Groq fallback "
                "reads text only)"
            )
        pages: list[tuple[int, bytes]] = []
        for page in drawing.pages[:MAX_SCAN_PAGES]:
            png = await run_in_threadpool(
                self._store.page_png, drawing.sha256, page.page, SCAN_DPI, page.correction
            )
            if png is None:
                raise ScanNotFoundError(
                    f"the original bytes of {file_name} are not in the file store; re-ingest it"
                )
            pages.append((page.page, png))
        started = time.perf_counter()
        status, error = "ok", None
        try:
            reading = await self._provider.read(pages, file_name)
        except ProviderError as exc:
            status, error = "vision_error", str(exc)
            raise
        finally:
            call = CallRecord(
                provider=f"{self._provider.name}:vision",
                model=self._provider.model,
                attempt=1,
                status=status,
                latency_ms=int((time.perf_counter() - started) * 1000),
                usage=Usage(),
                error=error,
            )
            await run_in_threadpool(self._log_call, call, part_key, request_id, conversation_id)
        updated = facts_from_reading(drawing, reading)
        await run_in_threadpool(self._save, file_name, updated)
        log.info("vision.read_scan", part=part_key, file=file_name, facts=len(updated.facts))
        return updated

    def _save(self, file_name: str, updated: DrawingSlice) -> None:
        with session_scope(self._factory) as session:
            replace_drawing(session, file_name, updated)

    def _log_call(self, call: CallRecord, part_key: str, request_id, conversation_id) -> None:
        with session_scope(self._factory) as session:
            conv_repo.save_llm_calls(
                session,
                [call],
                request_id=request_id,
                conversation_id=conversation_id,
                part_key=part_key,
                prompt_sha256=None,
                prices=self._prices,
                fallback_reason=None,
            )
