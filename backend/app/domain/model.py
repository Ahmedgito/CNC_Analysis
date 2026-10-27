"""IGES 3D models as stored in a part record.

A ``ModelSlice`` is one model file's contribution to a part: what its header declares, how its
geometry closed up (one valid solid, several, an open shell, curves only) and the features the
app measured from it. Every feature becomes one citable fact, ``<file stem>!m!<feature id>``.

Values here are measurements the app made from geometry, not text someone wrote, so each feature
records ``method``: how it was measured. Nothing a model cannot prove (material, tolerance,
finish, threads, mass) ever appears here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.evidence import Confidence

Topology = Literal["solid", "multi_solid", "open_shell", "wireframe", "empty"]
PartForm = Literal["turned", "prismatic", "unknown"]
FeatureKind = Literal[
    "header",  # declared in the file's Global section (units, system, dates)
    "envelope",  # overall size in the part's own frame
    "body",  # volume, surface area, body count
    "boss",  # an outer cylindrical surface: the OD, a step
    "bore",  # a hole on the main axis
    "hole",  # one hole off the main axis
    "hole_pattern",  # several equal holes: circular (PCD), grid or linear
    "counterbore",
    "chamfer",
    "fillet",
]
VIEWS = ("front", "top", "right")


def make_model_fact_id(file_stem: str, feature_id: str) -> str:
    return f"{file_stem}!m!{feature_id}"


class ModelHeader(BaseModel):
    """The Global section, parsed as text (no kernel), so these facts are exact."""

    sending_system: str | None = None
    product_id: str | None = None
    file_name: str | None = None
    units_flag: int | None = None
    units_name: str | None = None
    units: str | None = None  # normalised: mm | in | cm | m | ft | um | mil | uin
    units_declared: bool = True  # False when the flag is missing and the IGES default applies
    model_scale: float = 1.0
    resolution: float | None = None
    created: str | None = None  # file generation date as written
    author: str | None = None
    organization: str | None = None
    start_text: str | None = None  # the Start section: free text, data only, never instructions


class ModelFeature(BaseModel):
    feature_id: str  # "od_1", "bore", "hole_pattern_1", "envelope", "volume", "hdr.units"
    kind: FeatureKind
    label: str  # "Outer diameter", "Hole pattern 1"
    canonical: str | None = None  # outer_diameter, bore, holes, length, thickness, volume, ...
    value: str  # what a person reads: "6 × Ø10 through on Ø90 PCD"
    numbers: dict[str, float] = Field(default_factory=dict)  # {"count": 6, "diameter_mm": 10}
    unit: str | None = "mm"
    confidence: Confidence = "measured"
    method: str = ""  # how the value was measured, shown on hover and given to the model
    body: int = 1
    faces: list[int] = Field(default_factory=list)  # face indices, for highlighting
    anchor: list[float] | None = None  # a 3D point (mm) the viewer frames
    axis: list[float] | None = None  # unit direction, for cylindrical features
    # Axis segments of each cylinder in the feature, [ax, ay, az, bx, by, bz] in mm, so the
    # projections and the viewer can mark every hole of a pattern.
    segments: list[list[float]] = Field(default_factory=list)
    stale: bool = False
    stale_reason: str | None = None


class MeshInfo(BaseModel):
    lods: list[int]  # available levels of detail (0 = fine)
    triangles: dict[str, int] = Field(default_factory=dict)  # "0" -> count
    face_feature: dict[str, str] = Field(default_factory=dict)  # face index -> feature id
    bounds: list[list[float]] | None = None  # [[xmin, ymin, zmin], [xmax, ymax, zmax]] in mm


class ModelSlice(BaseModel):
    file: str
    file_stem: str
    sha256: str
    header: ModelHeader
    topology: Topology
    valid: bool = False  # one closed, valid solid (volume is meaningful)
    bodies: int = 0
    faces: int = 0
    part_number: str | None = None
    part_number_source: Literal["header", "filename"] | None = None
    revision: str | None = None
    revision_source: Literal["filename", "header"] | None = None
    form: PartForm = "unknown"
    features: list[ModelFeature] = Field(default_factory=list)
    mesh: MeshInfo | None = None
    views: list[str] = Field(default_factory=list)
    kernel: str = ""  # "OCCT 8.0.1"
    extractor_version: int = 1
    warnings: list[str] = Field(default_factory=list)

    def feature(self, feature_id: str) -> ModelFeature | None:
        return next((f for f in self.features if f.feature_id == feature_id), None)

    def by_kind(self, *kinds: str) -> list[ModelFeature]:
        return [f for f in self.features if f.kind in kinds and not f.stale]
