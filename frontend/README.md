# DHRUVA Frontend

React 18 + Vite + TypeScript SPA — dark-first, shadcn/ui + Tailwind, gRPC-Web.

## Quick start

```bash
cd frontend
cp .env.example .env
npm install
npm run dev                 # http://localhost:5173
```

Requires backend (`uvicorn` on :8000) and Envoy (:8080) to be running; see `../deploy/compose/docker-compose.dev.yml`.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |
| `npm run test` | Vitest unit tests |
| `npm run e2e` | Playwright end-to-end tests |
| `npm run proto:generate` | Regenerate gRPC-Web clients from `../proto/` |

## Structure

```
src/
├── api/
│   ├── grpc/          (transport + generated clients)
│   ├── rest/          (axios + endpoints)
│   └── websocket/     (multiplexed WS hub)
├── components/
│   ├── ui/            (shadcn copies)
│   ├── charts/        (EquityCurve, Candle, Donut, Sparkline)
│   ├── layout/        (Shell, Sidebar, Topbar)
│   └── common/        (Logo, ThemeToggle, Loader, EmptyState)
├── features/
│   ├── auth/          (login, register, refresh, AuthGuard)
│   ├── dashboard/     (KPIs, overall equity curve)
│   ├── trading/       (order ticket, positions, blotter)
│   ├── portfolio/     (holdings, allocation, per-account)
│   ├── strategies/    (list, create, backtest, ML model picker)
│   ├── scanner/       (pre-market results, setup scoring)
│   └── reports/       (request + list PDFs/Excels)
├── hooks/
├── store/             (zustand slices)
├── theme/
├── routes/            (TanStack Router tree + guards)
├── utils/
└── types/
```

See [../docs/prompts/DHRUVA_Python_React_Master_Prompt.md](../docs/prompts/DHRUVA_Python_React_Master_Prompt.md) §11 for the full frontend spec.
