import { z } from "zod";
import { readSse } from "@/lib/sse";
import {
  AskResult,
  PartDetail,
  PartList,
  Problem,
  StageEvent,
  type AskResult as AskResultT,
  type StageEvent as StageEventT,
} from "./schemas";

/** Browser calls go through the same-origin proxy route, so no CORS and SSE is unbuffered. */
export const API_BASE = "/api/backend";

export class ApiError extends Error {
  constructor(
    public status: number,
    public problem: Problem,
  ) {
    super(problem.detail ?? problem.title);
  }
}

async function failure(resp: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    /* non-JSON error body */
  }
  const parsed = Problem.safeParse(body);
  return new ApiError(
    resp.status,
    parsed.success ? parsed.data : { title: `HTTP ${resp.status}`, detail: resp.statusText },
  );
}

export async function listParts(q?: string) {
  const url = q ? `${API_BASE}/parts?q=${encodeURIComponent(q)}` : `${API_BASE}/parts`;
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw await failure(resp);
  return PartList.parse(await resp.json());
}

export async function getPart(partNumber: string) {
  const resp = await fetch(`${API_BASE}/parts/${encodeURIComponent(partNumber)}`, {
    cache: "no-store",
  });
  if (!resp.ok) throw await failure(resp);
  return PartDetail.parse(await resp.json());
}

/** A drawing page rendered upright as PNG; the server caches it, so the URL is stable. */
export function drawingPageUrl(partNumber: string, file: string, page: number, dpi = 110) {
  return `${API_BASE}/parts/${encodeURIComponent(partNumber)}/drawings/${encodeURIComponent(file)}/pages/${page}.png?dpi=${dpi}`;
}

const modelBase = (partNumber: string, file: string) =>
  `${API_BASE}/parts/${encodeURIComponent(partNumber)}/models/${encodeURIComponent(file)}`;

/**
 * Binary glTF of a model: one mesh per measured feature (node name = feature id). Artifacts are
 * served as immutable, so the extractor version is part of the URL: a rebuilt mesh gets a new
 * cache key instead of a stale browser copy.
 */
export function modelMeshUrl(partNumber: string, file: string, lod: 0 | 1 = 1, version = 1) {
  return `${modelBase(partNumber, file)}/mesh.glb?lod=${lod}&v=${version}`;
}

/** Hidden-line projection of a model as SVG (front, top or right). */
export function modelViewUrl(partNumber: string, file: string, view: string, version = 1) {
  return `${modelBase(partNumber, file)}/views/${encodeURIComponent(view)}.svg?v=${version}`;
}

/**
 * The part report as a PDF file: summary, sources, cross-check, record, drawings, models and,
 * with a conversation id, the questions asked with their verified sources.
 */
export async function downloadReport(partNumber: string, conversationId?: string | null) {
  const query = conversationId ? `?conversation=${encodeURIComponent(conversationId)}` : "";
  const resp = await fetch(`${API_BASE}/parts/${encodeURIComponent(partNumber)}/report.pdf${query}`, {
    cache: "no-store",
  });
  if (!resp.ok) throw await failure(resp);
  const name =
    /filename="([^"]+)"/.exec(resp.headers.get("content-disposition") ?? "")?.[1] ??
    `part-${partNumber}-report.pdf`;
  const url = URL.createObjectURL(await resp.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  // Revoke after the click has been handled, or some browsers cancel the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type AskOptions = {
  conversationId?: string | null;
  signal?: AbortSignal;
  onStage?: (stage: StageEventT) => void;
};

/** Ask over SSE: stage events arrive while the pipeline works, then the verified answer. */
export async function askStream(
  partNumber: string,
  question: string,
  { conversationId, signal, onStage }: AskOptions = {},
): Promise<AskResultT> {
  const resp = await fetch(`${API_BASE}/parts/${encodeURIComponent(partNumber)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
    signal,
  });
  if (!resp.ok || !resp.body) throw await failure(resp);
  for await (const msg of readSse(resp.body)) {
    if (msg.event === "stage") {
      const parsed = StageEvent.safeParse(JSON.parse(msg.data));
      if (parsed.success) onStage?.(parsed.data);
    } else if (msg.event === "answer") {
      return AskResult.parse(JSON.parse(msg.data));
    } else if (msg.event === "error") {
      const p = Problem.safeParse(JSON.parse(msg.data));
      throw new ApiError(500, p.success ? p.data : { title: "Stream error" });
    }
  }
  throw new ApiError(502, { title: "Stream ended", detail: "The server closed the stream early." });
}

export const Readiness = z.object({
  status: z.string(),
  database: z.boolean(),
  parts: z.number().optional(),
  providers: z.record(z.string(), z.unknown()).optional(),
});
export type Readiness = z.infer<typeof Readiness>;

/** Backend readiness: database reachable, parts indexed, which LLM keys are configured. */
export async function getReadiness(signal?: AbortSignal) {
  const resp = await fetch(`${API_BASE}/readyz`, { cache: "no-store", signal });
  if (!resp.ok) throw await failure(resp);
  return Readiness.parse(await resp.json());
}
