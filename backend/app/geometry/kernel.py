"""The only module family that talks to OpenCascade: read an IGES file and measure it.

``process_model`` turns IGES bytes into a ``ModelSlice`` (header, topology, measured features)
plus the viewer artifacts (binary glTF meshes, hidden-line SVG projections). It runs inside the
geometry worker process (``app.geometry.worker``); nothing kernel-typed leaves this package.

Reading steps:
1. Header and limits from the text (``app.geometry.header``), before the kernel sees the file.
2. Transfer every root entity with lengths converted to millimetres.
3. Sew faces (faces-mode exports are loose trimmed surfaces) and classify the topology: one
   closed valid solid, several solids, an open shell, curves only.
4. Measure features (``app.geometry.features``) and build artifacts.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.model import ModelFeature, ModelSlice
from app.geometry.errors import ModelLimitError, UnreadableModelError
from app.geometry.header import NotIgesError, entity_count, read_header

EXTRACTOR_VERSION = 2  # bump when measurements or artifacts change
MAX_BYTES = 25 * 1024 * 1024
MAX_ENTITIES = 200_000
MAX_FACES = 20_000


@dataclass(slots=True)
class GeometryResult:
    slice: ModelSlice
    meshes: dict[int, bytes] = field(default_factory=dict)  # lod -> GLB bytes
    views: dict[str, str] = field(default_factory=dict)  # view -> SVG text


@contextlib.contextmanager
def quiet_stdout():
    """OpenCascade prints progress ("Total number of loaded entities") to the C stdout. Redirect
    file descriptor 1 so it never mixes with structured logs."""
    try:
        saved = os.dup(1)
    except OSError:  # no real stdout (some embedded hosts)
        yield
        return
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)


def kernel_version() -> str:
    try:
        from OCP.Standard import Standard_Version  # type: ignore[import-not-found]

        return f"OCCT {Standard_Version.String_s()}"
    except Exception:
        return "OCCT"


_REV_RE = re.compile(
    r"(?:^|[_\-\s.])rev(?:ision)?[_\-\s.]?([A-Z]{1,2}|\d{1,2})(?=$|[_\-\s.])", re.I
)
_PART_RE = re.compile(r"^(?:[A-Z]{1,4}[-_ ]?)?(\d{3,})")


def revision_from_name(name: str) -> str | None:
    m = _REV_RE.search(Path(name).stem)
    return m.group(1).upper() if m else None


def part_number_from_text(text: str | None) -> str | None:
    """A part number in a header field or file name: leading digits, optionally prefixed."""
    if not text:
        return None
    m = _PART_RE.match(Path(text.strip()).stem.upper())
    return m.group(0).replace("_", "-") if m else None


def _read_shape(data: bytes):
    from OCP.IFSelect import IFSelect_RetDone  # type: ignore[import-not-found]
    from OCP.IGESControl import IGESControl_Reader  # type: ignore[import-not-found]
    from OCP.Interface import Interface_Static  # type: ignore[import-not-found]

    # The reader needs a path. Write to a private temp file and delete it right after.
    fd, tmp = tempfile.mkstemp(suffix=".igs")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        with quiet_stdout():
            Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
            reader = IGESControl_Reader()
            if reader.ReadFile(tmp) != IFSelect_RetDone:
                raise UnreadableModelError(
                    "the IGES reader rejected the file (damaged or truncated)"
                )
            roots = reader.NbRootsForTransfer()
            reader.TransferRoots()
            shape = reader.OneShape()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    if shape is None or shape.IsNull():
        raise UnreadableModelError("the file contains no geometry the kernel could transfer")
    return shape, roots


def process_model(
    data: bytes,
    file_name: str,
    sha256: str,
    *,
    max_bytes: int = MAX_BYTES,
    max_entities: int = MAX_ENTITIES,
    artifacts: bool = True,
) -> GeometryResult:
    """Read, measure and render one IGES file. Raises UnreadableModelError / ModelLimitError."""
    if len(data) > max_bytes:
        raise ModelLimitError(
            f"{file_name} is {len(data) / 1e6:.1f} MB; the limit is {max_bytes / 1e6:.0f} MB"
        )
    try:
        header = read_header(data)
    except NotIgesError as exc:
        raise UnreadableModelError(str(exc)) from exc
    n_entities = entity_count(data)
    if n_entities == 0:
        raise UnreadableModelError("the file has no directory entries (no geometry)")
    if n_entities > max_entities:
        raise ModelLimitError(f"{file_name} has {n_entities} entities; the limit is {max_entities}")

    from app.geometry.features import measure  # imports OCP

    stem = Path(file_name).stem
    warnings: list[str] = []
    try:
        shape, roots = _read_shape(data)
        geometry = measure(shape, stem, header, warnings)
    except (UnreadableModelError, ModelLimitError):
        raise
    except Exception as exc:  # kernel exceptions (Standard_Failure and friends)
        raise UnreadableModelError(_plain_kernel_error(exc)) from exc
    if roots == 0:
        warnings.append("the file declares no root entities; every entity was transferred")

    part_number, pn_source = None, None
    for text, source in (
        (header.product_id, "header"),
        (header.file_name, "header"),
        (file_name, "filename"),
    ):
        if (
            source == "header"
            and text
            and text.strip().lower() in ("filename.iges", "filename.igs")
        ):
            continue
        pn = part_number_from_text(text)
        if pn:
            part_number, pn_source = pn, source
            break
    revision = revision_from_name(file_name)
    if not header.units_declared:
        warnings.append("the file does not declare units; the IGES default (inches) was applied")
    if header.model_scale != 1.0:
        warnings.append(
            f"the header declares a model-space scale of {header.model_scale:g}; values are "
            "reported "
            "as stored in the file, not rescaled"
        )

    slice_ = ModelSlice(
        file=file_name,
        file_stem=stem,
        sha256=sha256,
        header=header,
        topology=geometry.topology,
        valid=geometry.valid,
        bodies=geometry.bodies,
        faces=len(geometry.faces),
        part_number=part_number,
        part_number_source=pn_source,  # type: ignore[arg-type]
        revision=revision,
        revision_source="filename" if revision else None,
        form=geometry.form,
        features=_header_features(header, revision, file_name) + geometry.features,
        kernel=kernel_version(),
        extractor_version=EXTRACTOR_VERSION,
        warnings=warnings,
    )
    result = GeometryResult(slice=slice_)
    if artifacts and geometry.faces:
        from app.geometry.mesh import build_meshes
        from app.geometry.projection import build_views

        try:
            result.meshes, slice_.mesh = build_meshes(geometry)
        except Exception as exc:
            warnings.append(f"3D mesh could not be built: {_plain_kernel_error(exc)}")
        try:
            result.views = build_views(geometry)
            slice_.views = sorted(result.views)
        except Exception as exc:
            warnings.append(f"2D projections could not be drawn: {_plain_kernel_error(exc)}")
    return result


def _plain_kernel_error(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc).strip()
    if "Bnd_Box is void" in text:
        return "the geometry is empty or incomplete (the file may be truncated)"
    return f"the geometry kernel failed ({name}{': ' + text if text else ''})"


def _header_features(h, revision: str | None = None, file_name: str = "") -> list[ModelFeature]:
    out: list[ModelFeature] = []
    if revision:
        out.append(
            ModelFeature(
                feature_id="hdr.revision",
                kind="header",
                label="Revision (from the file name)",
                canonical="revision",
                value=revision,
                unit=None,
                confidence="inferred",
                method=f"read from the file name {file_name}; IGES has no revision field",
            )
        )
    if h.units:
        how = (
            f"Global section units flag {h.units_flag}"
            + (f" ({h.units_name})" if h.units_name else "")
            if h.units_declared
            else "no units flag in the Global section; IGES default"
        )
        out.append(
            ModelFeature(
                feature_id="hdr.units",
                kind="header",
                label="Units",
                canonical="units",
                value=h.units if h.units_declared else f"{h.units} (not declared; IGES default)",
                unit=None,
                confidence="exact" if h.units_declared else "inferred",
                method=how,
            )
        )
    if h.sending_system:
        out.append(
            ModelFeature(
                feature_id="hdr.system",
                kind="header",
                label="Created by",
                value=h.sending_system,
                unit=None,
                confidence="exact",
                method="Global section, native system field",
            )
        )
    if h.created:
        out.append(
            ModelFeature(
                feature_id="hdr.created",
                kind="header",
                label="File date",
                value=h.created,
                unit=None,
                confidence="exact",
                method="Global section, file generation date",
            )
        )
    return out
