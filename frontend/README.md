# Frontend

Next.js 16 (App Router) with Tailwind CSS v4, TanStack Query and Zod. All styling uses Tailwind
utility classes; `src/app/globals.css` holds only the Tailwind import and theme tokens.

```bash
pnpm install
pnpm dev          # http://localhost:3000, proxies /api/backend/* to BACKEND_URL (default http://127.0.0.1:8000)
pnpm test         # Vitest + Testing Library
pnpm lint && pnpm format:check && pnpm typecheck && pnpm build
```

Key files:

- `src/app/api/backend/[...path]/route.ts`: same-origin streaming proxy to FastAPI
- `src/lib/api/`: typed client and Zod schemas mirroring the backend contract
- `src/lib/sse.ts`: Server-Sent Events reader for the ask stream
- `src/components/`: part picker, record viewer, chat panel, answer card with source chips

See the root [README](../README.md) for the full system.
