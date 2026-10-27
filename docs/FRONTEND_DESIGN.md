# Frontend design: what an enterprise-grade UI means for the CNC Part Analyzer

This document records what the frontend must be good at, why, and how the animated redesign
delivers it. It is the spec the `frontend/` code follows.

## 1. Who uses it and what they need

| User | Moment | What the UI must do |
|---|---|---|
| Manufacturing / CNC engineer | Quoting, planning or setting up a job | Find a part in seconds, get a short answer, and see exactly which cell it came from |
| Quality engineer | Checking a record before release | See every value the answer used, spot conflicts and warnings, trust that nothing was invented |
| Hackathon judge | Five-minute evaluation | Understand within one screen that answers are evidence-based, honest about gaps, and built to grow to PDF and IGES |

The product promise is **trust**. Every visual decision either builds trust or gets out of the way.

## 2. Principles

1. **Provenance is the hero.** An answer is never shown without its source chips. Clicking a chip
   jumps to and highlights the cell in the record. The verification result (citations checked,
   rejected, auto-linked) sits in the answer footer.
2. **Honesty is visible, not buried.** Each answer status ("Answered from the files", "Computed
   from the files", "Not in the files", "Needs clarification", "Request blocked") has its own
   colour, icon and label, so colour is never the only signal. General knowledge appears in a
   separate dashed block labelled "not from the files".
3. **Motion explains state; it never decorates over content.** Animation shows the answer
   pipeline progressing, a cell being located, a new answer arriving. Ambient effects (grid
   beams, spotlights) live behind content, pause when off screen, and switch off under
   `prefers-reduced-motion`.
4. **Show the roadmap in the data model.** Excel, PDF and IGES source pills appear on every part,
   with PDF and IGES marked "not available". Judges see the 25% "sources combined" path without
   reading docs, and the UI does not change when Level 2 and 3 land.
5. **Fast on a factory-floor laptop.** Server-rendered shell, client data via TanStack Query with
   caching, motion on `transform` and `opacity` only, a canvas effect that stops when hidden, and
   no layout shift from loading states.

## 3. Information architecture

```
/                      Home: hero search, live stats, part catalogue, how answers are made, trust guarantees
/parts/[partNumber]    Workspace: record viewer | ask panel (tabs on mobile), source pills, related parts
⌘K / Ctrl+K            Command palette on every page: jump to any part by number or description
```

Planned (not built yet, so not linked): an ingest page that uploads files and shows the ingest
report, and an admin page over the existing `/admin/llm-calls` endpoint.

## 4. States every screen handles

| State | Treatment |
|---|---|
| Loading | Skeletons with the final layout's shape; no spinners for page loads |
| Empty | Explains the next action (for example how to ingest files) |
| Part not found | "Did you mean" suggestions from the backend |
| Backend down | Status pill in the navbar turns red; the proxy returns a readable 502 |
| Answer in progress | Live pipeline stepper driven by server-sent stage events; Stop button |
| Fallback provider | Amber "fallback provider" tag in the answer footer, with the reason on hover |
| Offline rules engine | Navbar status pill says the app is answering with offline rules, not an LLM |

## 5. Accessibility (WCAG 2.2 AA target)

- Full keyboard path: search, command palette (arrow keys, Enter, Escape), sheet tabs (arrow
  keys), source chips, ask box (Enter sends, Shift+Enter adds a line).
- Visible focus rings on every interactive element.
- Answers are announced through an `aria-live="polite"` region; errors use `role="alert"`.
- `prefers-reduced-motion` turns off ambient motion app-wide by default. A Motion control in
  the navbar cycles System (follow the OS), Full and Reduced, stored per browser. Every animated
  component reads the same setting through `MotionConfig` and `useReducedMotionConfig`, including
  the canvas background, which also stops drawing while off screen.
- Contrast is checked for both themes; status is always icon plus text plus colour.

## 6. Theming and tokens

- Light and dark themes, defaulting to the system setting, with a toggle in the navbar
  (`next-themes`, class strategy, no flash on load).
- Tailwind utility classes only. `globals.css` contains just the Tailwind import, the dark
  variant and font tokens.
- Palette: graphite neutrals (zinc), a cyan "coolant" accent for interactive and live states,
  amber for "located cell" highlights, and semantic colours for answer statuses.
- Typography: Geist for text, Geist Mono for part numbers, cell coordinates and computations,
  which reads as engineering data.

## 7. Engineering quality bar

- Typed API layer: Zod schemas mirror the backend contract and fail loudly on drift.
- Server-sent events parsed by a tested, chunk-safe reader; `AbortController` for Stop.
- No raw HTML rendering: markdown goes through `react-markdown` without HTML support, and links
  in answers are rendered as text.
- Unit tests (Vitest and Testing Library) cover the answer card contract and the SSE parser;
  lint, type check and production build gate every change.

## 8. Component map (21st.dev catalogue)

The redesign uses the 21st.dev catalogue as its component vocabulary. Two components were
retrieved as source code (the free tier allows two retrievals a day); the rest were written in
this repo in the same style, with `motion` and Tailwind, because their code is behind the paid
registry.

| Where | Component | 21st.dev reference | Source |
|---|---|---|---|
| Hero background | Grid Beam: light travelling along blueprint grid lines | `cult-ui/grid-beam` | Retrieved, adapted (theme-aware, pauses off screen and for reduced motion) |
| Ask box | AI Chat Input: spring-expanding input, blur-in rotating placeholders | `preetsuthar17/ai-chat-input` | Retrieved, adapted (real submit and stop, no dead buttons, textarea) |
| Navbar | Floating glass navbar that tightens on scroll | `preetsuthar17/navbar-1`, `abushaidislam7/morphing-island-navbar` | Written here |
| Part cards, bento tiles | Spotlight card: pointer-following glow | `ibelick/spotlight`, `manuarora700/card-spotlight` | Written here |
| Part cards | 3D tilt on hover | tilt card family | Written here |
| Search box, live answer | Border beam: light running around the edge | `kevingirelli/animated-border` | Written here |
| Pipeline progress | AI processing states stepper with shimmer text | `arunjdass/ai-agent-processing-states`, `serafimcloud/text-shimmer` | Written here |
| Hero stats | Number ticker | `danielpetho/basic-number-ticker` | Written here |
| Sheet tabs, mobile view switch | Animated tabs with sliding indicator | `educalvolpz/animated-tabs` | Written here |
| Hero headline | Blur-in word reveal | text generate effect family | Written here |
| Example questions strip | Marquee | marquee family | Written here |
| Trust section | Bento grid with live mini-demos | `kokonutd/bento-grid` | Written here |
| Global navigation | Command palette (⌘K) | command menu family | Written here |
| Source chips | Hover preview card | animated tooltip family | Written here |
| Theme | Animated sun/moon/system toggle | theme toggle family | Written here |
| Motion setting | Animated System / Full / Reduced toggle | (no catalogue match) | Written here |
