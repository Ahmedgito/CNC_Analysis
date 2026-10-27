"use client";

import { AlertTriangle, Box, Grid2x2, Layers, Rotate3d, Scissors, Sparkles } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { modelMeshUrl } from "@/lib/api/client";
import type { CrossCheck, ModelFeature, ModelSlice, Verdict } from "@/lib/api/schemas";
import { modelFactId } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { useFactSelection } from "@/lib/selection";
import { VerdictPill } from "../cross-checks";
import { ModelProjections } from "./model-projections";
import type { ViewPreset } from "./model-scene";

const ModelScene = dynamic(() => import("./model-scene").then((m) => m.ModelScene), {
  ssr: false,
  loading: () => <SceneLoading />,
});

function SceneLoading() {
  return (
    <div className="grid size-full place-items-center">
      <span className="inline-flex items-center gap-2 text-xs text-zinc-500">
        <Rotate3d className="size-4 animate-spin [animation-duration:2.5s]" aria-hidden /> Loading the 3D
        view…
      </span>
    </div>
  );
}

const GROUPS: { title: string; kinds: ModelFeature["kind"][] }[] = [
  { title: "Size", kinds: ["envelope", "boss"] },
  { title: "Holes", kinds: ["bore", "hole", "hole_pattern", "counterbore"] },
  { title: "Edges", kinds: ["chamfer", "fillet"] },
  { title: "Body", kinds: ["body"] },
  { title: "File header", kinds: ["header"] },
];

const TOPOLOGY: Record<ModelSlice["topology"], string> = {
  solid: "one closed solid",
  multi_solid: "several solids",
  open_shell: "open surfaces (not a closed solid)",
  wireframe: "curves only",
  empty: "no geometry",
};

type FeatureCheck = { verdict: Verdict; modelDiffers: boolean };

/** The field verdict for each model fact, and whether the model is the file that differs. */
function verdictByFact(checks: CrossCheck[]): Map<string, FeatureCheck> {
  const out = new Map<string, FeatureCheck>();
  for (const c of checks)
    for (const id of c.iges)
      out.set(id, { verdict: c.verdict, modelDiffers: c.odd_one_out === "iges" || c.dissent.includes(id) });
  return out;
}

export function ModelPanel({
  partNumber,
  model,
  checks,
  onSelect,
}: {
  partNumber: string;
  model: ModelSlice;
  checks: CrossCheck[];
  onSelect?: (factId: string) => void;
}) {
  const { primary, related } = useFactSelection();
  const prefix = `${model.file_stem}!m!`;
  const primaryFeature = primary?.startsWith(prefix) ? primary.slice(prefix.length) : null;
  const relatedFeatures = useMemo(
    () => [...related].filter((id) => id.startsWith(prefix)).map((id) => id.slice(prefix.length)),
    [related, prefix],
  );
  const [hovered, setHovered] = useState<string | null>(null);
  const [section, setSection] = useState(false);
  const [edges, setEdges] = useState(true);
  const [fine, setFine] = useState(false);
  const [preset, setPreset] = useState<ViewPreset>("iso");
  const [nonce, setNonce] = useState(0);
  const [noWebgl, setNoWebgl] = useState<string | null>(null);
  const [triangles, setTriangles] = useState<number | null>(null);
  const verdicts = useMemo(() => verdictByFact(checks), [checks]);
  const select = (featureId: string) => onSelect?.(modelFactId(model, featureId));
  const canRender = Boolean(model.mesh?.lods.length) && !noWebgl;
  const lod: 0 | 1 = fine && model.mesh?.lods.includes(0) ? 0 : 1;

  const applyPreset = (p: ViewPreset) => {
    setPreset(p);
    setNonce((n) => n + 1);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
        <span className="inline-flex items-center gap-1 font-medium text-zinc-700 dark:text-zinc-300">
          <Box className="size-3.5 text-indigo-500" aria-hidden /> {TOPOLOGY[model.topology]}
          {model.valid ? <span className="text-emerald-600 dark:text-emerald-400">· valid</span> : null}
        </span>
        <span>{model.form === "unknown" ? "form not determined" : `${model.form} part`}</span>
        <span>
          units {model.header.units ?? "?"}
          {model.header.units_declared ? "" : " (not declared)"}
          {model.header.units && model.header.units !== "mm" ? ", shown in mm" : ""}
        </span>
        {model.revision ? <span>Rev {model.revision}</span> : null}
        {model.part_number_source ? (
          <span>linked by {model.part_number_source.replace("_", " ")}</span>
        ) : null}
        {triangles ? <span className="font-mono">{triangles.toLocaleString()} triangles</span> : null}
      </div>

      {canRender ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-1" role="group" aria-label="View">
              {(["iso", "front", "top", "right"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={preset === p}
                  onClick={() => applyPreset(p)}
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs capitalize transition-colors",
                    preset === p
                      ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                      : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-white/5",
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              {(
                [
                  ["Section", Scissors, section, setSection, "Cut the model in half to see bores"],
                  ["Edges", Grid2x2, edges, setEdges, "Show sharp edges"],
                  ["Fine", Sparkles, fine, setFine, "Load the detailed mesh"],
                ] as const
              ).map(([label, Icon, on, set, hint]) => (
                <button
                  key={label}
                  type="button"
                  aria-pressed={on}
                  title={hint}
                  onClick={() => set(!on)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs transition-colors",
                    on
                      ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-400/10 dark:text-indigo-300 dark:ring-indigo-400/25"
                      : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-white/5",
                  )}
                >
                  <Icon className="size-3.5" aria-hidden /> {label}
                </button>
              ))}
            </div>
          </div>
          <div
            className="relative aspect-[4/3] overflow-hidden rounded-xl border border-zinc-200 bg-gradient-to-b from-zinc-50 to-zinc-100 dark:border-white/10 dark:from-zinc-900 dark:to-zinc-950"
            role="img"
            aria-label={`3D view of ${model.file}. Drag to rotate, scroll to zoom, click a surface to select its feature.`}
          >
            <ModelScene
              key={lod}
              url={modelMeshUrl(partNumber, model.file, lod, model.extractor_version)}
              features={model.features}
              primary={primaryFeature}
              related={relatedFeatures}
              hovered={hovered}
              section={section}
              edges={edges}
              preset={preset}
              presetNonce={nonce}
              onPick={select}
              onHover={setHovered}
              onUnsupported={setNoWebgl}
              onLoaded={setTriangles}
            />
            {hovered ? (
              <span className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-white/90 px-2 py-1 text-xs shadow-sm dark:bg-zinc-900/90">
                {model.features.find((f) => f.feature_id === hovered)?.label}:{" "}
                <span className="font-medium">
                  {model.features.find((f) => f.feature_id === hovered)?.value}
                </span>
              </span>
            ) : null}
            <span className="pointer-events-none absolute right-2 bottom-2 text-[10px] text-zinc-400">
              drag to rotate · scroll to zoom · click a surface
            </span>
          </div>
        </div>
      ) : null}

      {noWebgl ? (
        <p className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-amber-200">
          <AlertTriangle className="size-4 shrink-0" aria-hidden />
          The 3D view is unavailable ({noWebgl}); the projections below show the same model.
        </p>
      ) : null}

      <ModelProjections
        partNumber={partNumber}
        file={model.file}
        views={model.views}
        version={model.extractor_version}
        primary={primary}
        related={related}
        onSelect={(id) => onSelect?.(id)}
        onPreset={canRender ? applyPreset : undefined}
        large={!canRender}
      />

      {GROUPS.map(({ title, kinds }) => {
        const feats = model.features.filter((f) => kinds.includes(f.kind) && f.feature_id !== "holes");
        if (!feats.length) return null;
        return (
          <section key={title} aria-label={title} className="flex flex-col gap-1">
            <h3 className="text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
              {title} <span className="font-mono tracking-normal text-zinc-400">· {feats.length}</span>
            </h3>
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-white/5">
              {feats.map((f) => {
                const id = modelFactId(model, f.feature_id);
                const check = verdicts.get(id);
                const isPrimary = id === primary;
                const isRelated = !isPrimary && related.has(id);
                return (
                  <li key={f.feature_id}>
                    <button
                      type="button"
                      data-cell-id={id}
                      onClick={() => select(f.feature_id)}
                      onMouseEnter={() => setHovered(f.feature_id)}
                      onMouseLeave={() => setHovered(null)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-md px-1 py-1.5 text-left transition-colors",
                        isPrimary
                          ? "bg-amber-50 dark:bg-amber-400/10"
                          : isRelated
                            ? "bg-amber-50/40 ring-1 ring-amber-300/60 ring-inset dark:bg-amber-400/5"
                            : "hover:bg-zinc-50 dark:hover:bg-white/[0.03]",
                        f.stale && "text-zinc-500",
                      )}
                    >
                      <span className="w-2/5 shrink-0">
                        <span className="block font-medium text-zinc-800 dark:text-zinc-200">{f.label}</span>
                        <span className="block text-xs text-zinc-400">
                          {(f.canonical ?? f.kind).replaceAll("_", " ")}
                        </span>
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className={cn("break-words", f.stale && "line-through decoration-zinc-400")}>
                          {f.value}
                        </span>
                        {f.method ? (
                          <span className="line-clamp-2 text-[11px] text-zinc-500" title={f.method}>
                            {f.method}
                          </span>
                        ) : null}
                        <span className="flex flex-wrap gap-1">
                          <span
                            className={cn(
                              "rounded px-1 text-[10px]",
                              f.confidence === "inferred"
                                ? "border border-dashed border-zinc-300 text-zinc-500 dark:border-white/15"
                                : f.confidence === "exact"
                                  ? "bg-zinc-100 text-zinc-600 dark:bg-white/5 dark:text-zinc-400"
                                  : "bg-indigo-50 text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-300",
                            )}
                            title={
                              f.confidence === "measured"
                                ? "Measured by the app from the model's geometry"
                                : f.confidence === "inferred"
                                  ? "Recognised within a small tolerance, or from surfaces that do not close"
                                  : "Written in the file's header"
                            }
                          >
                            {f.confidence === "exact" ? "from header" : f.confidence}
                          </span>
                          {check && check.verdict === "disagree" && !check.modelDiffers ? (
                            <span
                              className="rounded px-1 text-[10px] text-amber-800 ring-1 ring-amber-300 dark:text-amber-200 dark:ring-amber-400/30"
                              title="The model agrees with at least one other file; another file differs"
                            >
                              another file differs
                            </span>
                          ) : check ? (
                            <VerdictPill verdict={check.verdict} small />
                          ) : null}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {model.warnings.length ? (
        <ul className="flex flex-col gap-1">
          {model.warnings.map((w) => (
            <li key={w} className="flex gap-1.5 text-xs text-amber-800 dark:text-amber-300">
              <Layers className="size-3.5 shrink-0" aria-hidden /> {w}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
