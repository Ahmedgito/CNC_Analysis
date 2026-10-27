"use client";

/**
 * The model's hidden-line projections (front, top, right) as inline SVG, so strokes follow the
 * theme (currentColor) and features are clickable. The SVG comes from our backend, but it is
 * still re-parsed against an allowlist of elements and attributes before it touches the DOM.
 */

import { useQuery } from "@tanstack/react-query";
import { modelViewUrl } from "@/lib/api/client";
import { cn } from "@/lib/cn";

const ALLOWED_TAGS = new Set(["svg", "g", "path", "circle", "polygon", "title"]);
const ALLOWED_ATTRS = new Set([
  "xmlns",
  "viewBox",
  "class",
  "d",
  "cx",
  "cy",
  "r",
  "points",
  "fill",
  "stroke",
  "stroke-width",
  "stroke-dasharray",
  "stroke-linecap",
  "stroke-linejoin",
  "opacity",
  "data-fact-id",
  "data-view",
  "data-units",
]);

export function sanitizeSvg(text: string): string | null {
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const root = doc.documentElement;
  if (root.nodeName !== "svg" || doc.querySelector("parsererror")) return null;
  const walk = (el: Element) => {
    for (const child of [...el.children]) {
      if (!ALLOWED_TAGS.has(child.nodeName)) {
        child.remove();
        continue;
      }
      walk(child);
    }
    for (const attr of [...el.attributes]) {
      if (!ALLOWED_ATTRS.has(attr.name)) el.removeAttribute(attr.name);
    }
  };
  walk(root);
  root.setAttribute("class", "size-full");
  root.setAttribute("preserveAspectRatio", "xMidYMid meet");
  return new XMLSerializer().serializeToString(root);
}

function Projection({
  partNumber,
  file,
  view,
  version,
  primary,
  related,
  onSelect,
  large,
  onActivate,
}: {
  partNumber: string;
  file: string;
  view: string;
  version: number;
  primary: string | null;
  related: ReadonlySet<string>;
  onSelect: (factId: string) => void;
  large?: boolean;
  onActivate?: () => void;
}) {
  const url = modelViewUrl(partNumber, file, view, version);
  const { data, isError } = useQuery({
    queryKey: ["model-view", url],
    queryFn: async () => {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return sanitizeSvg(await resp.text());
    },
    staleTime: Infinity,
  });
  // The markup stays static; highlights are applied to the nodes after render (see ref).
  const markup = data ?? null;

  return (
    <figure
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white text-zinc-800 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-200",
        large ? "h-full" : "h-28",
      )}
    >
      <figcaption className="absolute top-1 left-2 z-1 text-[10px] tracking-[0.15em] text-zinc-400 uppercase">
        {view}
      </figcaption>
      {onActivate ? (
        <button
          type="button"
          onClick={onActivate}
          className="absolute top-1 right-1 z-1 rounded px-1.5 text-[10px] text-zinc-500 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-zinc-100 focus-visible:opacity-100 dark:hover:bg-white/10"
        >
          3D {view}
        </button>
      ) : null}
      {markup ? (
        <div
          className={cn(
            "min-h-0 flex-1 p-2",
            "[&_.features>*]:cursor-pointer [&_.features>*:hover]:stroke-cyan-500/70",
          )}
          onClick={(e) => {
            const id = (e.target as Element).closest("[data-fact-id]")?.getAttribute("data-fact-id");
            if (id) onSelect(id);
          }}
          ref={(el) => {
            if (!el) return;
            el.querySelectorAll<SVGElement>("[data-fact-id]").forEach((m) => {
              const id = m.getAttribute("data-fact-id") ?? "";
              m.style.stroke =
                id === primary ? "rgb(245 158 11)" : related.has(id) ? "rgb(252 211 77 / 0.8)" : "";
              m.style.fill = id === primary ? "rgb(251 191 36 / 0.25)" : "";
            });
          }}
          // Sanitised above: only svg, g, path, circle, polygon and title, no scripts or links.
          dangerouslySetInnerHTML={{ __html: markup }}
        />
      ) : (
        <div className="grid flex-1 place-items-center text-xs text-zinc-400">
          {isError ? "projection unavailable" : "drawing…"}
        </div>
      )}
    </figure>
  );
}

export function ModelProjections({
  partNumber,
  file,
  views,
  version = 1,
  primary,
  related,
  onSelect,
  onPreset,
  large = false,
}: {
  partNumber: string;
  file: string;
  views: string[];
  version?: number;
  primary: string | null;
  related: ReadonlySet<string>;
  onSelect: (factId: string) => void;
  onPreset?: (view: "front" | "top" | "right") => void;
  /** The projections are the main view (no WebGL). */
  large?: boolean;
}) {
  const order = ["front", "top", "right"].filter((v) => views.includes(v));
  if (!order.length) return null;
  return (
    <div className={cn("grid gap-2", large ? "grid-cols-1 sm:grid-cols-3 sm:[&>*]:h-56" : "grid-cols-3")}>
      {order.map((v) => (
        <Projection
          key={v}
          partNumber={partNumber}
          file={file}
          view={v}
          version={version}
          primary={primary}
          related={related}
          onSelect={onSelect}
          large={large}
          onActivate={onPreset ? () => onPreset(v as "front" | "top" | "right") : undefined}
        />
      ))}
    </div>
  );
}
