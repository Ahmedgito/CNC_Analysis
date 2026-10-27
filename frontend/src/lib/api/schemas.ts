import { z } from "zod";

/** Mirrors backend/app/domain/record.py and answer.py. Parsing fails loudly on contract drift. */

export const SourceStatus = z.object({
  available: z.boolean(),
  files: z.array(z.string()).default([]),
  note: z.string().nullable().optional(),
  /** PDF only: false when a drawing has no text layer and has not been read yet. */
  readable: z.boolean().nullable().optional(),
  scanned: z.array(z.string()).default([]),
  current_revision: z.string().nullable().optional(),
  /** IGES only: true when the current model is one closed, valid solid. */
  valid: z.boolean().nullable().optional(),
});
export type SourceStatus = z.infer<typeof SourceStatus>;

export const Sources = z.record(z.string(), SourceStatus);

export const CellRef = z.object({
  cell_id: z.string(),
  file: z.string(),
  sheet: z.string(),
  row: z.number(),
  col: z.string(),
  header: z.string(),
  canonical: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
  value: z.string(),
  value_type: z.string(),
  hidden: z.boolean().default(false),
  comment: z.string().nullable().optional(),
  formula: z.string().nullable().optional(),
});
export type CellRef = z.infer<typeof CellRef>;

export const SheetSlice = z.object({
  file: z.string(),
  sheet: z.string(),
  kind: z.enum(["attributes", "rows"]),
  header_row: z.number(),
  hidden: z.boolean().default(false),
  columns: z.array(
    z.object({
      col: z.string(),
      header: z.string(),
      canonical: z.string().nullable().optional(),
      unit: z.string().nullable().optional(),
    }),
  ),
  rows: z.array(
    z.object({
      row: z.number(),
      cells: z.array(CellRef),
      stale: z.boolean().default(false),
      stale_reason: z.string().nullable().optional(),
    }),
  ),
  banner: z.array(CellRef).default([]),
  /** Archive sheets, superseded revisions: history, never the current value. */
  stale: z.boolean().default(false),
  stale_reason: z.string().nullable().optional(),
  layout: z.enum(["table", "card"]).default("table"),
  default_unit: z.string().nullable().optional(),
});
export type SheetSlice = z.infer<typeof SheetSlice>;

export const Region = z.enum(["title_block", "note", "dimension", "revision", "text"]);
export type Region = z.infer<typeof Region>;

/** Drawing coordinates are PDF points with a top-left origin, on the upright (corrected) page. */
export const BBox = z.array(z.number()).length(4);

export const DrawingFact = z.object({
  fact_id: z.string(),
  page: z.number(),
  region: Region,
  key: z.string(),
  kind: z.string().nullable().optional(),
  label: z.string(),
  canonical: z.string().nullable().optional(),
  value: z.string(),
  unit: z.string().nullable().optional(),
  confidence: z.enum(["exact", "inferred", "vision"]).default("exact"),
  stale: z.boolean().default(false),
  stale_reason: z.string().nullable().optional(),
  bboxes: z.array(BBox).default([]),
  points_to: z.string().nullable().optional(),
});
export type DrawingFact = z.infer<typeof DrawingFact>;

export const DrawingPage = z.object({
  page: z.number(),
  width: z.number(),
  height: z.number(),
  rotation: z.number().default(0),
  correction: z.number().default(0),
  role: z.enum(["drawing", "revision_history", "text", "scanned", "blank"]),
  units: z.string().nullable().optional(),
});
export type DrawingPage = z.infer<typeof DrawingPage>;

export const DrawingSlice = z.object({
  file: z.string(),
  file_stem: z.string(),
  sha256: z.string(),
  page_count: z.number(),
  pages: z.array(DrawingPage),
  facts: z.array(DrawingFact),
  part_number: z.string().nullable().optional(),
  part_number_source: z.enum(["title_block", "text", "filename"]).nullable().optional(),
  title: z.string().nullable().optional(),
  current_revision: z.string().nullable().optional(),
  units: z.string().nullable().optional(),
  readable: z.boolean(),
  scanned: z.boolean(),
  extraction: z.enum(["text", "vision", "none"]),
  warnings: z.array(z.string()).default([]),
});
export type DrawingSlice = z.infer<typeof DrawingSlice>;

export const Verdict = z.enum([
  "agree",
  "agree_after_conversion",
  "equivalent_by_convention",
  "within_tolerance",
  "consistent",
  "not_modelled",
  "disagree",
  "excel_only",
  "pdf_only",
  "iges_only",
  "not_comparable",
]);
export type Verdict = z.infer<typeof Verdict>;

export const SourceKind = z.enum(["excel", "pdf", "iges"]);
export type SourceKind = z.infer<typeof SourceKind>;

export const CheckSide = z.object({
  source: SourceKind,
  facts: z.array(z.string()).default([]),
  value: z.string().nullable().optional(),
  normalised: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
});
export type CheckSide = z.infer<typeof CheckSide>;

/** One field compared across the spreadsheet, the drawing and the 3D model. */
export const CrossCheck = z.object({
  field: z.string(),
  label: z.string(),
  verdict: Verdict,
  excel: z.array(z.string()).default([]),
  pdf: z.array(z.string()).default([]),
  iges: z.array(z.string()).default([]),
  excel_value: z.string().nullable().optional(),
  pdf_value: z.string().nullable().optional(),
  iges_value: z.string().nullable().optional(),
  sides: z.array(CheckSide).default([]),
  /** "excel~pdf" | "excel~iges" | "pdf~iges" -> verdict for that pair of files. */
  pairs: z.record(z.string(), Verdict).default({}),
  odd_one_out: SourceKind.nullable().optional(),
  /** Fact ids of the statements that differ from the rest. */
  dissent: z.array(z.string()).default([]),
  detail: z.string(),
});
export type CrossCheck = z.infer<typeof CrossCheck>;

export const ModelFeature = z.object({
  feature_id: z.string(),
  kind: z.enum([
    "header",
    "envelope",
    "body",
    "boss",
    "bore",
    "hole",
    "hole_pattern",
    "counterbore",
    "chamfer",
    "fillet",
  ]),
  label: z.string(),
  canonical: z.string().nullable().optional(),
  value: z.string(),
  numbers: z.record(z.string(), z.number()).default({}),
  unit: z.string().nullable().optional(),
  confidence: z.enum(["exact", "inferred", "vision", "measured"]).default("measured"),
  method: z.string().default(""),
  faces: z.array(z.number()).default([]),
  anchor: z.array(z.number()).nullable().optional(),
  axis: z.array(z.number()).nullable().optional(),
  segments: z.array(z.array(z.number())).default([]),
  stale: z.boolean().default(false),
  stale_reason: z.string().nullable().optional(),
});
export type ModelFeature = z.infer<typeof ModelFeature>;

export const ModelSlice = z.object({
  file: z.string(),
  file_stem: z.string(),
  sha256: z.string(),
  header: z.object({
    sending_system: z.string().nullable().optional(),
    units: z.string().nullable().optional(),
    units_declared: z.boolean().default(true),
    created: z.string().nullable().optional(),
  }),
  topology: z.enum(["solid", "multi_solid", "open_shell", "wireframe", "empty"]),
  valid: z.boolean().default(false),
  bodies: z.number().default(0),
  faces: z.number().default(0),
  part_number: z.string().nullable().optional(),
  part_number_source: z.enum(["header", "filename"]).nullable().optional(),
  revision: z.string().nullable().optional(),
  form: z.enum(["turned", "prismatic", "unknown"]).default("unknown"),
  features: z.array(ModelFeature).default([]),
  mesh: z
    .object({
      lods: z.array(z.number()),
      triangles: z.record(z.string(), z.number()).default({}),
      bounds: z.array(z.array(z.number())).nullable().optional(),
    })
    .nullable()
    .optional(),
  views: z.array(z.string()).default([]),
  kernel: z.string().default(""),
  extractor_version: z.number().default(1),
  warnings: z.array(z.string()).default([]),
});
export type ModelSlice = z.infer<typeof ModelSlice>;

/** The citable id of a model feature, as the backend builds it. */
export const modelFactId = (m: Pick<ModelSlice, "file_stem">, featureId: string) =>
  `${m.file_stem}!m!${featureId}`;

export const PartRecord = z.object({
  part_key: z.string(),
  display_part_number: z.string(),
  base_key: z.string(),
  suffix: z.string().nullable().optional(),
  sources: Sources,
  sheets: z.array(SheetSlice),
  available_fields: z.array(z.string()),
  warnings: z.array(z.string()).default([]),
  drawings: z.array(DrawingSlice).default([]),
  models: z.array(ModelSlice).default([]),
  cross_checks: z.array(CrossCheck).default([]),
  aliases: z.array(z.string()).default([]),
});
export type PartRecord = z.infer<typeof PartRecord>;

export const PartSummary = z.object({
  part_key: z.string(),
  display_part_number: z.string(),
  description: z.string().nullable(),
  sources: Sources,
  files: z.array(z.string()),
});
export type PartSummary = z.infer<typeof PartSummary>;

export const PartList = z.object({ parts: z.array(PartSummary), total: z.number() });
export const PartDetail = z.object({ record: PartRecord, related: z.array(z.string()).default([]) });
export type PartDetail = z.infer<typeof PartDetail>;

export const AnswerStatus = z.enum([
  "answered",
  "computed",
  "not_found",
  "clarify",
  "needs_consent",
  "blocked",
  "part_not_found",
  "invalid_question",
  "error",
]);
export type AnswerStatus = z.infer<typeof AnswerStatus>;

/** One verified fact behind an answer: a spreadsheet cell or a value printed on a drawing. */
export const Evidence = z.object({
  fact_id: z.string(),
  source: SourceKind.default("excel"),
  file: z.string(),
  locator: z.string().default(""),
  header: z.string(),
  canonical: z.string().nullable(),
  value: z.string(),
  quoted: z.string(),
  hidden: z.boolean().default(false),
  stale: z.boolean().default(false),
  confidence: z.enum(["exact", "inferred", "vision", "measured"]).default("exact"),
  auto_linked: z.boolean().default(false),
  sheet: z.string().nullable().optional(),
  cell: z.string().nullable().optional(),
  row: z.number().nullable().optional(),
  page: z.number().nullable().optional(),
  region: z.string().nullable().optional(),
  bbox: z.array(z.number()).nullable().optional(),
  feature: z.string().nullable().optional(),
  method: z.string().nullable().optional(),
  anchor: z.array(z.number()).nullable().optional(),
});
export type Evidence = z.infer<typeof Evidence>;

export const Computation = z.object({
  label: z.string(),
  expression: z.string(),
  working: z.string(),
  result: z.number(),
  display: z.string(),
  unit: z.string().nullable(),
  inputs: z.array(z.object({ name: z.string(), fact_id: z.string(), value: z.string(), number: z.number() })),
  constants: z.array(z.number()).default([]),
});
export type Computation = z.infer<typeof Computation>;

export const AskAction = z.object({
  id: z.literal("read_scan"),
  file: z.string(),
  label: z.string(),
  reply: z.string(),
});

export const AskResult = z.object({
  message_id: z.string().nullable().optional(),
  conversation_id: z.string().nullable().optional(),
  part_number: z.string(),
  question: z.string(),
  status: AnswerStatus,
  answer: z.string(),
  evidence: z.array(Evidence).default([]),
  computation: Computation.nullable().optional(),
  general_knowledge: z.array(z.string()).default([]),
  missing_information: z.array(z.string()).default([]),
  available_fields: z.array(z.string()).default([]),
  suggestions: z.array(z.string()).default([]),
  confidence: z.enum(["high", "medium", "low"]),
  verification: z
    .object({
      citations_checked: z.number(),
      citations_verified: z.number(),
      auto_linked: z.number(),
      dropped: z.array(z.object({ fact_id: z.string(), quoted: z.string(), reason: z.string() })),
      unsupported_numbers: z.array(z.string()),
    })
    .nullable()
    .optional(),
  provider: z
    .object({
      provider: z.string(),
      model: z.string(),
      fallback_used: z.boolean(),
      fallback_reason: z.string().nullable(),
      refusal_fallback_used: z.boolean().default(false),
      attempts: z.number(),
      latency_ms: z.number(),
    })
    .nullable()
    .optional(),
  sources: Sources.default({}),
  cross_checks: z.array(CrossCheck).default([]),
  /** Things the user can approve, e.g. reading a scanned drawing; never done without a yes. */
  actions: z.array(AskAction).default([]),
  warnings: z.array(z.string()).default([]),
  request_id: z.string().nullable().optional(),
});
export type AskResult = z.infer<typeof AskResult>;
export type AskAction = z.infer<typeof AskAction>;

export const Stage = z.enum([
  "validating",
  "loading_record",
  "reading_scan",
  "asking_llm",
  "verifying",
  "computing",
  "saving",
]);
export const StageEvent = z.object({ stage: Stage, detail: z.string().nullable().optional() });
export type StageEvent = z.infer<typeof StageEvent>;

export const Problem = z.object({
  title: z.string(),
  status: z.number().optional(),
  detail: z.string().optional(),
  request_id: z.string().nullable().optional(),
  suggestions: z.array(z.string()).optional(),
});
export type Problem = z.infer<typeof Problem>;
