# DHRUVA Master Implementation Prompt — Python Backend + React Frontend

> **Give this single document to any developer or AI agent to build DHRUVA end-to-end.**
>
> **Stack**: Python 3.12 (FastAPI + gRPC) backend · React 18 + Vite + TypeScript frontend · PostgreSQL/TimescaleDB · Redis · gRPC-Web · Docker
>
> **Latency target**: < 100 ms REST, < 50 ms gRPC order placement (30 ms+ is acceptable — correctness and AI/ML extensibility prioritized over microsecond latency)
>
> **Scope**: MVP1 production-ready algo trading + portfolio management platform for Indian markets (NSE/BSE)

---

## 0. How to Use This Prompt

1. Read this entire document top to bottom once before writing any code.
2. The repository already contains the directory scaffold under `backend/`, `frontend/`, `proto/`, `deploy/`, `scripts/`. Fill it in by section.
3. Each section lists **what to build**, **where it lives**, **key interfaces**, and **acceptance criteria**.
4. Section 14 is the phase-by-phase execution plan (Days 1 → 22).
5. Run `scripts/install.sh` (or `scripts/install.ps1` on Windows) once to install the whole ecosystem, then `scripts/run.sh` to start the stack.

---

## 1. Product Vision

**DHRUVA** (Sanskrit: *Pole Star*) is a production-grade algorithmic trading + portfolio management platform for Indian markets.

**User outcomes**:

- Place orders across 5+ brokers (Zerodha, Upstox, Dhan, Fyers, 5Paisa) from one UI, extensible to 23+.
- Run rule-based **and AI/ML** strategies on 1-minute candles with paper/live toggle.
- Get consolidated portfolio view across accounts with Sharpe, Sortino, Calmar, VaR, drawdown.
- Generate PDF/Excel/CSV reports (strategy, portfolio, risk, tax).
- Receive real-time P&L, order fills, risk alerts via WebSocket.
- Authenticate via JWT (15-min access + 7-day refresh), with broker credentials encrypted at rest.

**Non-goals for MVP1**: options Greeks modeling, HFT-grade sub-millisecond execution, mobile native apps.

---

## 2. Architecture at a Glance

### 2.1 Backend — Python Modular Monolith

A single FastAPI process (port `8000` REST, port `50051` gRPC, port `8001` WebSocket) that hosts all modules via dependency injection. Modules are internally decoupled so any of them can be extracted into its own service later without rewriting callers.

```
┌─────────────────────────────────────────────────────────────┐
│                     DHRUVA Backend (Python 3.12)            │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐     │
│  │  REST API   │  │  gRPC API   │  │  WebSocket Hub   │     │
│  │ (FastAPI)   │  │  (grpcio)   │  │ (FastAPI native) │     │
│  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘     │
│         │                │                  │               │
│  ┌──────┴────────────────┴──────────────────┴─────────┐     │
│  │              Application Services                  │     │
│  │  auth │ execution │ portfolio │ strategy │ scanner │     │
│  │  reports │ notifications │ audit │ data            │     │
│  └──────┬────────────────┬──────────────┬─────────────┘     │
│         │                │              │                   │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌────┴──────────┐        │
│  │  Brokers    │  │ Strategies  │  │ Infrastructure │       │
│  │ (5+ adapters│  │ (templates  │  │ logs/trace/    │       │
│  │  + factory) │  │  + ML)      │  │ cache/metrics) │       │
│  └──────┬──────┘  └──────┬──────┘  └────┬──────────┘        │
│         │                │              │                   │
│  ┌──────┴────────────────┴──────────────┴──────┐            │
│  │   SQLAlchemy 2 async · Alembic · Redis      │            │
│  └──────────┬──────────────────────────┬───────┘            │
└─────────────┼──────────────────────────┼────────────────────┘
              ▼                          ▼
   ┌────────────────────┐      ┌──────────────────┐
   │ PostgreSQL 16 +    │      │   Redis 7        │
   │ TimescaleDB        │      │ (positions/price │
   │ (OHLCV, orders,    │      │  cache, pubsub)  │
   │  audit events)     │      └──────────────────┘
   └────────────────────┘
```

### 2.2 Frontend — React SPA

```
┌────────────────────────────────────────────────────────────┐
│        Browser — React 18 + Vite + TypeScript              │
│                                                            │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐      │
│  │  Routing   │  │  Theme     │  │  Auth guard      │      │
│  │  (TanStack │  │ (shadcn/ui │  │ (JWT + refresh   │      │
│  │   Router)  │  │  + Tailwind│  │  interceptor)    │      │
│  └─────┬──────┘  └─────┬──────┘  └────────┬─────────┘      │
│        │               │                  │                │
│  ┌─────┴───────────────┴──────────────────┴─────────┐      │
│  │  Feature modules                                 │      │
│  │  auth · dashboard · trading · portfolio ·        │      │
│  │  strategies · scanner · reports                  │      │
│  └─────┬────────────────────────────────────────────┘      │
│        │                                                   │
│  ┌─────┴─────────────────┐   ┌─────────────────────┐       │
│  │  gRPC-Web client      │   │  REST/WS clients    │       │
│  │  (@bufbuild/connect)  │   │  (axios + native WS)│       │
│  └───────────┬───────────┘   └──────────┬──────────┘       │
└──────────────┼──────────────────────────┼──────────────────┘
               ▼                          ▼
        Envoy proxy (gRPC-Web ↔ gRPC)   FastAPI REST/WS
```

### 2.3 Data Flow — Order Lifecycle

```
React UI  ─(gRPC-Web)→  Envoy  ─(gRPC)→  DHRUVA OrderService
                                              │
                      ┌───────────────────────┤
                      ▼                       ▼
                Risk Engine          Audit (event store)
                      │                       │
                      ▼                       │
                Broker Adapter ──→ NSE/BSE    │
                      │                       │
                      ▼                       │
                Position Tracker ──→ Redis ◄──┘
                      │
                      ▼
                WebSocket Hub ──push──→ All connected clients
```

### 2.4 Service Interaction Pattern (Python DI)

```python
# Everything wired through a single container (dependency_injector or FastAPI Depends).
# Controllers/servicers receive services; services call other services directly.

@app.post("/api/v1/orders")
async def place_order(
    req: PlaceOrderRequest,
    execution: ExecutionService = Depends(get_execution_service),
    user: User = Depends(get_current_user),
):
    return await execution.place_order(user.id, req)
```

---

## 3. Technology Stack (Pinned to Latest Stable)

### Backend (`backend/requirements.txt`)

| Concern | Library | Version |
|---|---|---|
| Web framework | `fastapi` | `>=0.115,<0.116` |
| ASGI server | `uvicorn[standard]` | `>=0.32,<0.33` |
| Event loop | `uvloop` | `>=0.21` (Linux/Mac only) |
| gRPC | `grpcio`, `grpcio-tools`, `grpcio-reflection` | `>=1.68` |
| Validation | `pydantic` | `>=2.9,<3` |
| Settings | `pydantic-settings` | `>=2.6` |
| ORM (async) | `sqlalchemy[asyncio]` | `>=2.0.36` |
| Postgres driver | `asyncpg` | `>=0.30` |
| Migrations | `alembic` | `>=1.14` |
| Cache | `redis[hiredis]` | `>=5.2` |
| Data / indicators | `polars` `>=1.17`, `numpy` `>=2.1`, `numba` `>=0.60`, `pandas-ta` `>=0.3.14b` |
| Backtest | `vectorbt` | `>=0.26` |
| ML | `scikit-learn` `>=1.6`, `xgboost` `>=2.1`, `lightgbm` `>=4.5`, `torch` `>=2.5` (optional) |
| Structured logs | `structlog` `>=24.4`, `python-json-logger` `>=2.0.7` |
| Tracing | `opentelemetry-api`, `-sdk`, `-instrumentation-fastapi`, `-instrumentation-grpc`, `-instrumentation-sqlalchemy`, `-instrumentation-redis`, `-exporter-otlp-proto-grpc` (all `>=1.28`) |
| Metrics | `prometheus-client` `>=0.21` |
| Auth | `pyjwt[crypto]` `>=2.10`, `passlib[bcrypt]` `>=1.7.4`, `cryptography` `>=43` |
| Reports | `reportlab` `>=4.2`, `openpyxl` `>=3.1.5` |
| Email | `aiosmtplib` `>=3.0` |
| Scheduler | `apscheduler` `>=3.10.4` |
| HTTP client | `httpx` `>=0.28` |
| Testing | `pytest` `>=8.3`, `pytest-asyncio` `>=0.24`, `pytest-cov` `>=6.0`, `httpx` (same) |
| Lint/format | `ruff` `>=0.8`, `mypy` `>=1.13` |

### Frontend (`frontend/package.json` highlights)

| Concern | Library | Version |
|---|---|---|
| Build | `vite` `^6`, `@vitejs/plugin-react` `^4.3` |
| UI | `react` `^18.3`, `react-dom` `^18.3` |
| TypeScript | `typescript` `~5.6` |
| Styling | `tailwindcss` `^3.4`, `postcss`, `autoprefixer` |
| Theme / components | `shadcn/ui` (copy-in) backed by `@radix-ui/*`, `class-variance-authority`, `tailwind-merge`, `lucide-react` |
| Icons | `lucide-react` `^0.460` |
| Routing | `@tanstack/react-router` `^1.82` |
| Data fetching | `@tanstack/react-query` `^5.59` |
| State | `zustand` `^5.0` |
| Charts | `recharts` `^2.13` + `apexcharts` `^4.0` + `react-apexcharts` `^1.7` |
| gRPC-Web | `@bufbuild/connect` `^1.6`, `@bufbuild/connect-web` `^1.6`, `@bufbuild/protobuf` `^1.10` |
| Codegen | `@bufbuild/buf` (CLI) |
| Forms | `react-hook-form` `^7.53` + `zod` `^3.23` |
| WebSocket | native `WebSocket` API + `reconnecting-websocket` `^4.4` |
| Notifications | `sonner` `^1.7` |
| Date | `date-fns` `^4.1` |
| Testing | `vitest` `^2.1`, `@testing-library/react` `^16`, `@playwright/test` `^1.48` |

**Free theme choice**: Use **[shadcn/ui](https://ui.shadcn.com/)** (MIT licensed, copy-in components) with the **"Slate" or "Zinc" base color** and **custom DHRUVA primary** (`#F59E0B` amber — pole-star gold). Dark mode first, with a light toggle. All component source stays inside `frontend/src/components/ui/`.

### Infra

| Service | Image |
|---|---|
| PostgreSQL + TimescaleDB | `timescale/timescaledb:latest-pg16` |
| Redis | `redis:7-alpine` |
| gRPC-Web proxy | `envoyproxy/envoy:v1.32-latest` |
| Tracing | `jaegertracing/all-in-one:latest` |
| Metrics | `prom/prometheus:latest` + `grafana/grafana:latest` |
| Reverse proxy (prod) | `nginx:alpine` |

---

## 4. Repository Layout

This is the canonical layout already scaffolded in the repo. **Do not add files outside this tree.**

```
DHRUVA/
├── README.md
├── LICENSE
├── .gitignore
├── .editorconfig
│
├── docs/
│   ├── README.md
│   ├── architecture/
│   │   ├── DHRUVA_Python_OpenAlgo_Master_Plan.md
│   │   └── DHRUVA_Complete_Plan.md                 (legacy .NET reference)
│   ├── brand/
│   │   └── DHRUVA_Logo_Design_Prompt.md
│   ├── guides/
│   │   └── IMPLEMENTATION_GUIDE.md
│   ├── phase1-reference/
│   │   └── DHRUVA_Phase1_Implementation_Prompt.md  (legacy .NET reference)
│   └── prompts/
│       ├── DHRUVA_Master_Implementation_Prompt.md  (legacy .NET+Python)
│       └── DHRUVA_Python_React_Master_Prompt.md    ← YOU ARE HERE
│
├── assets/
│   └── logo/DHRUVA-Logos/
│
├── proto/                                          (shared .proto contracts — source of truth)
│   └── dhruva/v1/
│       ├── common.proto
│       ├── auth.proto
│       ├── orders.proto
│       ├── portfolio.proto
│       ├── strategies.proto
│       ├── scanner.proto
│       └── reports.proto
│
├── backend/
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── .env.example
│   ├── .dockerignore
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 (FastAPI + gRPC + WS bootstrap)
│   │   ├── config.py               (pydantic-settings)
│   │   ├── container.py            (DI wiring)
│   │   │
│   │   ├── api/
│   │   │   ├── rest/v1/            (auth, orders, portfolio, strategies, scanner, reports, health)
│   │   │   ├── grpc/servicers/     (generated stubs + implementations)
│   │   │   └── websocket/hubs.py   (trading, portfolio, notifications channels)
│   │   │
│   │   ├── core/                   (business services — pure Python, no framework)
│   │   │   ├── auth/               (jwt, password, token_service, user_service)
│   │   │   ├── execution/          (execution_service, risk_engine, position_tracker)
│   │   │   ├── portfolio/          (portfolio_service, analytics, rebalancer)
│   │   │   ├── strategy/           (strategy_service, executor, backtest, paper_trader)
│   │   │   ├── scanner/            (scanner_service, pattern_detector, scoring)
│   │   │   ├── reports/            (pdf, excel, csv report generators)
│   │   │   ├── notifications/      (email, in_app, webhook)
│   │   │   └── audit/              (event_store, domain_events)
│   │   │
│   │   ├── brokers/                (adapters — one file per broker)
│   │   │   ├── base.py             (abstract BrokerAdapter)
│   │   │   ├── factory.py
│   │   │   ├── zerodha.py
│   │   │   ├── upstox.py
│   │   │   ├── dhan.py
│   │   │   ├── fyers.py
│   │   │   ├── five_paisa.py
│   │   │   └── health_monitor.py
│   │   │
│   │   ├── data/                   (market data)
│   │   │   ├── pipeline.py         (ingestion loop)
│   │   │   ├── ohlcv_repository.py (TimescaleDB queries)
│   │   │   └── indicators.py       (Numba-accelerated TA)
│   │   │
│   │   ├── strategies/             (strategy implementations — hot-loadable)
│   │   │   ├── base.py             (Strategy abstract class)
│   │   │   ├── registry.py         (auto-discovery)
│   │   │   ├── templates/
│   │   │   │   ├── momentum.py
│   │   │   │   ├── mean_reversion.py
│   │   │   │   └── breakout.py
│   │   │   └── ml/                 ★ AI/ML HOME — see §9
│   │   │       ├── base_ml.py      (abstract MLStrategy + training hooks)
│   │   │       ├── features/       (engineered features)
│   │   │       ├── models/         (serialized .pkl / .pt artifacts + registry.json)
│   │   │       ├── lstm_predictor.py
│   │   │       ├── xgboost_signal.py
│   │   │       ├── rf_classifier.py
│   │   │       └── reinforcement/  (RL agents — optional, post-MVP1)
│   │   │
│   │   ├── db/
│   │   │   ├── session.py          (async engine + session factory)
│   │   │   ├── base.py
│   │   │   ├── models/             (SQLAlchemy models — mirror §7.2)
│   │   │   └── migrations/         (alembic env.py + versions/)
│   │   │
│   │   ├── cache/
│   │   │   ├── client.py           (Redis async client)
│   │   │   ├── keys.py             (cache key builders — see §8.2)
│   │   │   └── decorators.py       (@cached TTL decorator)
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── logging.py          (structlog config)
│   │   │   ├── tracing.py          (OpenTelemetry setup)
│   │   │   ├── metrics.py          (Prometheus metrics)
│   │   │   ├── health.py           (health probes)
│   │   │   └── encryption.py       (AES-GCM for broker creds)
│   │   │
│   │   ├── middleware/             (auth, logging, correlation_id, error_handler)
│   │   ├── schemas/                (Pydantic DTOs for REST)
│   │   └── utils/                  (datetime, money, validators)
│   │
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   │
│   └── scripts/
│       ├── seed_data.py
│       ├── generate_proto.sh       (protoc → app/api/grpc/_generated/)
│       └── create_migration.sh
│
├── frontend/
│   ├── README.md
│   ├── package.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── components.json             (shadcn/ui config)
│   ├── buf.gen.yaml                (gRPC-Web codegen)
│   ├── .env.example
│   ├── Dockerfile
│   ├── nginx.conf                  (SPA serving in prod)
│   │
│   ├── public/
│   │   ├── favicon.ico
│   │   └── logo.svg
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css               (Tailwind base + CSS vars)
│       │
│       ├── api/
│       │   ├── grpc/
│       │   │   ├── _generated/     (buf-generated clients)
│       │   │   ├── transport.ts    (Connect-Web transport + auth interceptor)
│       │   │   └── clients.ts      (typed wrapper hooks)
│       │   ├── rest/
│       │   │   ├── axios.ts        (instance + interceptors)
│       │   │   └── endpoints.ts
│       │   └── websocket/
│       │       └── hub.ts          (reconnecting WS + channel subscriptions)
│       │
│       ├── components/
│       │   ├── ui/                 (shadcn copies: button, card, dialog, …)
│       │   ├── charts/             (LineChart, CandleChart, DonutChart, Sparkline)
│       │   ├── layout/             (Shell, Sidebar, Topbar, Breadcrumbs)
│       │   └── common/             (Logo, ThemeToggle, EmptyState, Loader)
│       │
│       ├── features/
│       │   ├── auth/               (login, register, refresh flow, AuthGuard)
│       │   ├── dashboard/          (KPI cards, overall equity, daily P&L)
│       │   ├── trading/            (order ticket, positions grid, order blotter)
│       │   ├── portfolio/          (holdings, allocation donut, per-account view)
│       │   ├── strategies/         (list, create/edit, backtest, live toggle, ML model picker)
│       │   ├── scanner/            (pre-market results, setup scoring)
│       │   └── reports/            (request, list, download PDFs/Excels)
│       │
│       ├── hooks/                  (useAuth, useWs, useGrpc, usePortfolio, …)
│       ├── store/                  (zustand slices: auth, ui, portfolio)
│       ├── theme/                  (CSS variables, dark/light, brand colors)
│       ├── routes/                 (TanStack Router tree + guards)
│       ├── utils/                  (format money, percent, date, errors)
│       └── types/                  (shared TS types)
│
├── deploy/
│   ├── compose/
│   │   ├── docker-compose.dev.yml      (infra only: postgres, redis, jaeger, envoy)
│   │   └── docker-compose.prod.yml     (full stack: infra + backend + frontend + nginx)
│   ├── docker/
│   │   ├── envoy.yaml                  (gRPC-Web proxy config)
│   │   ├── nginx.conf                  (prod reverse proxy)
│   │   └── prometheus.yml
│   ├── kubernetes/                     (manifests, Helm chart — MVP2)
│   └── grafana/
│       └── dashboards/                 (importable JSON: API latency, order rate, strategy P&L)
│
├── scripts/                            (one-line lifecycle scripts — see §13)
│   ├── install.sh / install.ps1
│   ├── run.sh / run.ps1
│   ├── stop.sh / stop.ps1
│   ├── build.sh / build.ps1
│   ├── test.sh / test.ps1
│   └── migrate.sh / migrate.ps1
│
└── .github/workflows/                  (CI: lint, test, build images)
    ├── backend-ci.yml
    ├── frontend-ci.yml
    └── release.yml
```

---

## 5. Design Principles (Non-Negotiable)

1. **Async everywhere**. All I/O is `async/await` — SQLAlchemy async, `httpx`, `redis.asyncio`, WebSockets.
2. **Typed everything**. `pydantic` models for all DTOs; `mypy --strict` on `app/core/` and `app/brokers/`.
3. **No business logic in API layer**. REST/gRPC/WS handlers only translate DTOs and call a service.
4. **One source of truth for contracts** — `.proto` files in `proto/`. Both Python servicers and TypeScript clients generate from them.
5. **Structured logs, always**. Every log line is JSON with `trace_id`, `user_id`, `account_id`, `correlation_id` when available. No `print`, no f-string logging with PII.
6. **Every mutating action goes through audit**. `AuditService.record(event)` is the only write path for `audit_events`.
7. **Secrets never in code**. Use `.env` locally, environment variables / secrets manager in prod. Broker API keys are AES-GCM encrypted in DB.
8. **ML strategies are plug-ins**. See §9 — adding a new model must not require changes outside `app/strategies/ml/`.
9. **Tests ship with features**. No merge without at least one unit test for new service logic and one integration test for new API endpoint.
10. **Scripts are the interface**. `scripts/install.sh` and `scripts/run.sh` must work on a clean machine with only Docker + Python + Node installed.

---

## 6. Authentication & Security

### 6.1 JWT Flow

- **Access token**: JWT (HS256), 15-minute TTL, carries `sub` (user id), `jti`, `roles`.
- **Refresh token**: opaque 64-byte base64, 7-day TTL, stored hashed in `refresh_tokens` table, single-use (rotated on every refresh), revocable.
- **Endpoints**:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login` → `{access_token, refresh_token, expires_in}`
  - `POST /api/v1/auth/refresh` → new pair (old refresh invalidated)
  - `POST /api/v1/auth/logout` → revoke all user refresh tokens
  - `GET /api/v1/auth/me`
- **gRPC auth**: a unary interceptor reads `authorization: Bearer …` from metadata, validates, injects `User` into context.
- **Frontend**: axios/Connect-Web interceptor attaches `Authorization` header, on `401` triggers silent refresh; if refresh fails, redirects to `/login`.

### 6.2 Broker Credential Encryption

- AES-256-GCM with a master key from `DHRUVA_MASTER_KEY` env var (32 bytes, base64).
- Encrypted per-field (`api_key_encrypted`, `api_secret_encrypted`) with a fresh 12-byte nonce stored alongside the ciphertext.
- Decrypt only at the moment of broker call; never log decrypted secrets.

### 6.3 Request Hardening

- CORS: allow `FRONTEND_ORIGIN` from env, deny wildcard in prod.
- Rate limiting: 100 req/min/user on REST, 20 orders/min/account (Redis token bucket).
- Input validation via Pydantic v2 models at every boundary.
- Passwords hashed with `bcrypt` (work factor 12).

---

## 7. Database

### 7.1 Tech

- **PostgreSQL 16** with **TimescaleDB** extension for hypertables.
- **Alembic** migrations, auto-generated with `--autogenerate` but always reviewed.
- Async SQLAlchemy 2.0, session-per-request, `AsyncSession` via FastAPI dependency.

### 7.2 Tables (minimum set)

Regular tables:

- `users` — id (uuid), email, password_hash, display_name, created_at
- `accounts` — id, user_id, name, broker_id, broker_account_id, api_key_encrypted, api_secret_encrypted, nonce, config_jsonb, is_active, created_at
- `strategies` — id, account_id, name, strategy_class (dotted path), parameters_jsonb, is_enabled, mode (`paper` | `live`), is_ml, model_version, created_at
- `orders` — id, account_id, strategy_id, symbol, side, qty, price, order_type, status, broker_order_id, filled_qty, filled_price, created_at, updated_at
- `trades` — id, order_id, account_id, strategy_id, symbol, side, qty, price, fees, pnl, trade_time
- `positions` — id, account_id, symbol, qty, avg_cost, current_price, unrealized_pnl, realized_pnl, sector, instrument_type, updated_at (unique `(account_id, symbol)`)
- `portfolio_snapshots` — id, account_id, snapshot_date, total_value, cash, invested, daily_return, cumulative_return
- `rebalance_plans` — id, account_id, name, status, target_allocation_jsonb, created_at, executed_at
- `notification_configs` — id, account_id, channel, destination, events_jsonb, is_active
- `risk_alerts` — id, account_id, alert_type, severity, message, is_read, created_at
- `reports` — id, user_id, report_type, period, file_path, format, generated_at
- `audit_events` — id, user_id, action, entity_type, entity_id, old_value_jsonb, new_value_jsonb, ip, user_agent, trace_id, created_at (append-only, never updated)
- `refresh_tokens` — id, user_id, token_hash, expires_at, is_revoked, created_at, rotated_from

Hypertables (TimescaleDB):

- `ohlcv_candles` — symbol, exchange, timeframe, ts, open, high, low, close, volume (time-partitioned on `ts`, 7-day chunks)
- `order_events` — order_id, event_type, payload_jsonb, ts
- `pnl_snapshots` — account_id, ts, mtm, realized, unrealized, cash

### 7.3 Indexes (create explicitly)

- `orders(account_id, created_at DESC)`
- `trades(account_id, trade_time DESC)`
- `positions(account_id)`
- `audit_events(entity_type, entity_id)` and `(user_id, created_at DESC)`
- `ohlcv_candles(symbol, timeframe, ts DESC)` (TimescaleDB handles time)

---

## 8. Caching, Tracing, Logging, Metrics

### 8.1 Redis Layout

```
price:{symbol}                 TTL 5s
position:{account_id}:{symbol} TTL 1s
holdings:{account_id}          TTL 60s
equity:{account_id}            TTL 30s
strategy:perf:{strategy_id}    TTL 300s
risk:{account_id}:metrics      TTL 600s
analytics:{account_id}:{period}:{metric}  TTL 300s
ratelimit:{user_id}            sliding window
ratelimit:orders:{account_id}  token bucket
```

Implement in `app/cache/keys.py` as helper functions, never hard-code keys in services.

### 8.2 Logging (`app/infrastructure/logging.py`)

- `structlog` configured to emit JSON to stdout and to a PostgreSQL sink (table `logs`, indexed by `trace_id`, `level`, `created_at`).
- Bound context per request: `trace_id`, `user_id`, `account_id`, `correlation_id`, `path`, `method`.
- `LOG_LEVEL` env var; default `INFO` in prod, `DEBUG` in dev.

### 8.3 Tracing (`app/infrastructure/tracing.py`)

- OpenTelemetry with auto-instrumentation for FastAPI, gRPC, SQLAlchemy, Redis, httpx.
- Resource attributes: `service.name=dhruva-backend`, `service.version`, `deployment.environment`.
- Exporter: OTLP over gRPC to Jaeger (`http://jaeger:4317` in compose, configurable).
- Custom spans around: `broker.place_order`, `risk.validate`, `strategy.execute`, `ml.predict`, `report.generate`.

### 8.4 Metrics (`app/infrastructure/metrics.py`)

Expose `/metrics` (Prometheus text format). Required counters/histograms:

- `dhruva_http_requests_total{method,route,status}`
- `dhruva_http_request_duration_seconds{route}` histogram
- `dhruva_orders_placed_total{broker,status}`
- `dhruva_order_place_duration_seconds` histogram
- `dhruva_strategy_executions_total{strategy,result}`
- `dhruva_ml_predictions_total{model,signal}`
- `dhruva_active_websocket_connections`

### 8.5 Dashboards

Ship Grafana JSON under `deploy/grafana/dashboards/`:

1. **API Overview** — RPS, p50/p95/p99 latency, error rate per route.
2. **Order Flow** — orders/sec by broker, fill ratio, rejection reasons, p95 latency.
3. **Strategy Performance** — live equity, cumulative P&L, signals/hour, ML confidence histogram.
4. **Infrastructure** — DB connections, Redis hit ratio, queue lag.
5. **Portfolio (per-account)** — selectable `account_id`, equity curve, drawdown, exposure by sector.
6. **Portfolio (overall)** — consolidated across accounts.

Frontend also shows its own in-app charts (§11) sourced from the same APIs.

---

## 9. Strategy Framework (Rules + AI/ML)

### 9.1 Abstract Base (`app/strategies/base.py`)

```python
class Strategy(ABC):
    id: str
    account_id: str
    parameters: dict

    @abstractmethod
    async def on_candle(self, candle: Candle, context: StrategyContext) -> Optional[Signal]:
        """Called on each new candle. Return a Signal or None."""

    async def on_fill(self, fill: Fill, context: StrategyContext) -> None: ...
    async def on_start(self, context: StrategyContext) -> None: ...
    async def on_stop(self, context: StrategyContext) -> None: ...
```

`Signal` is `{symbol, side, qty, order_type, reason, confidence: float in [0,1], metadata}`.

`StrategyContext` exposes: `market_data`, `positions`, `place_order`, `logger`, `tracer`, `cache`.

### 9.2 Template Strategies (`app/strategies/templates/`)

Rule-based: `momentum.py`, `mean_reversion.py`, `breakout.py`. Pure logic, zero external calls except through `context`.

### 9.3 ML Strategies (`app/strategies/ml/`)

**Design contract — every ML strategy:**

1. Subclasses `MLStrategy(Strategy)` in `base_ml.py`.
2. Declares `feature_spec: FeatureSpec` (list of features + window + transforms).
3. Implements `load_model(version: str)` — loads from `models/{strategy_name}/{version}/`.
4. Implements `predict(features: np.ndarray) -> Prediction` — returns `(signal_class, probability)`.
5. Optionally implements `train(dataset)` — used by the standalone training CLI, never at runtime.
6. Registers itself in `registry.py` via `@register_ml_strategy`.

**Folder layout**:

```
app/strategies/ml/
├── base_ml.py
├── registry.py
├── features/
│   ├── price_features.py          (returns, log returns, vol)
│   ├── technical_features.py      (RSI, MACD, BB via pandas-ta)
│   ├── microstructure_features.py (spread, imbalance — future)
│   └── builder.py                 (FeatureSpec → feature matrix)
├── models/
│   ├── registry.json              (name → versions → path + metrics)
│   ├── lstm_predictor/v1/model.pt
│   └── xgboost_signal/v3/model.json
├── lstm_predictor.py              (PyTorch LSTM for next-bar direction)
├── xgboost_signal.py              (XGBoost classifier → BUY/SELL/HOLD)
├── rf_classifier.py               (RandomForest baseline)
├── training/
│   ├── data_loader.py
│   ├── train_xgboost.py           (CLI: `python -m app.strategies.ml.training.train_xgboost`)
│   └── train_lstm.py
└── reinforcement/                 (optional, post-MVP1)
    ├── env.py
    └── ppo_agent.py
```

**Runtime rules**:

- Models are loaded once at app start and cached (`lru_cache`) per `(strategy_class, version)`.
- Prediction must complete < 20 ms per candle on commodity CPU; anything heavier runs in a dedicated worker process (post-MVP1).
- Every prediction is traced (`ml.predict` span) and counted (`dhruva_ml_predictions_total`).
- Model artifacts are NOT committed — stored in object storage or mounted volume, referenced by `registry.json`.

### 9.4 Backtesting

- `vectorbt`-based engine in `app/core/strategy/backtest.py`.
- CLI: `python -m app.scripts.backtest --strategy momentum --from 2024-01-01 --to 2024-12-31 --symbol RELIANCE.NS`.
- Outputs: equity curve, trade list, metrics (Sharpe, Sortino, Calmar, max DD, win rate). Stored as a `Report` row.

### 9.5 Live Execution

- `APScheduler` runs `strategy_service.execute_enabled_strategies()` at every candle close (1m/5m/15m/1h/1d configurable per strategy).
- Execution path: load latest candles → build features → `strategy.on_candle()` → if `Signal`, validate via `RiskEngine` → `ExecutionService.place_order()` → audit → WebSocket push.

---

## 10. Broker Adapters

### 10.1 Interface (`app/brokers/base.py`)

```python
class BrokerAdapter(ABC):
    broker_id: str

    @abstractmethod
    async def authenticate(self, creds: BrokerCredentials) -> AuthSession: ...
    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderAck: ...
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None: ...
    @abstractmethod
    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck: ...
    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...
    @abstractmethod
    async def get_holdings(self) -> list[BrokerHolding]: ...
    @abstractmethod
    async def get_margin(self) -> MarginDetails: ...
    @abstractmethod
    async def refresh_token(self) -> AuthSession: ...
    @abstractmethod
    async def health(self) -> BrokerHealth: ...
```

### 10.2 Required Adapters for MVP1

`zerodha` (Kite Connect), `upstox`, `dhan`, `fyers`, `five_paisa`. Each maps broker-specific fields to DHRUVA's canonical DTOs. Retries: 3 with exponential backoff (0.2s, 0.5s, 1s). Timeouts: connect 2s, read 5s.

### 10.3 Factory

`BrokerFactory.create(broker_id, account) -> BrokerAdapter` — resolves the class from a registry, injects decrypted credentials, reuses a pooled `httpx.AsyncClient`.

### 10.4 Health Monitor

Background job every 60s pings each active account's broker; on failure N=3 in a row, raises a `RiskAlert` of severity `Warning` and disables live trading for that account until recovery.

---

## 11. Frontend (React) Details

### 11.1 Theme

- `tailwind.config.ts` — extend colors with DHRUVA palette (amber-500 `#F59E0B` primary, zinc neutrals, semantic success/warning/danger).
- Dark-first. `<html class="dark">` by default. Light toggle via CSS variables.
- `components.json` for shadcn/ui with base color `zinc`, radius `0.5rem`.
- Logo rendered from `frontend/src/assets/logo/` (SVG) in `Topbar` and splash screen.

### 11.2 Routes (TanStack Router)

```
/                       → redirect to /dashboard (if auth) or /login
/login
/register
/dashboard              (overall KPIs + equity curve)
/trading
  /trading/orders
  /trading/positions
/portfolio
  /portfolio/$accountId (per-account detail)
/strategies
  /strategies/$id       (edit, backtest, live toggle, ML model picker)
/scanner
/reports
/settings
  /settings/accounts
  /settings/notifications
```

All routes except auth pages are guarded by `AuthGuard` hook.

### 11.3 gRPC-Web

- `proto/dhruva/v1/*.proto` is compiled via `buf generate` (config in `frontend/buf.gen.yaml`) into `frontend/src/api/grpc/_generated/`.
- Transport: `@bufbuild/connect-web` with `createGrpcWebTransport`, pointed at `VITE_GRPC_URL` (defaults to `http://localhost:8080` — Envoy).
- Auth interceptor attaches `authorization: Bearer <access>` and transparently refreshes on `code: unauthenticated`.

### 11.4 Real-time

- Single `ws://…/ws` connection multiplexed via channel names (`orders:{account}`, `positions:{account}`, `notifications:{user}`, `prices:{symbol}`).
- `reconnecting-websocket` for auto-reconnect. Push events flow into React Query cache via `queryClient.setQueryData`.

### 11.5 Charts

| Chart | Library | Usage |
|---|---|---|
| Candlestick (OHLC) | ApexCharts | Symbol detail, backtest results |
| Equity curve (line) | Recharts | Dashboard, per-account portfolio |
| Donut (allocation) | Recharts | Portfolio sector breakdown |
| Sparkline (KPI) | Recharts | KPI cards |
| Heatmap (correlation) | ApexCharts | Risk page |
| Bar (P&L by strategy) | Recharts | Strategy page |

Reusable wrappers live in `frontend/src/components/charts/` so pages never import Recharts/ApexCharts directly.

### 11.6 Pages — Minimum UX

- **Dashboard**: 4 KPI cards (Total Equity, Day P&L, Open Positions, Active Strategies), equity curve (All Accounts, selectable), recent orders table, alert feed.
- **Per-account Portfolio**: Equity curve, sector donut, holdings table, drawdown sparkline, Sharpe/Sortino cards.
- **Overall Portfolio**: Consolidated equity curve across accounts, per-account comparison chart, aggregate metrics.
- **Trading**: Order ticket (symbol search, qty, price, SL/TP), live positions grid, order blotter with filter.
- **Strategies**: List with on/off toggle, per-strategy card (live P&L, win rate, sparkline); detail page with backtest runner, parameter form, ML model version dropdown when `is_ml`.
- **Reports**: Request form + generated reports table with download links (PDF/Excel/CSV).

---

## 12. Docker & Deployment

### 12.1 `deploy/compose/docker-compose.dev.yml`

Runs only infrastructure locally so developers can run backend/frontend natively:

- `postgres` (TimescaleDB image), `redis`, `jaeger`, `envoy`, `prometheus`, `grafana`.

### 12.2 `deploy/compose/docker-compose.prod.yml`

Full stack: infra + `backend` (built from `backend/Dockerfile`) + `frontend` (built from `frontend/Dockerfile`, served by nginx) + `envoy` front door. Uses `.env` file for secrets (never committed).

### 12.3 `backend/Dockerfile`

Multi-stage:

1. `python:3.12-slim` builder — install poetry/pip, build wheels.
2. `python:3.12-slim` runtime — copy app, non-root user `dhruva`, `HEALTHCHECK` on `/health/live`, `EXPOSE 8000 50051 8001`, entrypoint `uvicorn app.main:app`.

### 12.4 `frontend/Dockerfile`

Multi-stage:

1. `node:22-alpine` builder — `npm ci && npm run build`.
2. `nginx:alpine` runtime — copy `dist/` to `/usr/share/nginx/html`, custom `nginx.conf` with SPA fallback + gzip + security headers.

### 12.5 Kubernetes (stub, MVP2)

`deploy/kubernetes/` contains Deployment, Service, Ingress, ConfigMap, Secret manifests per component plus a Helm chart skeleton.

---

## 13. Scripts (One-Command Lifecycle)

All scripts live in top-level `scripts/`. Each `.sh` has a matching `.ps1`. Every script prints a banner, exits non-zero on failure, and is idempotent.

### 13.1 `scripts/install.sh` — install entire ecosystem

1. Verify prerequisites: `docker`, `docker compose`, `python3.12`, `node >=22`, `npm >=10`.
2. Create `.env` files from `.env.example` if missing.
3. `docker compose -f deploy/compose/docker-compose.dev.yml pull`.
4. Create Python venv under `backend/.venv`, activate, `pip install -U pip wheel`, `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`.
5. Run `backend/scripts/generate_proto.sh` to generate gRPC stubs into `backend/app/api/grpc/_generated/`.
6. `cd frontend && npm ci`, then `npx buf generate` for gRPC-Web clients.
7. Bring up infra: `docker compose -f deploy/compose/docker-compose.dev.yml up -d`.
8. Wait for Postgres healthy, then run `alembic upgrade head`.
9. Optionally seed via `python backend/scripts/seed_data.py`.
10. Print next-step banner: "Run `scripts/run.sh` to start DHRUVA."

### 13.2 `scripts/run.sh` — start the whole app

1. Ensure infra is up (`docker compose … up -d` is idempotent).
2. Start backend in background: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` (dev) or production command.
3. Start frontend dev server: `cd frontend && npm run dev` (port 5173).
4. Tail both logs in split-screen (using `concurrently` on POSIX or Start-Job on PowerShell).
5. On Ctrl+C, gracefully stop backend + frontend (infra stays up; `stop.sh` tears it down).

### 13.3 Other scripts

- `scripts/stop.sh` — stop backend, frontend, and (with `--all` flag) infra.
- `scripts/build.sh` — build production Docker images.
- `scripts/test.sh` — `pytest` backend, `vitest` + `playwright` frontend.
- `scripts/migrate.sh` — `alembic upgrade head`; with `--create "msg"` it runs `alembic revision --autogenerate -m "msg"`.

---

## 14. Phase-by-Phase Execution Plan (Days 1–22)

### Phase 1 — Core Infrastructure (Days 1–6)

- **Day 1**: Repo scaffold is already in place. Implement `app/main.py`, `config.py`, structured logging, OpenTelemetry tracing, `/health/live` + `/health/ready`. Bring up `docker-compose.dev.yml`. Verify Jaeger receives spans.
- **Day 2**: JWT auth module (`core/auth/`), `users`, `refresh_tokens` tables, register/login/refresh/me endpoints. Redis client + `cache/keys.py` + `@cached` decorator. Rate limiter middleware.
- **Day 3**: SQLAlchemy models for all entities in §7.2. Alembic initial migration. TimescaleDB hypertables created via `create_hypertable` in migration.
- **Day 4**: `ExecutionService`, `RiskEngine`, `PositionTracker`. REST `POST /api/v1/orders`. Audit event store with append-only `audit_events` table.
- **Day 5**: Broker abstract base + factory + Zerodha + Upstox adapters. Broker health monitor background job. Credential encryption (§6.2).
- **Day 6**: Strategy framework skeleton (`base.py`, `registry.py`, one template + one ML stub). Backtesting CLI. APScheduler wiring for live strategy execution.

### Phase 2 — Portfolio, Analytics, Reports (Days 7–12)

- **Day 7**: `PortfolioService`, holdings consolidation across accounts, `portfolio_snapshots` daily job.
- **Day 8**: Analytics — Sharpe, Sortino, Calmar, max DD, VaR (historical + parametric), sector exposure. Cached.
- **Day 9**: Rebalancer service (target allocation → order plan → preview → execute).
- **Day 10**: Dhan, Fyers, 5Paisa adapters. Reach ≥5 brokers supported.
- **Day 11**: Reports — PDF (`reportlab`), Excel (`openpyxl`), CSV. Types: Strategy Performance, Portfolio Monthly, Risk, Tax P&L, Trade Journal, Multi-Account Consolidated.
- **Day 12**: Scanner service — pre-market momentum/breakout/mean-reversion patterns with 0–100 setup scoring. REST endpoint + results table.

### Phase 3 — Real-Time, gRPC, Monitoring (Days 13–15)

- **Day 13**: gRPC servicers for `AuthService`, `OrderService`, `PortfolioService`, `StrategyService`. Envoy gRPC-Web proxy config.
- **Day 14**: WebSocket hub with channel multiplexing. Push order fills, position updates, alerts, price ticks.
- **Day 15**: Prometheus metrics, Grafana dashboards (§8.5) provisioned via `deploy/grafana/`. Email notifier (SMTP) for risk alerts and daily summaries.

### Phase 4 — React Frontend (Days 16–19)

- **Day 16**: Vite scaffold, Tailwind, shadcn/ui setup, theme, Logo, Shell layout (Sidebar + Topbar), TanStack Router with guard.
- **Day 17**: Auth feature (login/register/refresh), REST client + gRPC-Web client, axios/Connect interceptors.
- **Day 18**: Dashboard + Portfolio + Trading pages with live WebSocket feeds and charts.
- **Day 19**: Strategies + Scanner + Reports pages; settings/accounts flow with broker credential form.

### Phase 5 — Testing, Security, Deployment (Days 20–22)

- **Day 20**: Unit + integration tests reaching ≥80% coverage on `app/core/` and `app/brokers/`. Playwright E2E for login → place order → see position.
- **Day 21**: Security hardening (OWASP review, secrets audit, rate limits, input fuzz), `mypy --strict` on core paths, load test with `locust` (100 concurrent users, p95 < 200 ms REST).
- **Day 22**: Production Dockerfiles, `docker-compose.prod.yml`, GitHub Actions CI/CD (lint, test, build, push images). Staging deploy rehearsal.

---

## 15. Acceptance Criteria (MVP1 Done Definition)

- [ ] `scripts/install.sh` runs to completion on a fresh Ubuntu 24.04 / macOS / Windows 11 + WSL machine.
- [ ] `scripts/run.sh` starts the stack; visiting `http://localhost:5173` shows the login page with DHRUVA logo and dark theme.
- [ ] A user can register, log in, add a Zerodha account (with encrypted credentials), place a paper order, and see it filled on the positions grid in real time.
- [ ] At least 5 broker adapters implement all methods of `BrokerAdapter` with green integration tests (using broker sandboxes or mocks).
- [ ] At least 3 template strategies and 1 ML strategy pass backtests and can run live in paper mode.
- [ ] Per-account and overall equity/P&L charts render correctly with live data and with historical backfill.
- [ ] `/health/ready` returns 200 only when DB, Redis, and at least one broker health check pass.
- [ ] Jaeger shows a full trace for `place_order` with spans: `rest.post_orders → execution.place_order → risk.validate → broker.zerodha.place_order → audit.record → ws.push`.
- [ ] Grafana dashboards load and display non-zero data under synthetic load.
- [ ] Reports (PDF, Excel, CSV) generate correctly for at least 4 report types and are downloadable from the UI.
- [ ] `pytest` and `vitest` CI jobs pass; coverage gate ≥80% on core services.
- [ ] `mypy --strict app/core app/brokers` passes with zero errors.
- [ ] `ruff check .` and `npm run lint` both pass with zero errors.
- [ ] Secrets audit: no hardcoded keys; `.env.example` committed, `.env` gitignored.
- [ ] Production images build: `docker build` succeeds for both backend and frontend.

---

## 16. Open Questions (Decide Before Day 1)

1. **Broker sandbox availability** — confirm access to Zerodha Kite Connect sandbox, Upstox sandbox, etc. If unavailable, build with recorded HTTP fixtures.
2. **Market data source** — in MVP1, rely on each broker's quote API per account, or subscribe to a single feed (e.g., Global Datafeeds, Truedata)? Decide before Day 5.
3. **Deployment target** — single VM with Docker Compose, or Kubernetes from day one? Default: VM for MVP1, K8s manifests stubbed for MVP2.
4. **Multi-tenancy** — single-user-per-instance (simpler) or multi-tenant DB (row-level `user_id` filters everywhere) from day one? Default: multi-tenant from day one (cheap to do now, expensive to retrofit).

---

## 17. Reference Documents

- `docs/architecture/DHRUVA_Python_OpenAlgo_Master_Plan.md` — prior Python plan, useful context on OpenAlgo leverage.
- `docs/architecture/DHRUVA_Complete_Plan.md` — original .NET architecture (archival only; Python supersedes it).
- `docs/phase1-reference/DHRUVA_Phase1_Implementation_Prompt.md` — original .NET Phase 1 (archival; kept for wording/flow ideas).
- `docs/brand/DHRUVA_Logo_Design_Prompt.md` — brand guidelines, palette, logo concepts.
- `docs/guides/IMPLEMENTATION_GUIDE.md` — quick-start guide (refresh to match this prompt when Day 1 begins).

---

**Status**: Ready to execute. Start with §14 Day 1.
**Owner**: DHRUVA Team.
**Last updated**: see git log.
