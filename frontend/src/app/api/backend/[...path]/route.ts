import type { NextRequest } from "next/server";

/**
 * Same-origin proxy to the FastAPI backend. Streams request and response bodies through
 * untouched, so SSE is not buffered (Next rewrites buffer text/event-stream) and the browser
 * never needs CORS.
 */
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const FORWARD_REQUEST = ["content-type", "accept", "x-request-id"];
const FORWARD_RESPONSE = [
  "content-type",
  "x-request-id",
  "cache-control",
  "etag",
  "content-security-policy",
  "x-content-type-options",
];

async function forward(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  const target = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, BACKEND_URL);
  target.search = req.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // Required by undici when streaming a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      signal: req.signal,
      cache: "no-store",
    } as RequestInit);
  } catch {
    return Response.json(
      {
        title: "Backend unavailable",
        status: 502,
        detail: `Could not reach the API at ${BACKEND_URL}. Is it running?`,
      },
      { status: 502, headers: { "content-type": "application/problem+json" } },
    );
  }

  const out = new Headers();
  for (const name of FORWARD_RESPONSE) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  if (out.get("content-type")?.includes("text/event-stream")) {
    out.set("cache-control", "no-cache, no-transform");
    out.set("x-accel-buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST };
