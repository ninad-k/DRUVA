# DHRUVA Backend

Python 3.12 FastAPI + gRPC backend for DHRUVA.

See [../docs/prompts/DHRUVA_Python_React_Master_Prompt.md](../docs/prompts/DHRUVA_Python_React_Master_Prompt.md) for the full implementation plan.

## Quick start (native dev)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -U pip wheel
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# edit .env as needed

# Infra (Postgres, Redis, Jaeger, Envoy, Prometheus, Grafana)
docker compose -f ../deploy/compose/docker-compose.dev.yml up -d

# Migrations
alembic upgrade head

# Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Layout

```
app/
├── api/             REST (v1) + gRPC servicers + WebSocket hubs
├── core/            Business services (auth, execution, portfolio, strategy, …)
├── brokers/         Broker adapters (zerodha, upstox, dhan, fyers, five_paisa)
├── data/            Market data pipeline, OHLCV, indicators (Numba)
├── strategies/      Template + ML strategies (see strategies/ml/ for AI models)
├── db/              SQLAlchemy models + Alembic migrations
├── cache/           Redis client, keys, cached decorator
├── infrastructure/  Logging, tracing, metrics, health, encryption
├── middleware/      Auth, logging, error handling
├── schemas/         Pydantic DTOs
└── utils/           Datetime, money, validators
```

## ML strategy home

All AI/ML strategies live under [`app/strategies/ml/`](app/strategies/ml/). See [`app/strategies/ml/README.md`](app/strategies/ml/README.md) for the plugin contract.

## Commands

| Task | Command |
|---|---|
| Run | `uvicorn app.main:app --reload` |
| Tests | `pytest` |
| Lint | `ruff check . && ruff format --check .` |
| Types | `mypy app/core app/brokers` |
| New migration | `alembic revision --autogenerate -m "msg"` |
| Apply migrations | `alembic upgrade head` |
| Regenerate gRPC stubs | `bash scripts/generate_proto.sh` |
