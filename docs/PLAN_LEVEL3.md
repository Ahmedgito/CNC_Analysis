# Level 3: IGES 3D models and the three-way cross-check — design and implementation plan

Status: proposed 2026-10-27, awaiting review. Branch to create: `level3-iges-models` (from
`level2-pdf-drawings`).

## 1. Context

The brief for Level 3:

> Add the 3D model. Also read the IGES model and use geometry facts you can extract reliably.
> Cross-check the three sources and flag anything that disagrees. Every answer cites its
> evidence.

Levels 1 and 2 are done: spreadsheets and PDF drawings are read into one source-neutral `Fact`
model (ADR 0006), every citation is checked in code before it is shown, the spreadsheet and the
drawing are cross-checked field by field (ADR 0007), and scanned drawings are read only after
the user agrees (ADR 0008). The seams for a third source are already there:
`SourceKind = "excel" | "pdf" | "iges"`, `sources.iges` on every record, and an IGES badge in
the UI.

Level 3 adds a third kind of evidence that is unlike the other two. A spreadsheet cell and a
drawing callout are **text a person wrote**. A 3D model holds **geometry**, and every number
taken from it (a diameter, a hole count, a volume) is a *measurement* the app makes. So
"reliably" carries the design: the app reports only what the geometry proves, says how each
value was measured, and never makes up attributes the model does not hold (material,
tolerance, finish, thread class).

Decisions already made by the user (2026-10-27):

| Question | Decision |
|---|---|
| How to read IGES geometry | **OpenCascade required**: one kernel path for everything |
| What the UI shows for the model | **3D viewer plus 2D projections**: an interactive viewer with faces you can highlight, plus three hidden-line projections that also act as the no-WebGL fallback |

Judging weights and what they mean here:

| Criterion | Weight | Level 3 consequence |
|---|---|---|
| Evidence-based answers that name the source | 30% | Model facts cite `file › Model › Feature`; clicking a chip frames that feature in the 3D view |
| Sources combined and cross-checked | 25% | Every comparable field is checked across all three sources; the explanation names the source that disagrees with the other two, and no value is silently "corrected" |
| Honesty and robustness | 15% | Only geometry the kernel proves; open shells, assemblies, wireframes and unknown units degrade to explicit "not derivable" facts with reasons |
| Engineering quality | 15% | Kernel isolated in a worker process with limits; artifacts cached by content hash; ADRs; models from other exporters as test data |

## 2. What the models contain (verified 2026-10-27)

### 2.1 The files

Eight models, `docs/spec26_synthetic_data/iges/` (2280–2283) and `docs/spec26_batch2_hard/iges/`
(3001–3004). **2284 has none on purpose** (the missing-file case). The organizers ship no IGES:
these were written by `tools/generate_iges.py` (build123d / OpenCascade 8.0) from the answer
keys. 2283 is modelled at Ø48, from the drawing, so the planted Ø50 in the spreadsheet stands
out three ways.

All eight share one exporter profile: `Open CASCADE IGES processor 8.0`, units flag 2 (`MM`),
resolution 1e-7, **faces mode**: trimmed surfaces (type 144) over planes (108) and surfaces of
revolution (120), bounded by lines (110), circular arcs (100) and B-spline curves (126). No
solids (186), no NURBS surfaces (128), no colours, names or properties.

### 2.2 What OpenCascade reliably extracts (throwaway spike, `cadquery-ocp-novtk` 8.0.1.1)

| Part | Envelope (mm) | Bosses | Holes / bores | Volume (mm³) | Matches the answer key |
|---|---|---|---|---|---|
| 2280 flange | 120 × 120 × 20 | Ø120 | Ø40 bore; 6 × Ø10 on Ø90 PCD | 191 637.15 | yes (volume checked by hand: π·20·(60²−20²) − 6·π·5²·20) |
| 2281 shaft | 30 × 30 × 200 | Ø30 × 160, Ø25 × 40 (stepped) | none | 132 732.29 | yes |
| 2282 bracket | 101.6 × 63.5 × 9.525 | — | 4 × Ø6.35 | 60 244.89 | yes (4.000 × 2.500 × 0.375 in, holes 0.250 in) |
| 2283 bushing | 48 × 48 × 40 | **Ø48** | Ø30 bore | 44 107.96 | yes (spreadsheet says Ø50) |
| 3001 gear blank | 80 × 80 × 15 | Ø80 | Ø25 bore | 68 035.12 | yes (its drawing is an unread scan) |
| 3002 coupling hub | 55 × 55 × 40 | Ø55 | Ø20 bore; 1 × Ø5 radial, through the wall into the bore | 82 122.44 | yes (Ø5 is the M6 tap drill) |
| 3003 base plate | 200 × 120 × 15 | — | **4** × Ø14 | 350 763.72 | yes (part card says 6) |
| 3004 shaft collar | 50.8 × 50.8 × 19.05 | Ø50.8 | Ø25.4 bore | 28 958.33 | yes (2.000 × 0.750 in, bore 1.000 in) |

Every model sewed into a single valid solid (`BRepCheck_Analyzer`), read in under 10 ms and
meshed in under 30 ms. Hidden-line projections took 30–120 ms per view; the flange's front view
has 45 hidden edges (the holes), drawn dashed the way a drawing draws them.

Findings that shape the design:

1. **Cylinders come in as surfaces of revolution, not `Cylinder` surfaces.** A face is recognised
   as a cylinder when its generatrix is a line parallel to the axis (exact), or by
   `ShapeAnalysis_CanonicalRecognition` within 1e-4 mm (for NURBS exports, labelled `inferred`).
2. **Hole versus boss** is decided by the face normal, with orientation, pointing toward the
   axis. Exact for every model.
3. **OpenCascade splits a full cylinder into two 180° faces.** Features are built by merging
   faces with the same radius on the same axis line; the summed sweep must reach 360° to count
   as a full hole.
4. **The naive PCD test gives a false positive**: the four corner holes of a rectangular plate
   are equidistant from their centroid (Ø178.9 "PCD" on 3003). A circular pattern must be centred
   on the part's turning axis or a coaxial bore and have equal angular spacing; otherwise it is a
   linear or grid pattern with its pitch (3003: 2 × 2 grid, 160 × 80).
5. **Axis-aligned boxes are wrong for rotated models.** The flange rotated 30° about two axes
   gives a 121 × 117 × 77 box; the oriented box (`AddOBB`) gives 120 × 120 × 20. The envelope is
   measured in the part's own frame: the main axis for turned parts, the oriented box otherwise.
6. **OpenCascade writes to stdout on every read** ("Total number of loaded entities"). The worker
   redirects file descriptors 1 and 2 so this never reaches the API log stream.
7. **A truncated file fails deep in the kernel** (`Standard_ConstructionError: Bnd_Box is void`),
   not at read time. Every kernel exception maps to `UnreadableModelError` with a plain reason.
8. **Kernel weight.** `cadquery-ocp` pulls in VTK and matplotlib (570 MB installed);
   **`cadquery-ocp-novtk`** is the same kernel without them, 166 MB with no other dependencies,
   and gave identical results. Import takes about 0.55 s, so the worker stays warm.

### 2.3 What a model cannot tell us, and the app will say so

Material, tolerance, surface finish, heat treatment, thread form or class, revision (unless the
file name or header carries it), cost, weight (a model has volume, not mass), and anything in a
drawing note. Chamfers and fillets are often left out of models, so "no chamfer in the model"
is reported as *not modelled*, never as a disagreement with the drawing's note.

## 3. Acceptance criteria (Level 3)

1. Every `.igs` / `.iges` file (detected by content, not extension) ingests into model facts with
   provenance: file, body, feature, the faces it came from, and how it was measured.
2. Reliable facts per model: units as declared, envelope, main axis and part form (turned or
   prismatic), outer diameters and steps with lengths, bores and holes (diameter, through or
   blind and depth, axis), hole patterns (count, PCD or grid pitch), volume and surface area of a
   closed valid solid, body count, solid validity. Anything not proven is absent, with a reason in
   the warnings.
3. The answer to "what is X" cites every source that states X; when they disagree it gives each
   source's value and names the one that differs. Majority never overrides; nothing is corrected.
4. Three-way cross-check verdicts reproduce every planted case (section 8) with no false
   `disagree` on the eight models or on the other-exporter fixtures.
5. Model questions that were "not in the files" in Level 1 and 2 (volume, envelope, hole
   positions) are now answered and cited; weight stays "not in the files" (section 5.6).
6. The UI shows the model in 3D with the cited feature highlighted, three projections, and a
   compare view where selecting a value in any source highlights the matching value in the
   other two.
7. A malformed, hostile or huge IGES file never crashes or stalls the API: it fails in the
   worker with a reason, and partial results are never stored.
8. All tests and the offline eval pass with no API keys; CI and Docker install the kernel from
   a pinned wheel.

## 4. Architecture

```
                                  ┌──────────────── geometry worker (subprocess, pool of 1–2) ───────────────┐
upload .igs ─► sniff (S/G/D/P/T  │ read (IGESControl) ─► sew ─► solid? ─► validate ─► units/scale           │
              record structure) ─►│      ─► surfaces: plane | cylinder | cone | torus | other (recognised)  │
                                  │      ─► features: bosses, bores, holes, steps, patterns, envelope       │
                                  │      ─► mass props ─► mesh (GLB) ─► HLR projections (SVG ×3)            │
                                  │ limits: 25 MB, 200k entities, 30 s, 1.5 GB RSS; stdout silenced         │
                                  └──────────────────────────────────┬────────────────────────────────────────┘
                                                                     │ ModelSlice (facts + feature graph)
                         FileStore: models/{sha}.igs, meshes/{sha}_{lod}.glb, views/{sha}_{view}.svg
                                                                     ▼
            part record  ── sheets (Excel) + drawings (PDF) + models (IGES) ──► three-way cross-check
                                                                     ▼
                           prompt <model> block ─► LLM ─► verifier (measured facts) ─► answer
```

### 4.1 Geometry kernel and the worker boundary (`app/geometry/`)

OpenCascade is C++ behind Python bindings. A bad file can segfault it, loop in sewing, or use
gigabytes of memory, and any of these would take a FastAPI worker down. So all kernel calls run
in a separate process:

- `app/geometry/worker.py`: a `ProcessPoolExecutor` (spawn context, `max_tasks_per_child=50`,
  1–2 workers) started lazily and warmed at startup when `AUTO_INGEST` or the first upload needs
  it. Each job gets a wall-clock timeout (30 s), a memory cap (Job Object on Windows,
  `RLIMIT_AS` on Linux) and an fd-level redirect of stdout/stderr. A crash or timeout kills that
  worker, raises `GeometryTimeoutError` / `GeometryCrashError` with the file name, and the
  pool replaces the worker.
- `app/geometry/kernel.py`: the only module that imports `OCP`. Pure functions from bytes to
  plain Pydantic models; nothing kernel-typed crosses the process boundary.
- The API process never imports `OCP`. Tests that need geometry run it in-process through the
  same functions (fast), and one integration test runs it through the pool.

Dependency: `cadquery-ocp-novtk==8.0.1.1.0` (exact pin, runtime). OpenCascade is LGPL-2.1 with
the OCCT exception and is linked dynamically through the wheel, which is fine for this project.
ADR 0009 records the choice and the rejected options: a pure-Python reader (lighter, but
re-implements a kernel badly as soon as files carry NURBS or solids), and `cadquery-ocp` with
VTK (570 MB for rendering features the app does not use).

### 4.2 Reading and normalising (`app/geometry/read.py`)

- **Sniffing**: an IGES file is fixed 80-column records with a section letter in column 73
  (`S`, `G`, `D`, `P`, `T`) and a terminate record. Detected by structure, so a `.txt` IGES or an
  `.igs` holding a PDF is handled right. Binary and compressed IGES are rejected as unsupported.
  `.step` / `.stp` gets a specific message (the kernel reads STEP too; it is a listed stretch
  goal, not silently half-supported).
- **Header facts** from the Global section: sending system, file name field, units flag and name,
  model-space scale, resolution, created date, author or organization. The header is parsed
  without the kernel, so units and the declared file name are cited from text in the file
  (`confidence="exact"`).
- **Units**: the kernel converts everything to mm (`xstep.cascade.unit = MM`); every fact keeps
  `source_unit` so answers can say "the model is in inches; 0.250 in = 6.35 mm". Flag 3 (named
  unit) is resolved from the name; a missing flag means inches per the IGES spec, and that is
  stated ("units not declared; IGES default is inches"). A model-space scale other than 1 is
  applied and reported.
- **Topology**: transfer all roots, sew at 1e-4 mm (or 10× the declared resolution, whichever is
  larger), then classify: one closed valid solid / several solids (assembly or multi-body) /
  open shell / wireframe only. Volume and area only come from a closed valid solid; a negative
  volume (shell inside out) is reversed and noted.

### 4.3 Feature recognition (`app/geometry/features.py`)

Deterministic and conservative: every feature records the faces it came from and the rule that
produced it, so the evidence can say *how* the value was measured.

| Feature | Rule | Confidence |
|---|---|---|
| Surface type | native analytic type; revolution of a line parallel to the axis = cylinder, inclined = cone; canonical recognition for B-spline faces within 1e-4 mm | `measured` / `inferred` |
| Cylindrical feature | faces merged by radius, axis direction and axis line; summed sweep ≥ 359.9° = full | `measured` |
| Hole vs boss | face normal (with orientation) points to the axis = hole | `measured` |
| Through vs blind | through when both ends of the hole open onto other faces (the outside or another bore, as for 3002's radial hole into the bore); blind when one end is closed by a floor face | `measured` |
| Depth | blind holes only: axial distance from the opening to the floor (a hole meeting a curved bore has no single length, so none is claimed) | `measured` |
| Main axis, part form | turned if the largest boss is coaxial with ≥ 80% of the volume's span; else prismatic | `measured` |
| Steps | coaxial bosses with different radii, ordered along the axis, each with its length | `measured` |
| Counterbore / counterdrill | coaxial holes of different radius sharing an end | `measured` |
| Circular pattern | ≥ 3 equal holes, parallel axes, centres on a circle whose centre is on the main axis, equal angular spacing within 0.01° | `measured` |
| Linear / grid pattern | equal holes on a 1-D or 2-D lattice; pitch reported | `measured` |
| Envelope | turned: max boss Ø × axial length; prismatic: oriented box L × W × T, sorted | `measured` |
| Chamfer / fillet | conical / toroidal faces adjacent to a boss or a hole end | `measured`, informational |
| Volume, surface area, centroid | mass properties of the closed valid solid | `measured` |

Rejected on purpose: thread recognition (IGES has no thread data; a Ø5 hole is reported as a
Ø5 hole, and the cross-check explains the M6 tap-drill convention), tolerances and fits (a
model is nominal), and material from entity names or colours (not reliable across exporters).

### 4.4 Domain and fact grammar (`app/domain/model.py`)

```python
class ModelFeature(BaseModel):
    feature_id: str          # "hole_pattern_1", "bore", "od_1", "envelope"
    kind: Literal["envelope", "boss", "bore", "hole", "hole_pattern", "step", "counterbore",
                  "chamfer", "fillet", "body", "header"]
    label: str               # "Hole pattern 1", "Outer diameter", "Bore"
    value: str               # "6 × Ø10 through on Ø90 PCD" (what a person reads)
    numbers: dict[str, float]  # {"count": 6, "diameter_mm": 10, "pcd_mm": 90}
    unit: Literal["mm"] = "mm"
    source_unit: str | None  # units declared in the file
    confidence: Literal["measured", "inferred", "exact"]
    method: str              # "6 cylindrical faces merged from 12; normals point to axis; ..."
    faces: list[int]         # face indices in the mesh, for highlighting
    anchor: list[float]      # 3D point the camera frames
    stale: bool = False

class ModelSlice(BaseModel):
    file: str; file_stem: str; sha256: str
    header: ModelHeader      # system, units, scale, resolution, date, declared file name
    topology: Literal["solid", "multi_solid", "open_shell", "wireframe"]
    valid: bool; bodies: int
    part_number: str | None; part_number_source: Literal["header", "filename"] | None
    revision: str | None     # from the file name ("_RevB") or header, never guessed
    form: Literal["turned", "prismatic", "unknown"]
    features: list[ModelFeature]
    mesh: MeshInfo | None    # lods, triangle counts, face→feature map
    views: list[str]         # "front", "top", "right"
    warnings: list[str]
```

Fact id grammar, extending ADR 0006:

- IGES: `<stem>!m!<feature_id>` and `<stem>!m!<feature_id>.<number>` for a number inside a
  feature, e.g. `2280_flange!m!hole_pattern_1`, `2283_bushing!m!od_1`, `2280_flange!m!volume`,
  `2282_bracket!m!hdr.units`.

`Fact` gains `source="iges"`, `confidence="measured"` ("computed by the app from the model's
geometry"; the verifier compares the cited value with the stored measurement, exactly like
cells), and `feature` / `anchor` provenance. Locator: `Model › Hole pattern 1`.

### 4.5 Storage (Alembic `0003_models`)

- `ingest_run`: `kind` gains `model`; `geometry_ms`, `kernel_version`.
- `part_fragment`: `kind = "model"`, `model JSONB` (the `ModelSlice`).
- New `model_fact` table, the audit row a model citation joins back to (same shape as
  `drawing_fact`: run, part, fact id, feature, kind, value, numbers JSONB, confidence, stale,
  generated `text_search`).
- `FileStore`: `models/{sha}.igs`, `meshes/{sha}_{lod}.glb` (two levels of detail),
  `views/{sha}_{view}_{theme}.svg`. Content-addressed and immutable, so cache headers are
  `immutable` and re-ingesting the same bytes is a no-op.
- `cnc rebuild` regroups existing records; `cnc ingest` takes `.igs` alongside `.xlsx` and
  `.pdf`; `cnc reset-drawing` generalises to `cnc reprocess <file>` (re-extract any source with
  the current extractor version).

### 4.6 Linking and revisions (`app/ingestion/model.py`)

- Part number from the Global section's product id or file name field when it holds a 3+ digit
  identity (`identity_key`), otherwise from the file name (`3001_gear_blank.igs` → 3001). The
  source is recorded and shown ("linked by file name").
- Header and file name disagree: link by header, warn, show both.
- Revision from `_RevB` / `-rev-b` / `REV B` in the file name or a header field. Two models for
  one part: highest revision current, the others `stale` with a reason; equal or no revisions:
  the newest header date wins, and the warning says the choice was made by date.
- A model whose revision differs from the current drawing revision gets a record warning
  ("model is Rev A, drawing is Rev B") and its facts stay in play but the cross-check says so.

### 4.7 Three-way cross-check (`app/services/crosscheck.py`, ADR 0010)

`CrossCheck` grows from two sides to N, keeping the Level 2 fields so stored records still load:

```python
class CheckSide(BaseModel):
    source: Literal["excel", "pdf", "iges"]
    facts: list[str]; value: str | None; normalised_mm: float | None; note: str | None

class CrossCheck(BaseModel):
    field: str; label: str
    verdict: Verdict                       # overall = worst pairwise verdict
    sides: list[CheckSide]                 # one per source that states the field
    pairs: dict[str, Verdict]              # "excel~pdf", "excel~iges", "pdf~iges"
    odd_one_out: Literal["excel", "pdf", "iges"] | None
    detail: str
    excel: list[str]; pdf: list[str]; excel_value: str | None; pdf_value: str | None  # Level 2 compatibility
```

Rules (all in code, the model never decides a verdict):

| Field | Spreadsheet | Drawing | Model | Rule |
|---|---|---|---|---|
| Outer diameter | finished size Ø | diameter callout | largest boss | equal within ε after unit conversion |
| Bore | "bore Ø" | bore callout | largest coaxial hole | equal within ε |
| Length / height | turned length, plate dims | unlabelled dims (only confirm) | envelope along main axis / sorted OBB | equal within ε |
| Thickness | plate T | `THK` callout | smallest OBB side (prismatic) | equal within ε |
| Steps | "Ø25 × 40 step" | stepped diameters | step list | each step matched |
| Holes (count, Ø) | hole details | hole-pattern callout | hole features minus the main bore | count and Ø equal |
| PCD | "on Ø90 PCD" | `PCD` callout | circular pattern | equal within ε |
| Thread | `M6 tapped` | `M6` callout | radial hole Ø | Ø equals the ISO 261 coarse tap drill (M6 → 5.0) ⇒ `equivalent_by_convention` |
| Stock envelope | raw stock | — | envelope | stock ≥ envelope on every axis ⇒ `consistent`; smaller ⇒ `disagree` ("the part does not fit in the stock") |
| Chamfer | — | chamfer note | chamfer faces | absent in model ⇒ `not_modelled` (never `disagree`) |

- ε = 0.005 mm, or 1e-4 relative for values above 50 mm. The model is nominal geometry, so a
  real difference above ε is a disagreement. **New verdict `within_tolerance`**: the difference
  exceeds ε but is inside the drawing's stated general tolerance (for example Ø49.95 against
  Ø50 ±0.1). A person should look at it; it is not reported as a clean agreement.
- **New verdicts** `consistent` (stock envelope) and `not_modelled` (features models often leave
  out). `excel_only` / `pdf_only` become "only one source states it".
- Units: the model is always in known units; spreadsheet units resolve as in Level 2. The model
  joins the corroboration pool used to infer an undeclared spreadsheet unit, so 2283's
  unlabelled `Ø50 x 40` is still compared in mm, never flipped to a match by unit guessing.
- **Odd one out**: when two sources agree and the third differs, `odd_one_out` names it and the
  detail says so: "The drawing (2283_bushing.pdf) and the model (2283_bushing.igs) both give
  Ø48; the job card (job_cards_B.xlsx › E5) says Ø50." The app never says which one is right.
- Stale facts (archive sheets, superseded drawing revisions, older models) never enter a check.
- A non-solid or multi-body model only contributes the fields that are still well defined
  (holes on a shell are fine; envelope of an assembly is not), and each skip is explained.
- Material, tolerance and finish stay two-way (the model holds none of them); the check lists
  the model as "does not state".

### 4.8 Answer pipeline

- **Prompt**: a `<model file=… units=… form=turned topology=solid>` block lists feature facts
  in the existing line grammar (`[id] Label -> canonical unit=mm flags = "value"`, with the new
  flag `measured`), and `<cross_checks>` shows the sides and the odd one out. Rules added: model
  values are measured nominal geometry and are cited like any fact; the model never supplies
  material, tolerance, finish, threads or weight; when three sources disagree, give every
  value and name the differing source; a measured value is not "more correct" than a written
  one.
- **Verifier**: checks quoted values against model facts. Numbers in an answer may come from a
  feature's `numbers` (6, 10, 90 in "6 × Ø10 on Ø90 PCD"); the unsupported-number check accepts
  them.
- **Compute**: volume conversions (mm³ ↔ cm³ ↔ in³) through pint; `pi` allowed as a constant so
  "how much material is removed from Ø125 × 25 stock" is `pi·62.5²·25 − volume`, computed with
  the working shown and both inputs cited.
- **Weight policy (decision for review)**: weight stays "not in the provided files". The answer
  may add the cited model volume and say that mass needs a density the files do not give. It
  does not multiply by a textbook density, because that would fill a missing field from general
  knowledge, which rule 2 forbids. Golden row N04 keeps `not_found`.
- **Volume and envelope questions** (golden N07 "what is the volume of the 3D model?") move
  from `not_found` to `answered` with the model fact cited.
- **Scan plus model (3001)**: geometry questions are answered from the model at once; the
  drawing is still offered for consented reading, and the answer says the drawing has not been
  read, so the model value is not cross-checked against it yet.
- **Offline rules adapter**: model-aware rules for envelope, volume, holes, diameters and
  three-way check summaries, so CI and the offline eval cover Level 3 with no keys.

### 4.9 API

| Method & path | Purpose |
|---|---|
| `POST /ingest` | accepts `.igs` / `.iges`; per-file summary adds `kind=model`, topology, units, feature counts, linked part |
| `GET /parts/{pn}` | record now has `models[]` and N-way `cross_checks[]` |
| `GET /parts/{pn}/models/{file}/mesh.glb?lod=0\|1` | binary glTF: one primitive per feature, node names = fact ids, plus a sharp-edge line set; `immutable` cache |
| `GET /parts/{pn}/models/{file}/views/{front\|top\|right}.svg` | hidden-line projection: visible edges solid, hidden edges dashed, `currentColor` strokes so it themes; feature markers carry `data-fact-id` |
| `GET /models/unlinked` | models that matched no part |
| `POST /admin/reprocess` | re-extract a file with the current extractor (replaces `reset-drawing`) |

All errors stay RFC 7807. Mesh size is capped (≤ 300k triangles at LOD 0, ≤ 30k at LOD 1,
deflection = 0.1% of the envelope diagonal) so a huge model cannot stall the browser.

### 4.10 Frontend (Tailwind utilities only)

**Model tab** in the record viewer, one per model:

- **3D viewer** (`three` 0.18x, plain three with a small React hook; no react-three-fiber, to
  keep the bundle small; loaded with `next/dynamic` only when the tab opens): orbit / pan / zoom,
  preset views (front, top, right, iso) and a view cube, a **section toggle** (clipping plane
  through the main axis, so bores are visible), edges on/off, ghosted mode. Faces are coloured
  by feature: bosses neutral, holes cyan, patterns teal, chamfers violet. Light and dark
  materials come from the theme tokens. `prefers-reduced-motion` turns off camera tweens.
- **Feature list** beside the viewer: label, value, how it was measured (tooltip), and the
  three-way verdict pill when the feature takes part in a check. Hover highlights the faces;
  click frames them.
- **Projections strip**: front, top and right SVGs under the viewer. Clicking one sets the 3D
  camera to that view. They become the main view if WebGL is unavailable or the context is
  lost.
- **Measurements overlay**: envelope dimensions drawn as dimension lines in 3D, in mm, with the
  source unit in brackets when the file was not in mm.

**Synchronised selection across sources** (the "sync" in the brief): selecting any fact, from a
chip, a cross-check side, a drawing box, a spreadsheet cell or a model face, resolves through the
cross-check correspondences to the **same field in the other two sources**. The primary
selection pulses amber; its counterparts get a softer outline in their own views. A
**Compare view** (toggle in the record header, on wide screens) shows the drawing page and the
3D model side by side above the spreadsheet row, so clicking "Outer diameter" lights up E5, the
Ø48 callout and the boss face together. One `useFactSelection` store (React context and a
reducer: `primary`, `related`, `origin`) replaces the per-component `selectedFactId` props, so
the three views stay consistent by construction.

**Cross-check tab** becomes a three-column table (Spreadsheet | Drawing | Model), with pairwise
connectors coloured by verdict and the odd one out outlined in rose. Filter chips: "Disagree",
"Needs a look" (`within_tolerance`, `not_comparable`), "Agree".

**Elsewhere**: evidence chips for model facts (cube icon, `file › Model › Feature`; hover shows
the measuring method; click opens the Model tab and frames the feature); the IGES source badge
goes live; the answer card's cross-check block shows three columns; home copy: "Level 3 live:
Excel, PDF and IGES, cross-checked three ways".

**States**: model processing (ingest is synchronous, so only on upload), no model for this part,
open shell or wireframe (viewer still renders and shows a banner explaining which facts are
missing), multi-body (body picker), WebGL unavailable (projections only), very large mesh (LOD 1
first, LOD 0 on demand).

## 5. Edge cases and their defined behaviour

| Case | Behaviour |
|---|---|
| No model for the part (2284) | `sources.iges.available=false`; model questions: "no 3D model is ingested for this part" |
| Faces-mode export (all 8 samples) | Sewn into a solid; volume reported only if the solid is valid |
| Exact-solid export (type 186), as from `generate_iges.py --brep` | Read directly; same facts |
| NURBS-only surfaces (type 128) | Canonical recognition within 1e-4 mm; facts labelled `inferred` with the deviation |
| Open shell (gaps after sewing) | Envelope and holes kept; volume and area "not derivable: surfaces do not close"; warning lists the free edges |
| Wireframe only (curves, no surfaces) | Envelope from curves (`inferred`); no features; banner in the viewer |
| Several solids | Facts per body; part-level envelope, volume and OD checks `not_comparable` with the reason; body picker in the UI |
| Inch model (fixture), mm records | Converted to mm in facts; `source_unit=in` shown; cross-check `agree_after_conversion` |
| Units flag missing or unknown | IGES default (inches) applied and stated; any check that depends on it is `not_comparable` unless another source corroborates the unit |
| Model-space scale ≠ 1 | Applied, cited from the header, warned |
| Rotated or off-origin model | Oriented frame; envelope correct; projections use the part's own axes |
| Revision in the file name (`3002_coupling_hub_RevB.igs`) | Revision B; matched to the drawing's current revision; mismatch warned |
| Two models for one part | Highest revision current; the other stale and kept for audit |
| File name and header disagree on part number | Link by header; warn; both shown |
| Model matches no part | Kept; listed by `/models/unlinked` and on the home page |
| Same bytes re-uploaded | Duplicate by sha256, no-op |
| Truncated / corrupted file | `422 Unreadable model` with the kernel reason in plain words; nothing stored |
| Not IGES despite `.igs` | `415` with a specific message |
| STEP file | `415`, "STEP is not supported yet" |
| Binary or compressed IGES | `415`, specific message |
| > 25 MB, > 200k entities, > 30 s, > 1.5 GB | Rejected with the limit that was hit; the worker is recycled |
| Kernel crash (segfault) | Worker dies, pool replaces it, `422 Model could not be processed`; the API stays up (integration test kills a worker) |
| Degenerate geometry (zero-volume faces, sliver faces) | Ignored below ε with a warning count |
| Radial / inclined holes (3002) | Axis direction reported; not counted in the axial hole pattern |
| Blind holes | Depth reported; "through" never claimed |
| Hole pattern not centred on the axis (rectangle of holes) | Grid pattern with pitch; never a PCD |
| Thread on the drawing, plain hole in the model | `equivalent_by_convention` via the tap-drill table, with the table cited as general knowledge |
| Chamfer in the drawing note, none in the model | `not_modelled` |
| Envelope smaller than a cited stock size | `consistent`; larger: `disagree` ("part does not fit in stock") |
| Model newer than the drawing revision | Warning; checks still run; the answer mentions it |
| Injection text in the Start section or header strings | Data, never instructions; header text appears only as cited facts; covered by a fixture |
| Path traversal in model file names | Basename only; sanitised in the mesh and view routes |
| WebGL unavailable / context lost | Projections become the main view; message in the viewer |

## 6. Test data beyond the generator

The eight models come from our own generator, so passing on them proves little about the
judges' files. The suite adds models built at test time with the kernel (no binary fixtures in
the repo), in `tests/fixtures/models.py`:

| Fixture | Purpose |
|---|---|
| `--brep` exports of all eight parts | Exact-solid path gives the same facts as faces mode |
| Flange in inches (`IGESControl_Writer("IN")`) | Unit conversion and `source_unit` |
| Flange rotated 30° about two axes and moved off the origin | Oriented envelope, axis detection |
| Bushing approximated as NURBS (`BRepBuilderAPI_NurbsConvert`) | Canonical recognition, `inferred` |
| Two separate solids in one file | Multi-body behaviour |
| Plate with one face removed | Open shell behaviour |
| Edges only | Wireframe behaviour |
| Counterbored hole, blind hole, radial hole, rectangular and linear patterns, chamfered shaft | Each feature rule |
| Truncated, zero-byte, wrong-section, huge entity count (synthesised D section), poisoned Start section | Guards and limits |

Every feature rule has a unit test on these. Every planted case has an end-to-end API test.

## 7. Work packages and order

TDD throughout: failing test, implementation, green. Days are estimates for one engineer.

| WP | Scope | Key files | Day |
|---|---|---|---|
| 0 | Kernel foundation: pin `cadquery-ocp-novtk`, worker pool with timeout, memory cap and stdout silencing, crash recovery, IGES sniffing, copy the 8 models into `data/`, ADR 0009 | `pyproject.toml`, `app/geometry/{worker,kernel}.py`, `app/ingestion/readers.py`, `Dockerfile`, CI | 1 |
| 1 | Reading: Global header parser, transfer, sewing, topology classification, validity, units and scale, guards; fixtures for every topology | `app/geometry/read.py`, `tests/fixtures/models.py`, `tests/unit/test_iges_read.py` | 1–2 |
| 2 | Features: surface recognition, cylinder merging, hole/boss, through/blind/depth, steps, counterbores, patterns (circular vs grid), envelope in the part frame, chamfers and fillets, mass properties | `app/geometry/features.py`, `tests/unit/test_features.py` | 2–3 |
| 3 | Domain, storage, linking: `ModelSlice`, fact grammar, `Fact` adapter, migration `0003_models`, repository, linking and revisions, record merge, `sources.iges`, CLI (`ingest`, `rebuild`, `reprocess`), ingest API | `app/domain/model.py`, `app/domain/evidence.py`, `alembic/versions/0003_models.py`, `app/repositories/parts.py`, `app/ingestion/model.py`, `app/services/ingest_service.py`, `app/cli.py` | 3–4 |
| 4 | Artifacts: tessellation to GLB (per-feature primitives, edge lines, two LODs), hidden-line SVG projections with feature markers, FileStore, mesh and view endpoints | `app/geometry/{mesh,glb,projection}.py`, `app/services/file_store.py`, `app/api/models.py` | 4 |
| 5 | Three-way cross-check: N-sided `CrossCheck` with Level 2 compatibility, model comparisons, ε and `within_tolerance`, stock envelope, tap-drill convention, `not_modelled`, odd one out, unit corroboration including the model; ADR 0010 | `app/domain/drawing.py` (or a new `app/domain/crosscheck.py`), `app/services/crosscheck.py`, `tests/unit/test_crosscheck3.py` | 5 |
| 6 | Answers: prompt `<model>` block and rules, verifier and compute (volume units, `pi`), offline rules, weight policy, scan-plus-model behaviour | `app/llm/{prompts,fake_adapter}.py`, `app/services/{verifier,compute,ask_service}.py` | 5–6 |
| 7 | Frontend: schemas and client, `useFactSelection` store, Model tab (three viewer, feature list, section, projections, measurements, WebGL fallback), Compare view, three-column cross-check, chips, badges, copy; Vitest for selection sync and schema parsing; checked in Chrome, light and dark, desktop and phone | `frontend/src/lib/{api,selection}`, `components/model-viewer/*`, `components/{record-viewer,cross-checks,answer-card,chat-panel,part-workspace,source-badges}.tsx` | 6–7 |
| 8 | Golden set and eval: ≈20 Level 3 rows, three-way precision and recall against the answer keys, Claude and Groq runs; README, ADRs 0010–0011, tracker, demo script | `evals/golden.jsonl`, `app/evaluation.py`, `README.md`, `docs/adr/*`, `docs/PROGRESS_TRACKER.md` | 7 |

Cut order if time runs short: Compare view (selection sync still works across tabs), section
toggle, LOD 1, counterbore and chamfer recognition. Never cut: worker isolation, the reliability
labels, the three-way check, citations.

ADRs: **0009** OpenCascade (no-VTK build) in an isolated worker process; **0010** three-way
cross-check: N sides, odd one out, ε versus tolerance, no majority vote; **0011** measured facts:
what counts as reliable geometry, and what a model must never be used to state.

## 8. Golden set additions (eval)

Expected verdicts come from the answer keys and the planted cases, not from the app's output.

| ID | Category | Part | Question | Expected |
|---|---|---|---|---|
| M01 | model_lookup | 2280 | What are the overall dimensions of the 3D model? | answered; 120 × 120 × 20; cites `2280_flange!m!envelope` |
| M02 | model_lookup | 2280 | What is the volume of the part? | answered; 191 637 mm³ (or 191.6 cm³); cites `!m!volume` (replaces N07) |
| M03 | model_lookup | 2281 | What diameters does the shaft have and how long is each step? | Ø30 × 160 and Ø25 × 40, cites the step features |
| M04 | three_agree | 2280 | How many holes, what size, and do all three files agree? | 6 × Ø10 on Ø90 PCD; holes verdict `agree` on all three pairs |
| M05 | three_agree | 3004 | Is the bore the same in every file? | Ø25.4 mm = 1.000 in; `agree_after_conversion`; three files cited |
| M06 | three_unit | 2282 | Do the drawing and the model agree on the bracket thickness? | 0.375 in = 9.525 mm; `agree_after_conversion` |
| M07 | three_disagree | 2283 | What is the outer diameter? | Ø48 from drawing and model, Ø50 from the job card; `odd_one_out = excel`; all three cited |
| M08 | three_disagree | 3003 | How many holes does the base plate have? | 4 (master list, drawing, model) against 6 (part card); the part card named as the one that differs |
| M09 | convention | 3002 | What thread is in the coupling hub, and does the model show it? | M6 on drawing and sheet; Ø5 radial hole in the model; `equivalent_by_convention` via tap drill |
| M10 | stock | 2280 | Does the part fit in the raw stock? | Ø125 × 25 stock against 120 × 120 × 20 envelope; `consistent`; both cited |
| M11 | computed | 2280 | How much material is removed from the stock? | computed: π·62.5²·25 − 191 637 ≈ 115 159 mm³; working shown |
| M12 | scan_plus_model | 3001 | What is the bore diameter? | answered Ø25 from the model and the master list; says the scanned drawing has not been read |
| M13 | scan_plus_model | 3001 | What does the drawing say? | `needs_consent` (unchanged) |
| M14 | missing_model | 2284 | What is the volume of the 3D model? | not_found: no model for 2284 |
| M15 | weight | 2281 | How much does the part weigh? | not_found; may cite the volume; must not state a mass (N04 unchanged) |
| M16 | model_limits | 2283 | What material does the 3D model specify? | not_found from the model; may say the sheet and drawing values |
| M17 | revision | 3002 | Which revision is the 3D model? | Rev B, from the file name; matches the drawing |
| M18 | units | 3004 | What units is the model in? | mm, cited from the header (`!m!hdr.units`) |
| M19 | model_lookup | 3002 | Is the radial hole through or blind? | through the wall into the bore, Ø5, radial; cites the hole feature; no depth claimed |
| M20 | identity | 003003 | What is the envelope of the plate? | 200 × 120 × 15; resolves the zero-padded spelling |

Eval additions: `three_way_precision` and `three_way_recall` (flagged disagreements against
the planted ones: 2283 OD and material, 3003 hole count; no false flags on 2280, 2281, 2282, 3002,
3004); per-source citation counts ("answers citing all three files"); the Level 3 pass count in
the README table. The report notes the circularity in section 6 and also reports the
other-exporter fixture results.

## 9. Verification

- `uv run pytest -q` (backend, kernel in-process plus one pool test), `pnpm test`, `pnpm lint`,
  `pnpm typecheck`, `pnpm build`: green with no API keys.
- `uv run cnc ingest ../data` with the 8 models added: report lists 8 models, all `solid`,
  `valid`, units mm, linked to 2280–2283 and 3001–3004; `GET /parts` shows IGES available for
  those and missing for 2284.
- Manual judge script in Chrome: 2283 OD and material show the job card as the odd one out, the
  Ø48 callout and the boss face light up together in Compare view; 3003 holes flag the part
  card; 2282 and 3004 agree after conversion with both units shown; 3002 thread explained by tap
  drill; 3001 answered from the model while the drawing still asks for consent; 2284 says no
  model; every answer names its files. Light and dark, desktop and phone; WebGL disabled shows
  the projections.
- Robustness: upload each hostile fixture; the API stays healthy (`/readyz`) and returns the
  specific problem; a killed worker is replaced.
- `uv run cnc eval --provider claude_code` and `--provider groq` on the extended golden set;
  numbers go into the README.
- Docker image builds with the pinned kernel wheel; CI caches it.

## 10. Risks and mitigations

- **The judges' IGES comes from a different exporter** (SolidWorks, Fusion, FreeCAD: NURBS
  faces, solids, inches, odd orientation). Fixtures cover each of those; recognition degrades to
  `inferred` or "not derivable" with a reason instead of guessing; every feature records its
  method so a wrong answer can be traced.
- **Kernel crashes or hangs on hostile input.** Isolated worker, hard limits, recycled workers,
  an integration test that kills one.
- **Dependency weight and platform wheels.** No-VTK build (166 MB); exact pin; Linux x86_64 and
  Windows wheels exist for 8.0.1.1. If a platform lacks one, ingest of `.igs` returns a clear
  503 ("3D geometry kernel unavailable") and everything else keeps working.
- **False disagreements from modelling noise.** ε is tight but explicit; `within_tolerance` for
  differences a person should review; chamfers `not_modelled`; stale sources excluded.
- **Over-trusting measured values.** The prompt and UI say a measurement is not more correct
  than a written value; the odd one out is named, never overruled.
- **Bundle size.** three.js loads only on the Model tab; projections render first, so the tab is
  useful before WebGL starts.
- **Timeboxing.** WP0–WP6 deliver the judged behaviour with projections only; the 3D viewer
  and Compare view are the first UI pieces to trim if needed.
