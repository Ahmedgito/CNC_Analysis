import { z } from "zod";

/** Mirrors backend/app/domain/record.py and answer.py. Parsing fails loudly on contract drift. */

export const SourceStatus = z.object({
  available: z.boolean(),
  files: z.array(z.string()).default([]),
  note: z.string().nullable().optional(),
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
  rows: z.array(z.object({ row: z.number(), cells: z.array(CellRef) })),
  banner: z.array(CellRef).default([]),
});
export type SheetSlice = z.infer<typeof SheetSlice>;

export const PartRecord = z.object({
  part_key: z.string(),
  display_part_number: z.string(),
  base_key: z.string(),
  suffix: z.string().nullable().optional(),
  sources: Sources,
  sheets: z.array(SheetSlice),
  available_fields: z.array(z.string()),
  warnings: z.array(z.string()).default([]),
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
  "blocked",
  "part_not_found",
  "invalid_question",
  "error",
]);
export type AnswerStatus = z.infer<typeof AnswerStatus>;

export const Evidence = z.object({
  cell_id: z.string(),
  file: z.string(),
  sheet: z.string(),
  cell: z.string(),
  row: z.number(),
  header: z.string(),
  canonical: z.string().nullable(),
  value: z.string(),
  quoted: z.string(),
  hidden: z.boolean().default(false),
  auto_linked: z.boolean().default(false),
});
export type Evidence = z.infer<typeof Evidence>;

export const Computation = z.object({
  label: z.string(),
  expression: z.string(),
  working: z.string(),
  result: z.number(),
  display: z.string(),
  unit: z.string().nullable(),
  inputs: z.array(
    z.object({ name: z.string(), cell_id: z.string(), cell_value: z.string(), number: z.number() }),
  ),
  constants: z.array(z.number()).default([]),
});
export type Computation = z.infer<typeof Computation>;

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
      dropped: z.array(z.object({ cell_id: z.string(), quoted: z.string(), reason: z.string() })),
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
  warnings: z.array(z.string()).default([]),
  request_id: z.string().nullable().optional(),
});
export type AskResult = z.infer<typeof AskResult>;

export const Stage = z.enum([
  "validating",
  "loading_record",
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
