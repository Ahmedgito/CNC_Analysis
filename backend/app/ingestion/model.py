"""IGES model ingestion: bytes in, a ``ModelSlice`` linked to a part out.

The geometry itself is measured in the isolated worker (``app.geometry.worker``); this module
only decides which part the model belongs to and packages what the worker returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.model import ModelSlice
from app.ingestion.parts import identity_key


@dataclass(slots=True)
class ModelIngestResult:
    file_name: str
    sha256: str
    slice: ModelSlice
    part_key: str | None  # normalised part number, None if the model names no part
    warnings: list[str] = field(default_factory=list)
    meshes: dict[int, bytes] = field(default_factory=dict)
    views: dict[str, str] = field(default_factory=dict)


def ingest_model_bytes(data: bytes, file_name: str, worker) -> ModelIngestResult:
    from app.ingestion.pipeline import sha256_bytes

    sha = sha256_bytes(data)
    result = worker.process(data, file_name, sha)
    m: ModelSlice = result.slice
    key = identity_key(m.part_number) if m.part_number else None
    if m.part_number_source == "filename" and key:
        m.warnings.append(f"no part number inside the model; linked by its file name ({key})")
    elif key is None:
        m.warnings.append(
            "no part number in the model header or file name; the model is not linked"
        )
    return ModelIngestResult(file_name, sha, m, key, list(m.warnings), result.meshes, result.views)


def _rev_key(rev: str | None) -> tuple[int, int, str]:
    if not rev:
        return (0, 0, "")
    return (1, int(rev), "") if rev.isdigit() else (1, 0, rev.rjust(2))


def mark_superseded_models(models: list[ModelSlice]) -> list[ModelSlice]:
    """With several models for one part, the highest revision is current; with no revisions to
    compare, the newest file date wins. Older models' features become history."""
    if len(models) < 2:
        return models
    ranked = sorted(
        models, key=lambda m: (_rev_key(m.revision), m.header.created or "", m.file), reverse=True
    )
    current = ranked[0]
    by_date = not any(m.revision for m in models)
    for m in ranked[1:]:
        reason = (
            f"older model (Rev {m.revision or '?'}; {current.file} Rev {current.revision} "
            "is current)"
            if not by_date
            else f"older model by file date ({current.file} is newer)"
        )
        for f in m.features:
            f.stale, f.stale_reason = True, reason
        m.warnings.append(reason)
    if by_date:
        current.warnings.append(
            "several models with no revision; the newest file date was taken as current"
        )
    return [current, *ranked[1:]]
