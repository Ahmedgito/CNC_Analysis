"""Resolve user-typed part numbers to stored records.

Lookup order: the identity key (``P-3001`` and ``003003`` are written that way in some files but
are parts ``3001`` and ``3003``), the key as typed, then a unique match on the base number
(``3004`` finds ``3004-A`` when that is the only part numbered 3004). A typed revision suffix is
respected: ``2281-B`` never silently resolves to ``2281``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.domain.record import PartRecord
from app.ingestion.parts import base_of, identity_key, normalize_part_key, split_part_key
from app.repositories.parts import get_part, parts_with_base, suggest_parts


@dataclass(slots=True)
class Resolution:
    query: str
    key: str | None
    record: PartRecord | None
    suggestions: list[str] = field(default_factory=list)
    resolved_by: str | None = None  # exact | identity | base

    @property
    def found(self) -> bool:
        return self.record is not None


def resolve_part(session: Session, raw: str) -> Resolution:
    key = normalize_part_key(raw)
    if key is None:
        return Resolution(query=raw, key=None, record=None)
    ident = identity_key(key)
    for candidate, how in ((ident, "identity"), (key, "exact")):
        record = get_part(session, candidate)
        if record is not None:
            return Resolution(raw, record.part_key, record, resolved_by=how)
    _, affix = split_part_key(ident)
    if affix is None:  # the user typed a bare number; a unique revisioned part is a safe match
        candidates = parts_with_base(session, base_of(key))
        if len(candidates) == 1 and (record := get_part(session, candidates[0])):
            return Resolution(raw, record.part_key, record, resolved_by="base")
    return Resolution(query=raw, key=key, record=None, suggestions=suggest_parts(session, key))
