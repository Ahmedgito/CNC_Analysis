"use client";

/**
 * Grid Beam: soft light travelling along grid dividers.
 * Source: 21st.dev, cult-ui/grid-beam (https://21st.dev/@cult-ui/components/grid-beam).
 * Adapted for this app: a "coolant" palette, the canvas loop stops while the element is off
 * screen, and reduced-motion users get the static grid only.
 */

import { useReducedMotionConfig } from "motion/react";
import {
  type ComponentProps,
  type CSSProperties,
  forwardRef,
  type RefObject,
  useEffect,
  useMemo,
  useRef,
} from "react";
import { cn } from "@/lib/cn";

type RGB = readonly [number, number, number];
type PaletteBand = Readonly<{ color: RGB; op: number }>;
export type GridBeamPalette = Readonly<{ h: readonly PaletteBand[]; v: readonly PaletteBand[] }>;

const PALETTES = {
  coolant: {
    dark: {
      h: [
        { color: [34, 211, 238], op: 0.42 },
        { color: [45, 212, 191], op: 0.36 },
        { color: [56, 189, 248], op: 0.4 },
        { color: [251, 191, 36], op: 0.3 },
        { color: [34, 211, 238], op: 0.36 },
        { color: [129, 140, 248], op: 0.32 },
      ],
      v: [
        { color: [56, 189, 248], op: 0.4 },
        { color: [34, 211, 238], op: 0.36 },
        { color: [45, 212, 191], op: 0.4 },
        { color: [129, 140, 248], op: 0.32 },
        { color: [34, 211, 238], op: 0.38 },
        { color: [251, 191, 36], op: 0.28 },
      ],
    },
    light: {
      h: [
        { color: [8, 145, 178], op: 0.32 },
        { color: [13, 148, 136], op: 0.26 },
        { color: [2, 132, 199], op: 0.3 },
        { color: [217, 119, 6], op: 0.24 },
        { color: [8, 145, 178], op: 0.28 },
        { color: [79, 70, 229], op: 0.22 },
      ],
      v: [
        { color: [2, 132, 199], op: 0.3 },
        { color: [8, 145, 178], op: 0.28 },
        { color: [13, 148, 136], op: 0.3 },
        { color: [79, 70, 229], op: 0.22 },
        { color: [8, 145, 178], op: 0.28 },
        { color: [217, 119, 6], op: 0.22 },
      ],
    },
  },
  mono: {
    dark: {
      h: [
        { color: [200, 200, 200], op: 0.16 },
        { color: [180, 180, 180], op: 0.13 },
      ],
      v: [
        { color: [185, 185, 185], op: 0.16 },
        { color: [170, 170, 170], op: 0.13 },
      ],
    },
    light: {
      h: [
        { color: [90, 90, 90], op: 0.13 },
        { color: [110, 110, 110], op: 0.1 },
      ],
      v: [
        { color: [100, 100, 100], op: 0.13 },
        { color: [80, 80, 80], op: 0.1 },
      ],
    },
  },
} as const satisfies Record<string, Record<"dark" | "light", GridBeamPalette>>;

export type GridBeamPaletteKey = keyof typeof PALETTES;

type RuntimeConfig = {
  rows: number;
  cols: number;
  palette: GridBeamPalette;
  active: boolean;
  duration: number;
  strength: number;
  breathe: boolean;
};

const smoothstep = (t: number) => t * t * (3 - 2 * t);
const gaussian = (x: number, s: number) => Math.exp(-(x * x) / (2 * s * s));
const rgba = (r: number, g: number, b: number, a: number) =>
  `rgba(${r},${g},${b},${Math.max(0, a).toFixed(4)})`;
const lift = (c: number, by: number) => Math.min(255, c + by);

function strokeBeam(
  ctx: CanvasRenderingContext2D,
  from: [number, number],
  to: [number, number],
  [cr, cg, cb]: RGB,
  alpha: number,
) {
  const grad = ctx.createLinearGradient(from[0], from[1], to[0], to[1]);
  grad.addColorStop(0, "transparent");
  grad.addColorStop(0.12, rgba(cr, cg, cb, alpha * 0.4));
  grad.addColorStop(0.35, rgba(lift(cr, 60), lift(cg, 60), lift(cb, 60), alpha * 0.8));
  grad.addColorStop(0.5, rgba(lift(cr, 100), lift(cg, 100), lift(cb, 100), alpha));
  grad.addColorStop(0.65, rgba(lift(cr, 60), lift(cg, 60), lift(cb, 60), alpha * 0.8));
  grad.addColorStop(0.88, rgba(cr, cg, cb, alpha * 0.4));
  grad.addColorStop(1, "transparent");
  ctx.strokeStyle = grad;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(from[0], from[1]);
  ctx.lineTo(to[0], to[1]);
  ctx.stroke();
}

function useBeamCanvas(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  config: RefObject<RuntimeConfig>,
  restartRef: RefObject<(() => void) | null>,
) {
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d", { alpha: true });
    if (!canvas || !ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    ro?.observe(canvas);

    const start = performance.now();
    let frame: number | null = null;
    let visible = true;
    let fade = 0; // 0..1, eased toward 1 while active and toward 0 when switched off
    let last = start;

    const draw = (now: number) => {
      frame = null;
      const { rows, cols, palette, active, duration, strength, breathe } = config.current;
      const { width: w, height: h } = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, w, h);
      if (!visible) return; // resumed by the IntersectionObserver

      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      fade = active ? Math.min(1, fade + dt / 0.8) : Math.max(0, fade - dt / 0.6);
      if (fade === 0 && !active) return; // fully off: stop until restarted

      const elapsed = (now - start) / 1000;
      const cellW = w / cols;
      const cellH = h / rows;
      const gs = smoothstep(fade) * strength;
      const br = breathe ? 0.85 + 0.3 * Math.sin(elapsed * 1.4) + 0.1 * Math.sin(elapsed * 2.3) : 1;
      const hPos = (r: number) =>
        (((elapsed * (1 + (r % 3) * 0.12)) / duration + r * 0.21 + (r % 2) * 0.35) % 1) * w;
      const vPos = (c: number) =>
        (((elapsed * (1 + (c % 3) * 0.1)) / (duration * 1.2) + c * 0.26 + (c % 2) * 0.4) % 1) * h;

      for (let r = 1; r < rows; r++) {
        const y = r * cellH;
        const band = palette.h[r % palette.h.length];
        const x = hPos(r);
        const len = cellW * 0.55 * br;
        strokeBeam(ctx, [x - len, y], [x + len, y], band.color, band.op * gs);
      }
      for (let c = 1; c < cols; c++) {
        const x = c * cellW;
        const band = palette.v[c % palette.v.length];
        const y = vPos(c);
        const len = cellH * 0.55 * br;
        strokeBeam(ctx, [x, y - len], [x, y + len], band.color, band.op * gs);
      }
      // Flare where a horizontal and a vertical beam cross at a grid node.
      for (let r = 1; r < rows; r++) {
        for (let c = 1; c < cols; c++) {
          const ix = c * cellW;
          const iy = r * cellH;
          const prox = gaussian((hPos(r) - ix) / cellW, 0.25) * gaussian((vPos(c) - iy) / cellH, 0.25);
          if (prox <= 0.05) continue;
          const a = palette.h[r % palette.h.length].color;
          const b = palette.v[c % palette.v.length].color;
          const [mr, mg, mb] = [0, 1, 2].map((i) => Math.floor((a[i] + b[i]) / 2));
          const radius = 3.5 * Math.sqrt(prox);
          const op = prox * 0.6 * gs;
          const glow = ctx.createRadialGradient(ix, iy, 0, ix, iy, radius);
          glow.addColorStop(0, rgba(lift(mr, 140), lift(mg, 140), lift(mb, 140), op));
          glow.addColorStop(0.5, rgba(mr, mg, mb, op * 0.4));
          glow.addColorStop(1, "transparent");
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(ix, iy, radius, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      frame = requestAnimationFrame(draw);
    };

    const startLoop = () => {
      if (frame !== null) return;
      last = performance.now();
      frame = requestAnimationFrame(draw);
    };
    restartRef.current = startLoop;
    const io =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([entry]) => {
            visible = entry.isIntersecting;
            if (visible) startLoop();
          });
    io?.observe(canvas);
    startLoop();

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      restartRef.current = null;
      ro?.disconnect();
      io?.disconnect();
    };
  }, [canvasRef, config, restartRef]);
}

export type UseGridBeamOptions = {
  rows?: number;
  cols?: number;
  colorVariant?: GridBeamPaletteKey;
  theme?: "dark" | "light";
  active?: boolean;
  duration?: number;
  strength?: number;
  breathe?: boolean;
};

export function useGridBeam({
  rows: rowsProp = 3,
  cols: colsProp = 4,
  colorVariant = "coolant",
  theme = "dark",
  active: activeProp = true,
  duration = 3,
  strength = 1,
  breathe = true,
}: UseGridBeamOptions) {
  const reduceMotion = useReducedMotionConfig();
  const active = activeProp && !reduceMotion;
  const rows = Math.max(2, rowsProp);
  const cols = Math.max(2, colsProp);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const restartRef = useRef<(() => void) | null>(null);
  const palette = useMemo(() => PALETTES[colorVariant][theme], [colorVariant, theme]);
  const configRef = useRef<RuntimeConfig>({ rows, cols, palette, active, duration, strength, breathe });

  useEffect(() => {
    configRef.current = { rows, cols, palette, active, duration, strength, breathe };
    if (active) restartRef.current?.();
  }, [rows, cols, palette, active, duration, strength, breathe]);

  useBeamCanvas(canvasRef, configRef, restartRef);
  return { canvasRef, rows, cols };
}

export function GridBeamDividers({
  rows,
  cols,
  className,
  ...props
}: ComponentProps<"svg"> & { rows: number; cols: number }) {
  return (
    <svg
      aria-hidden
      className={cn("pointer-events-none absolute inset-0 z-1 h-full w-full", className)}
      preserveAspectRatio="none"
      role="presentation"
      {...props}
    >
      {Array.from({ length: rows - 1 }, (_, r) => {
        const y = `${((r + 1) / rows) * 100}%`;
        return <line key={`h${y}`} stroke="currentColor" strokeWidth={1} x1="0" x2="100%" y1={y} y2={y} />;
      })}
      {Array.from({ length: cols - 1 }, (_, c) => {
        const x = `${((c + 1) / cols) * 100}%`;
        return <line key={`v${x}`} stroke="currentColor" strokeWidth={1} x1={x} x2={x} y1="0" y2="100%" />;
      })}
    </svg>
  );
}

export const GridBeamCanvas = forwardRef<
  HTMLCanvasElement,
  ComponentProps<"canvas"> & { borderRadius?: number }
>(function GridBeamCanvas({ className, style, borderRadius, ...props }, ref) {
  return (
    <canvas
      aria-hidden
      ref={ref}
      className={cn("pointer-events-none absolute inset-0 z-2 h-full w-full", className)}
      style={{ borderRadius, ...style } as CSSProperties}
      {...props}
    />
  );
});

export type GridBeamProps = UseGridBeamOptions &
  ComponentProps<"div"> & {
    /** Classes for the divider lines; their colour is `currentColor`. */
    dividerClassName?: string;
    borderRadius?: number;
  };

export function GridBeam({
  children,
  className,
  dividerClassName,
  borderRadius,
  rows,
  cols,
  colorVariant,
  theme,
  active,
  duration,
  strength,
  breathe,
  ...props
}: GridBeamProps) {
  const {
    canvasRef,
    rows: r,
    cols: c,
  } = useGridBeam({
    rows,
    cols,
    colorVariant,
    theme,
    active,
    duration,
    strength,
    breathe,
  });
  return (
    <div
      className={cn("relative overflow-hidden", className)}
      data-slot="grid-beam"
      style={{ borderRadius }}
      {...props}
    >
      <GridBeamDividers rows={r} cols={c} className={dividerClassName} />
      <GridBeamCanvas ref={canvasRef} borderRadius={borderRadius} />
      <div className="relative z-3">{children}</div>
    </div>
  );
}
