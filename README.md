# DHRUVA — Ultra-Fast Algo Trading Platform

> **DHRUVA** (Sanskrit: *Pole Star*) — production-grade algorithmic trading + portfolio management for Indian markets (NSE/BSE).
>
> **Stack**: Python 3.12 (FastAPI + gRPC) backend · React 18 + Vite + TypeScript frontend · PostgreSQL + TimescaleDB · Redis · gRPC-Web · Docker.

---

## What it does

- **Multi-broker execution** via 11 adapters plus a paper broker (Zerodha, Upstox, Dhan, Fyers, 5Paisa, Angel One, Shoonya, Kotak Neo, Alice Blue, Groww). Upstox/Dhan instrument sync and the Groww adapter are written from the brokers' published docs and have not been exercised against live accounts — test in a sandbox first.
- **Rule-based + AI/ML strategies** — XGBoost, LSTM, RandomForest baseline, optional RL — all hot-loadable via a plugin contract.
- **Real-time portfolio analytics** — Sharpe, Sortino, Calmar, max drawdown, VaR, sector exposure.
- **Per-account and consolidated dashboards** — equity curves, P&L, drawdown, KPIs.
- **Reports** — PDF, Excel, CSV (strategy performance, portfolio, risk, tax, trade journal).
- **Enterprise observability** — structured JSON logs, OpenTelemetry tracing (Jaeger), Prometheus metrics, Grafana dashboards.
- **Production-grade security** — JWT (15-min access + 7-day refresh), AES-256-GCM encrypted broker credentials, append-only audit log.

---

## Quick start

### One-shot install + run (Linux/macOS/WSL)

```bash
git clone <your-repo-url>
cd Druva

bash scripts/install.sh           # installs everything + brings up infra
bash scripts/run.sh               # starts backend + frontend
```

### One-shot install + run (Windows / PowerShell 7+)

```powershell
git clone <your-repo-url>
cd Druva

pwsh ./scripts/install.ps1
pwsh ./scripts/run.ps1
```

### No Docker? (macOS / Homebrew)

```bash
bash scripts/install.sh --skip-infra   # python venv + npm deps only
bash scripts/dev-local.sh              # Postgres 18 + TimescaleDB + Redis via brew, migrate, seed
bash scripts/run.sh --no-docker        # backend + frontend
```

`dev-local.sh` is idempotent. The Docker compose stack uses Postgres 16; the
Homebrew route uses Postgres 18 (what the Timescale formula builds against).

### First login

The seed step creates two accounts:

| Username | Password | What |
|---|---|---|
| `administrator` | `Admin@123` | admin, empty — add a broker account in Settings |
| `demo` | `DhruvaDemo123!` | paper account with positions, orders, strategies, goals |

Change both before exposing the app anywhere. With `DHRUVA_ENV` set to
`staging`/`production` the backend refuses to start on a default JWT secret,
a missing `DHRUVA_MASTER_KEY`, or `DHRUVA_DEBUG=true`.

Then open:

| URL | What |
|---|---|
| http://localhost:5173 | DHRUVA web app (React) |
| http://localhost:8000/docs | REST API (Swagger) |
| http://localhost:8080 | gRPC-Web (via Envoy) |
| http://localhost:16686 | Jaeger (distributed traces) |
| http://localhost:9090 | Prometheus |
| http://localhost:3000 | Grafana (admin / admin) |

---

## Repository layout

```
Druva/
├── README.md                                  ← you are here
├── LICENSE
├── .gitignore
│
├── docs/                                      All documentation
│   ├── README.md                              Doc index
│   ├── prompts/
│   │   └── DHRUVA_Python_React_Master_Prompt.md   ★ THE master prompt
│   ├── architecture/
│   ├── brand/
│   ├── guides/
│   └── phase1-reference/                      Archived .NET reference
│
├── proto/                                     Source-of-truth gRPC contracts
│   └── dhruva/v1/                             auth, orders, portfolio, strategies, scanner, reports
│
├── backend/                                   Python 3.12 backend
│   ├── README.md
│   ├── pyproject.toml                         ruff/mypy/pytest config
│   ├── requirements.txt / -dev.txt
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── .env.example
│   └── app/
│       ├── main.py · config.py
│       ├── api/      rest/v1, grpc/servicers, websocket
│       ├── core/     auth, execution, portfolio, strategy, scanner, reports, notifications, audit
│       ├── brokers/  zerodha, upstox, dhan, fyers, five_paisa, angel_one, shoonya, kotak_neo, alice_blue, groww, paper
│       ├── data/     market data pipeline, indicators (Numba)
│       ├── strategies/
│       │   ├── base.py · registry.py
│       │   ├── templates/      momentum, mean_reversion, breakout
│       │   └── ml/ ★          base_ml, features, models, lstm/xgboost/rf, training, reinforcement
│       ├── db/       sqlalchemy models + alembic migrations
│       ├── cache/    redis client + key builders
│       ├── infrastructure/  logging, tracing, metrics, encryption, health
│       ├── middleware · schemas · utils
│       └── (tests/ outside app/)
│
├── frontend/                                  React 18 + Vite + TypeScript
│   ├── README.md
│   ├── package.json · tsconfig.json · vite.config.ts
│   ├── tailwind.config.ts · components.json   shadcn/ui (zinc + amber)
│   ├── buf.gen.yaml                           gRPC-Web codegen
│   ├── Dockerfile · nginx.conf
│   ├── public/logo.svg
│   └── src/
│       ├── main.tsx · App.tsx · index.css     dark-first theme
│       ├── api/      rest (axios), grpc (connect-web), websocket (multiplexed)
│       ├── components/   ui, charts, layout, common
│       ├── features/     auth, dashboard, trading, portfolio, strategies, scanner, reports
│       ├── hooks · store · routes · theme · utils · types
│
├── deploy/
│   ├── compose/      docker-compose.dev.yml · docker-compose.prod.yml
│   ├── docker/       envoy.yaml · prometheus.yml · nginx.conf
│   ├── grafana/dashboards/                    importable JSON dashboards
│   └── kubernetes/                            (stub for MVP2)
│
├── scripts/                                   one-command lifecycle
│   ├── install.sh / install.ps1               install whole ecosystem
│   ├── run.sh     / run.ps1                   start backend + frontend
│   ├── stop.sh    / stop.ps1
│   ├── build.sh   / build.ps1                 prod docker images
│   ├── test.sh    / test.ps1
│   └── migrate.sh / migrate.ps1
│
└── .github/workflows/                         CI: lint, test, build images
```

---

## Where to add a new AI/ML strategy

It's a plugin — no other folder changes.

1. Drop a new file in [`backend/app/strategies/ml/`](backend/app/strategies/ml/).
2. Subclass `MLStrategy`, declare `FeatureSpec`, implement `load_model` + `predict`.
3. Register with `@register_strategy("my_model_v1")`.
4. Add the trained artifact under `models/my_model/v1/` and an entry in `models/registry.json`.

Full contract in [`backend/app/strategies/ml/README.md`](backend/app/strategies/ml/README.md).

---

## The master prompt

Everything in this repo — architecture, file layout, libraries, phase plan, acceptance criteria — comes from a single document. Give that document to any developer or AI agent to build DHRUVA from scratch.

→ **[docs/prompts/DHRUVA_Python_React_Master_Prompt.md](docs/prompts/DHRUVA_Python_React_Master_Prompt.md)**

---

## Status

- ✅ Repository scaffolding and master prompt
- ⏳ Phase 1 (Days 1–6): Core infrastructure
- ⏳ Phase 2 (Days 7–12): Portfolio, analytics, reports
- ⏳ Phase 3 (Days 13–15): gRPC, WebSocket, monitoring
- ⏳ Phase 4 (Days 16–19): React frontend
- ⏳ Phase 5 (Days 20–22): Testing, security, deployment

See [`docs/prompts/DHRUVA_Python_React_Master_Prompt.md`](docs/prompts/DHRUVA_Python_React_Master_Prompt.md) §14 for the day-by-day plan and §15 for the MVP1 done definition.

---

## License

MIT — see [LICENSE](LICENSE).

🚀 **Trade with DHRUVA precision.**
