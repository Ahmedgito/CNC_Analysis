"""Geometry errors. Importable without the kernel, so the API can map them to responses."""

from __future__ import annotations


class UnreadableModelError(ValueError):
    """The file is IGES but its geometry could not be read (truncated, corrupt, empty)."""


class ModelLimitError(ValueError):
    """The file exceeds a processing limit (size, entities, time, memory)."""


class GeometryUnavailableError(RuntimeError):
    """The 3D geometry kernel is not installed or its worker cannot start."""
