"""Resolve user-typed part numbers to stored records."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.domain.record import PartRecord
from app.ingestion.parts import normalize_part_key
from app.repositories.parts import get_part, suggest_parts


@dataclass(slots=True)
class Resolution:
    query: str
    key: str | None
    record: PartRecord | None
    suggestions: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.record is not None


def resolve_part(session: Session, raw: str) -> Resolution:
    key = normalize_part_key(raw)
    if key is None:
        return Resolution(query=raw, key=None, record=None)
    record = get_part(session, key)
    if record is not None:
        return Resolution(query=raw, key=key, record=record)
    return Resolution(query=raw, key=key, record=None, suggestions=suggest_parts(session, key))
