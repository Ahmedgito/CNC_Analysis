"""IGES models: meshes for the 3D viewer, hidden-line projections, unlinked models."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import ProblemError, SessionDep, StoreDep
from app.api.drawings import _record
from app.domain.model import VIEWS, ModelSlice
from app.domain.record import PartRecord
from app.repositories.parts import unlinked_models

router = APIRouter(tags=["models"])
_IMMUTABLE = "public, max-age=31536000, immutable"


def _model(record: PartRecord, file_name: str) -> ModelSlice:
    model = next((m for m in record.models if m.file == file_name), None)
    if model is None:
        raise ProblemError(
            404,
            "Model not found",
            f"Part {record.display_part_number} has no 3D model named '{file_name}'.",
        )
    return model


@router.get(
    "/parts/{part_number}/models/{file_name}/mesh.glb",
    summary="The model as binary glTF: one mesh per measured feature, plus sharp edges",
    response_class=Response,
    responses={200: {"content": {"model/gltf-binary": {}}}, 404: {"description": "Unknown model"}},
)
def model_mesh(
    part_number: str,
    file_name: str,
    session: SessionDep,
    store: StoreDep,
    lod: Annotated[int, Query(ge=0, le=1, description="0 = fine, 1 = coarse")] = 1,
) -> Response:
    model = _model(_record(session, part_number), file_name)
    if model.mesh is None or lod not in model.mesh.lods:
        raise ProblemError(404, "Mesh not available", f"{file_name} has no mesh at level {lod}.")
    glb = store.mesh(model.sha256, lod)
    if glb is None:
        raise ProblemError(
            404,
            "Model file missing",
            f"The mesh of {file_name} is not in the file store; re-ingest the file.",
        )
    return Response(
        glb,
        media_type="model/gltf-binary",
        headers={"Cache-Control": _IMMUTABLE, "ETag": f'"{model.sha256[:16]}-m{lod}"'},
    )


@router.get(
    "/parts/{part_number}/models/{file_name}/views/{view}.svg",
    summary="A hidden-line projection of the model (front, top or right)",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}, 404: {"description": "Unknown view"}},
)
def model_view(
    part_number: str,
    file_name: str,
    view: Literal["front", "top", "right"],
    session: SessionDep,
    store: StoreDep,
) -> Response:
    model = _model(_record(session, part_number), file_name)
    if view not in model.views or view not in VIEWS:
        raise ProblemError(404, "View not available", f"{file_name} has no {view} projection.")
    svg = store.view(model.sha256, view)
    if svg is None:
        raise ProblemError(
            404,
            "Model file missing",
            f"The projections of {file_name} are not in the file store; re-ingest the file.",
        )
    return Response(
        svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": _IMMUTABLE,
            "ETag": f'"{model.sha256[:16]}-{view}"',
            # The SVG is ours, but it is served as a document: never let it run script.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/models/unlinked",
    response_model=list[ModelSlice],
    summary="Models that matched no part number",
)
def models_unlinked(session: SessionDep) -> list[ModelSlice]:
    return unlinked_models(session)
