import { describe, expect, it } from "vitest";
import { parseSseBlock, readSse } from "./sse";

function streamOf(...chunks: (string | Uint8Array)[]) {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? enc.encode(c) : c);
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const out = [];
  for await (const msg of readSse(stream)) out.push(msg);
  return out;
}

describe("parseSseBlock", () => {
  it("reads event and data", () => {
    expect(parseSseBlock('event: stage\ndata: {"stage":"verifying"}')).toEqual({
      event: "stage",
      data: '{"stage":"verifying"}',
    });
  });

  it("ignores comments and joins multi-line data", () => {
    expect(parseSseBlock(": ping\nevent: answer\ndata: line1\ndata: line2")).toEqual({
      event: "answer",
      data: "line1\nline2",
    });
  });

  it("returns null for ping-only blocks", () => {
    expect(parseSseBlock(": ping - 2026-10-27")).toBeNull();
  });
});

describe("readSse", () => {
  it("handles CRLF framing as sent by sse-starlette", async () => {
    const msgs = await collect(streamOf("event: stage\r\ndata: a\r\n\r\nevent: answer\r\ndata: b\r\n\r\n"));
    expect(msgs).toEqual([
      { event: "stage", data: "a" },
      { event: "answer", data: "b" },
    ]);
  });

  it("reassembles events split across chunks", async () => {
    const msgs = await collect(streamOf("event: sta", 'ge\ndata: {"x"', ":1}\n", "\n"));
    expect(msgs).toEqual([{ event: "stage", data: '{"x":1}' }]);
  });

  it("keeps multi-byte characters split across chunks intact", async () => {
    const bytes = new TextEncoder().encode("event: answer\ndata: Ø125 ±0.1\n\n");
    const cut = bytes.indexOf(0xc3) + 1; // split inside the two-byte Ø
    const msgs = await collect(streamOf(bytes.slice(0, cut), bytes.slice(cut)));
    expect(msgs[0].data).toBe("Ø125 ±0.1");
  });
});
