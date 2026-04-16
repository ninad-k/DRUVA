# DHRUVA Phase 1 + Indian-Market Essentials — Cursor Implementation Prompt

> **Read this entire document before writing any code.** This prompt is self-contained: do not assume access to prior conversations. Everything you need is here or in the files referenced.
>
> **Goal**: Implement DHRUVA Phase 1 (Days 1–6) plus the OpenAlgo-derived "Indian Market Essentials" (Day 6.5). At the end, the platform must build, run, place a paper order through one broker, return correct positions, expose traces in Jaeger, and pass the acceptance checklist in §11.
>
> **Stack**: Python 3.12 + FastAPI + gRPC + PostgreSQL/TimescaleDB + Redis + React (frontend not in scope this run).
>
> **Repo root**: `D:\Personal\Druva` on Windows (works on Linux/macOS too).

---

## 0. Prerequisites

- Python 3.12+ on PATH
- Node 22+ (only needed if regenerating gRPC-Web stubs)
- Docker Desktop running
- Git
- 16 GB RAM recommended (Postgres + Redis + Jaeger + Prometheus + Grafana + Envoy locally)

---

## 1. Repo state — what is ALREADY scaffolded

Do not recreate these. They exist in the repo as of the starting commit. Read them before writing anything.

### Already in place

```
D:\Personal\Druva\
├── README.md                                         (top-level project doc)
├── docs/
│   └── prompts/DHRUVA_Python_React_Master_Prompt.md  ← FULL design reference
├── proto/dhruva/v1/                                  (auth, orders, portfolio, strategies, scanner, reports — all .proto files)
│
├── backend/
│   ├── pyproject.toml                                (ruff, mypy, pytest config)
│   ├── requirements.txt                              (PINNED — do not change versions)
│   ├── requirements-dev.txt
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── .env.example
│   └── app/
│       ├── __init__.py
│       ├── main.py                                   (FastAPI bootstrap — has lifespan + /health/live + /health/ready stubs)
│       ├── config.py                                 (pydantic-settings — DHRUVA_* env vars)
│       ├── infrastructure/
│       │   ├── logging.py                            (structlog configure_logging + bind_request_context)
│       │   ├── tracing.py                            (OpenTelemetry configure_tracing + get_tracer)
│       │   ├── metrics.py                            (Prometheus counters/histograms — already declared)
│       │   └── encryption.py                         (AES-256-GCM encrypt/decrypt — already implemented)
│       ├── strategies/
│       │   ├── base.py                               (Strategy ABC, Candle, Signal, Fill, StrategyContext)
│       │   ├── registry.py                           (@register_strategy + import_strategies)
│       │   ├── templates/__init__.py
│       │   └── ml/
│       │       ├── README.md                         (ML plugin contract — READ THIS)
│       │       ├── base_ml.py                        (MLStrategy ABC + FeatureSpec + Prediction)
│       │       └── models/.gitkeep
│       ├── brokers/
│       │   ├── __init__.py
│       │   └── base.py                               (BrokerAdapter ABC + DTOs — needs expansion, see §6)
│       ├── cache/keys.py                             (Redis key builders + TTL constants)
│       ├── db/
│       │   ├── session.py                            (async engine + SessionLocal + get_session dep)
│       │   ├── base.py                               (declarative Base)
│       │   └── migrations/
│       │       ├── env.py                            (Alembic env, async)
│       │       └── script.py.mako
│       ├── api/{rest,rest/v1,grpc,grpc/servicers,websocket}/__init__.py   (empty packages)
│       ├── core/{auth,execution,portfolio,strategy,scanner,reports,notifications,audit}/__init__.py   (empty packages)
│       └── (db/models, schemas, middleware, utils, data) — empty packages
│
├── deploy/
│   ├── compose/docker-compose.dev.yml                (postgres, redis, jaeger, envoy, prometheus, grafana)
│   ├── compose/docker-compose.prod.yml
│   └── docker/{envoy.yaml, prometheus.yml}
│
└── scripts/
    ├── install.sh / install.ps1                      (works — run before coding)
    ├── run.sh / run.ps1
    ├── stop.sh / stop.ps1
    ├── test.sh / test.ps1
    ├── build.sh / build.ps1
    └── migrate.sh / migrate.ps1
```

### What you must implement in this run

Everything described in §3–§9 below. Empty `__init__.py` files exist for the modules — fill them in.

---

## 2. Conventions — non-negotiable

1. **Async everywhere.** Use `async def` for all I/O. Use `sqlalchemy.ext.asyncio`, `redis.asyncio`, `httpx.AsyncClient`. Never block the event loop.
2. **Pydantic v2** for all DTOs at API boundaries. SQLAlchemy 2.x for ORM. Do NOT mix v1 syntax.
3. **Type hints everywhere.** `mypy --strict` must pass on `app/core/`, `app/brokers/`, `app/strategies/`.
4. **Structured logging only.** `from app.infrastructure.logging import get_logger; logger = get_logger(__name__)`. Never use `print` or stdlib `logging` directly. Bind `trace_id`, `user_id`, `account_id` via `bind_request_context` in middleware.
5. **Tracing.** Wrap every cross-module call in a span:
   ```python
   from app.infrastructure.tracing import get_tracer
   tracer = get_tracer(__name__)
   with tracer.start_as_current_span("execution.place_order") as span:
       span.set_attribute("account_id", account_id)
   ```
6. **Metrics.** Increment counters from `app.infrastructure.metrics` at every business event (order placed, order failed, ML prediction, etc.).
7. **Cache keys** come ONLY from `app/cache/keys.py`. Never hard-code key strings.
8. **No business logic in API handlers.** REST/gRPC/WS handlers just translate DTOs and call a service in `app/core/`.
9. **No secrets in code.** Read from `app.config.get_settings()`.
10. **Audit every mutating action.** Call `AuditService.record(...)` from inside services that write to the DB. The audit row write must be in the same transaction as the business write.
11. **Tests ship with code.** No new module without at least one test in `tests/unit/` or `tests/integration/`.
12. **File ownership**: each `.py` file has ONE class or a small group of tightly-related helpers. Don't dump 500-line modules.
13. **All times are UTC** in code and DB. Convert to IST only for display/Telegram/email.
14. **Money is `decimal.Decimal`** end-to-end. Never `float` for prices/quantities/PnL.
15. **Don't change pinned versions in `requirements.txt`.** If something doesn't work, fix the code.

---

## 3. Day 1 — Foundations (logging, tracing, health, middleware, DI)

**Goal**: A running FastAPI app with structured logs in stdout, traces in Jaeger, healthchecks reflecting real DB+Redis state, and middleware that binds request context.

### 3.1 Bring up infra and verify scaffold

```bash
bash scripts/install.sh        # creates venv, installs deps, brings up infra, runs alembic (no-op)
bash scripts/run.sh            # starts uvicorn :8000
```

Verify:
- `curl http://localhost:8000/health/live` → 200 `{"status":"live"}`
- `curl http://localhost:8000/docs` → Swagger UI loads
- `docker ps` shows `dhruva-postgres`, `dhruva-redis`, `dhruva-jaeger`, `dhruva-envoy`, `dhruva-prometheus`, `dhruva-grafana` all healthy

### 3.2 Implement middleware

Create:

- **`app/middleware/__init__.py`** — empty.
- **`app/middleware/correlation_id.py`** — middleware that:
  - Reads `X-Correlation-Id` request header, generates UUIDv4 if absent.
  - Calls `bind_request_context(correlation_id=..., trace_id=current_otel_trace_id())`.
  - Sets the same value on the response header.
- **`app/middleware/request_logging.py`** — logs `http.request` with `method`, `path`, `status`, `duration_ms`. Increments `http_requests_total` and observes `http_request_duration_seconds` from `app.infrastructure.metrics`.
- **`app/middleware/error_handler.py`** — catches `Exception`, logs with `exc_info=True`, returns `{"error":"internal_error","correlation_id":"..."}` with 500. Catches `HTTPException` and returns its status untouched. Catches our custom `DhruvaError` (define in `app/core/errors.py`) with mapping to HTTP status.

Create:

- **`app/core/errors.py`** with:
  ```python
  class DhruvaError(Exception):
      http_status = 500
      code = "internal_error"
  class NotFoundError(DhruvaError):  http_status = 404; code = "not_found"
  class ValidationError(DhruvaError): http_status = 422; code = "validation_error"
  class UnauthorizedError(DhruvaError): http_status = 401; code = "unauthorized"
  class ForbiddenError(DhruvaError):    http_status = 403; code = "forbidden"
  class RiskRejectedError(DhruvaError): http_status = 422; code = "risk_rejected"
  class BrokerError(DhruvaError):       http_status = 502; code = "broker_error"
  ```

Wire all three middlewares in `app/main.py` in order: error_handler (outermost) → request_logging → correlation_id → CORS → routers.

### 3.3 Real health checks

Replace stub `/health/ready` in `app/main.py` with checks for:
- DB: `SELECT 1` via the `get_session` dependency.
- Redis: `PING`.
- Return `{"status":"ready","checks":{"db":"ok","redis":"ok"}}` or 503 with the failing component.

Create `app/infrastructure/health.py`:

```python
async def check_db(session: AsyncSession) -> tuple[bool, str]: ...
async def check_redis(redis: Redis) -> tuple[bool, str]: ...
```

### 3.4 Mount auto-instrumentation and /metrics

In `app/main.py`, after `create_app()` returns:
- `FastAPIInstrumentor.instrument_app(app)` (from `opentelemetry.instrumentation.fastapi`)
- `SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)` — see opentelemetry-instrumentation-sqlalchemy docs
- `RedisInstrumentor().instrument()`
- `HTTPXClientInstrumentor().instrument()`
- Mount `/metrics` route returning `prometheus_client.generate_latest()` with `Content-Type: text/plain; version=0.0.4`.

### 3.5 Day-1 tests

- `tests/unit/test_logging.py` — logger emits JSON with bound context.
- `tests/unit/test_encryption.py` — round-trip encrypt/decrypt; wrong key fails; tampered ciphertext fails.
- `tests/integration/test_health.py` — `/health/live` and `/health/ready` (skip if no DB, mark integration).

### 3.6 Day-1 acceptance

- `pytest -m "not integration"` passes.
- `curl /health/ready` shows DB+Redis healthy.
- `curl /metrics` returns Prometheus text.
- A request to any endpoint creates a trace visible at http://localhost:16686 (service: `dhruva-backend`).

---

## 4. Day 2 — Auth (JWT + refresh + Argon2id) and Redis cache + rate limiting

**Goal**: Users can register, log in, get an access+refresh token pair, refresh, log out. Redis cache is wired and rate limiting is enforced.

### 4.1 Swap bcrypt → Argon2id

In `requirements.txt` (already pinned) we have `passlib[bcrypt]`. ADD the line `argon2-cffi>=23.1` (do not remove passlib). Use `passlib.hash.argon2` as the primary hasher.

### 4.2 Implement `app/core/auth/`

- **`password.py`** —
  ```python
  class PasswordService:
      def hash(self, plaintext: str) -> str: ...     # argon2id
      def verify(self, plaintext: str, hashed: str) -> bool: ...
  ```
- **`tokens.py`** —
  ```python
  class TokenService:
      def create_access_token(self, user_id: str) -> str: ...   # 15 min, HS256
      def create_refresh_token(self) -> tuple[str, str]: ...    # returns (raw, sha256_hash); store hash in DB, return raw to user
      def decode_access_token(self, token: str) -> str: ...     # returns user_id, raises UnauthorizedError on bad/expired
  ```
- **`service.py`** — `AuthService` with:
  - `register(email, password, display_name) -> User`
  - `login(email, password) -> TokenPair`           (rotates refresh)
  - `refresh(refresh_token) -> TokenPair`            (single-use rotation; old token marked `is_revoked=True, rotated_to_id=<new>`)
  - `logout(user_id) -> None`                        (revoke all user refresh tokens)
  - `get_current_user(user_id) -> User`
- **`dependencies.py`** — `get_current_user(token: str = Depends(oauth2_scheme), session)` returns `User`. Raises `UnauthorizedError` on bad token. Used by every protected route.

### 4.3 REST endpoints — `app/api/rest/v1/auth.py`

```
POST /api/v1/auth/register   {email, password, display_name}    → 201 {id, email, display_name}
POST /api/v1/auth/login      {email, password}                  → 200 {access_token, refresh_token, expires_in, token_type}
POST /api/v1/auth/refresh    {refresh_token}                    → 200 {access_token, refresh_token, expires_in, token_type}
POST /api/v1/auth/logout     (auth required)                    → 204
GET  /api/v1/auth/me         (auth required)                    → 200 {id, email, display_name, created_at}
```

All request/response shapes as Pydantic v2 models in `app/schemas/auth.py`.

### 4.4 Redis cache wrapper — `app/cache/client.py`

```python
class CacheClient:
    def __init__(self, redis: Redis): ...
    async def get_json(self, key: str) -> Any | None: ...
    async def set_json(self, key: str, value: Any, ttl: int) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[Any]], ttl: int) -> Any: ...
    async def invalidate_pattern(self, pattern: str) -> int: ...
```

Singleton wired via FastAPI `Depends`. Use `app/cache/keys.py` for every key.

### 4.5 Rate limiting middleware — `app/middleware/rate_limit.py`

Two limits, both Redis-backed token buckets keyed via `cache/keys.py`:
- 100 requests/minute/user (key: `ratelimit_user(user_id)`).
- 20 orders/minute/account (key: `ratelimit_orders(account_id)`) — apply only on `/api/v1/orders` POST.

Return 429 with `{"error":"rate_limited","retry_after_seconds":...}`. Set `Retry-After` header.

### 4.6 Day-2 tests

- `tests/unit/test_password.py` — hash/verify, wrong password fails, tampered hash fails.
- `tests/unit/test_tokens.py` — access token round-trip, expiry rejection, audience mismatch rejection.
- `tests/integration/test_auth_flow.py` — register → login → /me → refresh → logout → /me 401.
- `tests/integration/test_rate_limit.py` — 101st request in 60s gets 429.

### 4.7 Day-2 acceptance

- All four auth endpoints work end-to-end via curl.
- `pytest tests/` passes.
- 429 returned after exceeding limits.
- `/metrics` shows `dhruva_http_requests_total{status="429"}` > 0 after rate-limit test.

---

## 5. Day 3 — Database (with OpenAlgo-inspired Indian-market tables)

**Goal**: All entities defined as SQLAlchemy 2 async models, Alembic initial migration applied, TimescaleDB hypertables created.

### 5.1 SQLAlchemy models — `app/db/models/`

One file per logical area:

| File | Models |
|---|---|
| `user.py` | `User`, `RefreshToken` |
| `account.py` | `Account` (broker creds encrypted) |
| `strategy.py` | `Strategy` |
| `order.py` | `Order` |
| `trade.py` | `Trade` |
| `position.py` | `Position` |
| `portfolio.py` | `PortfolioSnapshot`, `RebalancePlan` |
| `notification.py` | `NotificationConfig`, `RiskAlert` |
| `report.py` | `Report` |
| `audit.py` | `AuditEvent` (append-only) |
| `instrument.py` | **NEW** `Instrument`, `MasterContractStatus`, `QtyFreezeLimit` |
| `calendar.py` | **NEW** `MarketHoliday`, `MarketSession` |
| `latency.py` | **NEW** `LatencySample` (hypertable) |
| `webhook.py` | **NEW** `WebhookSource`, `WebhookEvent` |
| `approval.py` | **NEW** `ApprovalRequest` (Action Center) |

Field details (only the new/important ones; standard fields like `id, created_at, updated_at` per the master prompt §7.2):

#### `Instrument`
```
id (uuid, pk)
symbol (str, idx)
exchange (enum: NSE/BSE/NFO/BFO/MCX/CDS/BCD)
broker_token (str)         -- broker-specific instrument token
broker_id (str)            -- which broker's master file this came from
instrument_type (enum: EQ/FUT/CE/PE/IDX)
expiry (date, nullable)
strike (numeric, nullable)
lot_size (int)
tick_size (numeric)
isin (str, nullable)
trading_symbol (str)       -- broker-side ticker
exchange_token (str, nullable)
extra_jsonb (jsonb)
updated_at (ts, idx)

INDEX (broker_id, symbol, exchange) UNIQUE
INDEX (symbol)               -- for cross-broker symbol search
```

#### `MasterContractStatus`
```
id (uuid, pk)
broker_id (str, idx)
last_synced_at (ts)
status (enum: ok/stale/failed)
record_count (int)
checksum (str, nullable)
error_message (str, nullable)
```

#### `QtyFreezeLimit`
```
id (uuid, pk)
exchange (enum)
symbol (str)
qty_freeze (numeric)
effective_from (date)
INDEX (exchange, symbol)
```

#### `MarketHoliday`
```
id, exchange, holiday_date, description
INDEX (exchange, holiday_date) UNIQUE
```

#### `MarketSession`
```
id, exchange, weekday (0=Mon), open_time (time), close_time (time), session_type (regular/pre/post)
```

#### `LatencySample` — TimescaleDB hypertable on `ts`
```
ts (timestamptz, pk-part)
broker_id (str)
operation (str)            -- place_order / cancel_order / get_positions / get_quotes / ...
account_id (uuid, nullable)
latency_ms (numeric)
status (str)               -- success / failed / timeout
INDEX (broker_id, ts DESC)
```

#### `WebhookSource`
```
id, account_id (fk), source (enum: chartink/tradingview/gocharting), secret_token (encrypted), is_active, created_at
```

#### `WebhookEvent`
```
id, source_id (fk), payload_jsonb, received_at, processed_at, status (enum: pending/processed/failed/ignored), error
```

#### `ApprovalRequest`
```
id, account_id, strategy_id, signal_jsonb, status (enum: pending/approved/rejected/expired),
requested_at, decided_at, decided_by_user_id (nullable), expires_at
INDEX (account_id, status, requested_at DESC)
```

### 5.2 Update existing tables for new fields

- `Account` — add `default_product` (MIS/CNC/NRML), `is_paper` (bool), `paper_starting_capital` (numeric).
- `Strategy` — add `requires_approval` (bool, default false), `mode` enum (`paper`/`live`), `is_ml` (bool), `model_version` (str, nullable).

### 5.3 Alembic initial migration

```bash
bash scripts/migrate.sh --create "phase1_schema"
```

Open the generated revision and:
1. Verify it picked up every model.
2. Add `op.execute("CREATE EXTENSION IF NOT EXISTS \"timescaledb\";")` at top of `upgrade()`.
3. After `latency_samples` table creation, add:
   ```python
   op.execute("SELECT create_hypertable('latency_samples', 'ts', chunk_time_interval => INTERVAL '7 days');")
   ```
4. Same hypertable conversion for `ohlcv_candles`, `order_events`, `pnl_snapshots` once those tables exist (define them now too — see master prompt §7.2).

Run `bash scripts/migrate.sh` and verify schema in `psql`.

### 5.4 Day-3 tests

- `tests/integration/test_models_crud.py` — create + read each entity.
- `tests/integration/test_audit_append_only.py` — attempt to UPDATE `audit_events` row → should fail (add a DB trigger in the migration, see below).

Add this trigger in the migration:
```python
op.execute("""
CREATE OR REPLACE FUNCTION audit_events_no_update_delete() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_immutable
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_no_update_delete();
""")
```

### 5.5 Day-3 acceptance

- `alembic upgrade head` succeeds on fresh DB.
- `\dt` in psql shows all tables.
- `\d+ latency_samples` shows hypertable info.
- Audit immutability test passes.

---

## 6. Day 4 — Execution, Risk, Audit (with smart_order/close/cancel_all/basket)

**Goal**: A user can POST `/api/v1/orders`, the order goes through risk checks, gets routed via the (mocked) broker adapter, the position is updated, and the audit trail records it — all in < 100 ms p95 with mocked broker.

### 6.1 `app/core/audit/event_store.py`

```python
class AuditService:
    async def record(
        self,
        *,
        action: str,                   # e.g. "order.placed", "order.cancelled", "strategy.enabled"
        entity_type: str,              # e.g. "Order"
        entity_id: str,
        old_value: dict | None,
        new_value: dict | None,
        user_id: str | None,
        ip: str | None,
        user_agent: str | None,
        session: AsyncSession,         # caller passes their session so we share txn
    ) -> AuditEvent: ...
```

Caller MUST be inside an existing transaction. Do NOT commit inside `record`.

### 6.2 `app/core/execution/`

- **`models.py`** — Pydantic DTOs:
  ```python
  class PlaceOrderRequest(BaseModel):
      account_id: UUID
      symbol: str
      exchange: Exchange
      side: Literal["BUY","SELL"]
      quantity: Decimal
      order_type: Literal["MARKET","LIMIT","SL","SL_M"]
      product: Literal["MIS","CNC","NRML"]
      price: Decimal | None = None
      trigger_price: Decimal | None = None
      stop_loss: Decimal | None = None
      take_profit: Decimal | None = None
      strategy_id: UUID | None = None
      tag: str | None = None

  class SmartOrderRequest(BaseModel):
      account_id: UUID
      symbol: str
      exchange: Exchange
      target_quantity: Decimal       # signed: positive = long target, negative = short target, 0 = flatten
      product: Literal["MIS","CNC","NRML"]
      order_type: Literal["MARKET","LIMIT"] = "MARKET"
      price: Decimal | None = None

  class BasketOrderItem(PlaceOrderRequest): ...
  class BasketOrderRequest(BaseModel):
      orders: list[BasketOrderItem]
      atomic: bool = False           # if true, fail all if any rejected by risk
  ```

- **`risk_engine.py`** — `RiskEngine` with checks (each returns `RiskCheckResult` with `passed: bool, reason: str | None`):
  - `check_market_hours(exchange)` — uses `MarketSession` + `MarketHoliday` table.
  - `check_symbol_exists(symbol, exchange, broker_id)` — must exist in `Instrument`.
  - `check_qty_freeze(exchange, symbol, quantity)` — qty < `QtyFreezeLimit`.
  - `check_min_lot(quantity, lot_size)` — quantity is a multiple of lot_size.
  - `check_margin(account, required_margin)` — broker margin ≥ required.
  - `check_concentration(account, symbol, new_qty)` — single-symbol exposure ≤ configurable cap (default 30%).
  - `check_max_orders_per_minute(account)` — same Redis bucket as the rate limiter.
  - `validate(request) -> RiskValidationResult` runs them in order; first failure short-circuits.

- **`position_tracker.py`** —
  ```python
  class PositionTracker:
      async def get(self, account_id, symbol) -> Position | None
      async def get_all(self, account_id) -> list[Position]
      async def apply_fill(self, fill: Fill, session: AsyncSession) -> Position    # updates qty, avg_cost, realized_pnl; emits PositionUpdated audit event
  ```
  Reads cache first (`cache/keys.position`), DB on miss; writes cache on update with TTL 1s.

- **`execution_service.py`** —
  ```python
  class ExecutionService:
      async def place_order(self, user_id, req: PlaceOrderRequest) -> Order
      async def smart_order(self, user_id, req: SmartOrderRequest) -> Order        # computes delta = target - current, places one order
      async def close_position(self, user_id, account_id, symbol) -> Order         # smart_order with target=0
      async def cancel_order(self, user_id, order_id) -> Order
      async def cancel_all(self, user_id, account_id) -> list[Order]
      async def basket_order(self, user_id, req: BasketOrderRequest) -> list[Order]
      async def modify_order(self, user_id, order_id, req: ModifyOrderRequest) -> Order
      async def list_orders(self, user_id, account_id, filters) -> list[Order]
  ```
  Each method:
  1. Wraps the body in `tracer.start_as_current_span("execution.<op>")`.
  2. Loads account, asserts user owns it.
  3. If `Account.is_paper` → routes to `PaperBroker` (see §6.5). Else routes to broker adapter.
  4. If `Strategy.requires_approval` and called from a strategy: creates `ApprovalRequest` and returns the order in status `pending_approval`.
  5. Records latency to `LatencySample` table.
  6. Records audit event in same txn.
  7. Updates `Position` via `PositionTracker.apply_fill` if fill received synchronously.
  8. Increments `orders_placed_total{broker, status}` and `order_place_duration_seconds`.

### 6.3 `app/api/rest/v1/orders.py`

```
POST   /api/v1/orders                  → place_order
POST   /api/v1/orders/smart            → smart_order
POST   /api/v1/orders/basket           → basket_order
POST   /api/v1/orders/{id}/cancel      → cancel_order
POST   /api/v1/accounts/{id}/orders/cancel-all  → cancel_all
POST   /api/v1/accounts/{id}/positions/{symbol}/close → close_position
PATCH  /api/v1/orders/{id}             → modify_order
GET    /api/v1/orders                  → list_orders
GET    /api/v1/positions               → list positions for an account
```

All require `Depends(get_current_user)`. Return Pydantic response models from `app/schemas/order.py`.

### 6.4 Approval (Action Center) endpoints — `app/api/rest/v1/approvals.py`

```
GET    /api/v1/approvals?status=pending   → list
POST   /api/v1/approvals/{id}/approve     → execute the order
POST   /api/v1/approvals/{id}/reject      → mark rejected
```

When approved, `ApprovalService.approve()` calls `ExecutionService.place_order(...)` with the saved signal payload.

### 6.5 Paper broker — `app/brokers/paper.py`

Implements `BrokerAdapter` for paper trading:
- Uses last cached price from `cache/keys.price(symbol)` as fill price.
- Simulates 50–200 ms broker latency via `await asyncio.sleep(random.uniform(0.05, 0.2))`.
- Persists virtual positions/holdings in the same DB tables (under accounts where `is_paper=True`).
- `MARKET` always fills 100%. `LIMIT` fills only if last price crosses the limit (background task checks every second).

### 6.6 Day-4 tests

- `tests/unit/test_risk_engine.py` — every check has at least 2 cases (pass + fail).
- `tests/integration/test_place_order_paper.py` — login → place paper MARKET → position appears → audit row exists.
- `tests/integration/test_smart_order.py` — target=10 from 0 places BUY 10; target=10 from 10 places nothing; target=5 from 10 places SELL 5; target=0 from 10 places SELL 10.
- `tests/integration/test_basket_order.py` — atomic mode rolls back when one fails risk.
- `tests/integration/test_approval_flow.py` — strategy with `requires_approval=true` creates pending approval; approve endpoint executes it.

### 6.7 Day-4 acceptance

- All endpoints return correct HTTP statuses.
- p95 latency for `POST /api/v1/orders` against paper broker < 100 ms (measure via `/metrics`).
- Jaeger shows full span tree: `rest.post_orders → execution.place_order → risk.validate → broker.paper.place_order → audit.record → position.apply_fill`.

---

## 7. Day 5 — Broker Adapters (5 brokers + expanded interface + master contracts + latency)

**Goal**: 5 broker adapters implementing the EXPANDED `BrokerAdapter` interface, broker factory with credential decryption, master contract sync job, broker health monitor that writes to `LatencySample`.

### 7.1 Expand `BrokerAdapter` ABC — edit `app/brokers/base.py`

Add these abstract methods to the existing class:

```python
@abstractmethod
async def search_symbols(self, query: str, exchange: Exchange | None = None) -> list[InstrumentMatch]: ...

@abstractmethod
async def get_quote(self, symbol: str, exchange: Exchange) -> Quote: ...

@abstractmethod
async def get_quotes(self, symbols: list[tuple[str, Exchange]]) -> dict[tuple[str, Exchange], Quote]: ...

@abstractmethod
async def get_depth(self, symbol: str, exchange: Exchange) -> Depth: ...   # 5-level

@abstractmethod
async def get_history(
    self, symbol: str, exchange: Exchange,
    interval: Literal["1m","5m","15m","1h","1d"],
    start: datetime, end: datetime,
) -> list[Candle]: ...

@abstractmethod
async def get_orderbook(self) -> list[BrokerOrder]: ...

@abstractmethod
async def get_tradebook(self) -> list[BrokerTrade]: ...

@abstractmethod
async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]: ...
    """Streaming iterator yielding raw broker instrument records.
    The InstrumentSyncService consumes this and upserts into `instruments`."""
```

Add the corresponding DTOs to `base.py` (`InstrumentMatch`, `Quote`, `Depth`, `BrokerOrder`, `BrokerTrade`, `InstrumentRecord`).

### 7.2 Implement 5 broker adapters

Create one module per broker — start each as a stub that raises `NotImplementedError` on broker-specific methods, with TODO comments referencing the broker's official API docs:

- **`app/brokers/zerodha.py`** — Kite Connect v3 (https://kite.trade/docs/connect/v3/). Use `httpx.AsyncClient`. Handle login token exchange + automatic refresh.
- **`app/brokers/upstox.py`** — Upstox API v2.
- **`app/brokers/dhan.py`** — Dhan API v2.
- **`app/brokers/fyers.py`** — Fyers API v3.
- **`app/brokers/five_paisa.py`** — 5paisa OpenAPI.

For THIS run, implement ONLY:
- `authenticate`, `place_order`, `cancel_order`, `get_positions`, `get_quote`, `health` for **Zerodha** (the rest can stay `NotImplementedError`).
- The other 4 brokers have full method stubs raising `NotImplementedError("TODO: <broker> – will be filled in Day 10")` so they compile and load.

Why: the adapter interface is what matters for Phase 1; full implementation comes in Day 10 of the master plan.

### 7.3 Broker factory — `app/brokers/factory.py`

```python
class BrokerFactory:
    def __init__(self, http: httpx.AsyncClient, settings: Settings): ...
    async def create(self, account: Account) -> BrokerAdapter:
        # 1. Decrypt account.api_key_encrypted, account.api_secret_encrypted via app.infrastructure.encryption
        # 2. Look up adapter class by account.broker_id (registry: dict[str, type[BrokerAdapter]])
        # 3. Instantiate, call .authenticate(creds), return
        ...
```

Singleton, injected via FastAPI `Depends`.

### 7.4 Latency-recording wrapper — `app/brokers/latency_wrapper.py`

```python
class LatencyRecordingAdapter(BrokerAdapter):
    """Decorator that wraps any BrokerAdapter and records latency to `latency_samples` table."""
    def __init__(self, inner: BrokerAdapter, recorder: LatencyRecorder): ...
    # Implement every method: time it, call inner, record (broker_id, op, latency_ms, status)
```

`BrokerFactory.create()` ALWAYS wraps the adapter in `LatencyRecordingAdapter` before returning.

### 7.5 Master contract sync — `app/data/instruments/sync_service.py`

```python
class InstrumentSyncService:
    async def sync_broker(self, broker_id: str) -> SyncResult:
        # 1. Pick any active Account for this broker_id (need creds to download).
        # 2. broker = await factory.create(account)
        # 3. records = broker.download_master_contract()
        # 4. UPSERT into `instruments` (ON CONFLICT (broker_id, symbol, exchange) DO UPDATE).
        # 5. Update `master_contract_status` row.
        # 6. Audit event "instruments.synced".
```

Schedule via APScheduler (`app/infrastructure/scheduler.py`):
- Every weekday at 08:00 IST (= 02:30 UTC) for each active broker.
- Manual trigger endpoint: `POST /api/v1/admin/instruments/sync?broker_id=zerodha`.

### 7.6 Broker health monitor — `app/brokers/health_monitor.py`

```python
class BrokerHealthMonitor:
    async def run_once(self) -> None:
        # For each active Account:
        # - broker = await factory.create(account)
        # - health = await broker.health()
        # - record latency sample (broker.health() call latency)
        # - if 3 consecutive failures: create RiskAlert(severity=Warning), set Account.is_active=False (live trading off)
        # - on recovery (1 success): clear alert, set Account.is_active=True
```

APScheduler: every 60 s.

### 7.7 Symbology / instruments REST API — `app/api/rest/v1/instruments.py`

```
GET  /api/v1/instruments/search?q=RELI&exchange=NSE&limit=20  → list of Instrument matches (cross-broker)
GET  /api/v1/instruments/{symbol}?exchange=NSE                → details
GET  /api/v1/instruments/master-status                        → list of MasterContractStatus rows
POST /api/v1/admin/instruments/sync?broker_id=zerodha         → trigger manual sync (admin only)
GET  /api/v1/calendar/holidays?exchange=NSE&year=2026         → market holidays
GET  /api/v1/calendar/sessions?exchange=NSE                   → trading sessions
GET  /api/v1/calendar/is-open?exchange=NSE                    → {open: bool, opens_at: ts | null, closes_at: ts | null}
```

### 7.8 Day-5 tests

- `tests/unit/test_broker_factory.py` — wraps adapter with latency recorder; decrypts creds.
- `tests/unit/test_latency_wrapper.py` — records sample on success and failure.
- `tests/integration/test_zerodha_mocked.py` — uses `respx` to mock Kite HTTP responses; place_order returns OrderAck.
- `tests/integration/test_health_monitor.py` — 3 consecutive failures → RiskAlert created, account deactivated.
- `tests/integration/test_instruments_search.py` — search returns expected matches.

### 7.9 Day-5 acceptance

- 5 broker modules importable; `BrokerFactory.create()` works for `zerodha` end-to-end against mocked HTTP.
- `latency_samples` rows accumulate; visible in Grafana via PromQL on `dhruva_order_place_duration_seconds`.
- Manual instrument sync against mocked Zerodha populates `instruments` table.
- `/api/v1/calendar/is-open?exchange=NSE` returns correct boolean for current UTC time.

---

## 8. Day 6 — Strategies (rule-based + ML) + Backtest + Paper mode

**Goal**: A user can register a strategy, enable it, see it generate signals on simulated candles, and run a backtest on historical data.

### 8.1 Strategy template implementations — `app/strategies/templates/`

Implement three working templates:

- **`momentum.py`** — `class MomentumStrategy(Strategy)`: BUY when 5-period EMA > 20-period EMA AND RSI(14) > 55; SELL when reverse. Use `pandas-ta` for indicators. Register as `"template.momentum.v1"`.
- **`mean_reversion.py`** — Bollinger Band reversion: BUY at lower band, SELL at upper. Register as `"template.mean_reversion.v1"`.
- **`breakout.py`** — Donchian channel: BUY on 20-bar high break, SELL on 20-bar low break. Register as `"template.breakout.v1"`.

Each `< 100 lines`. Pure logic, all data via `context`.

### 8.2 ML strategy stub — `app/strategies/ml/xgboost_signal.py`

A working `XGBoostSignalStrategy(MLStrategy)`:
- `feature_spec = FeatureSpec(features=["ret_1","ret_5","rsi_14","macd_hist"], lookback=60, timeframe="1m")`.
- `load_model(version)` reads `models/xgboost_signal/{version}/model.json` via `xgboost.Booster()`. If missing, log warning and use a `DummyModel` that always returns `Prediction(signal="HOLD", probability=0.0)` so the app still boots.
- `predict(features)` → `Prediction`.
- Registered as `"ml.xgboost_signal.v1"`.

Add training CLI under `app/strategies/ml/training/train_xgboost.py` (skeleton; full training script out of scope this run — leave a `TODO` and a docstring).

### 8.3 Strategy service — `app/core/strategy/`

- **`service.py`** — `StrategyService` with:
  - `create(account_id, name, strategy_class, parameters, mode, requires_approval, is_ml, model_version) -> Strategy`
  - `list(account_id) -> list[Strategy]`
  - `get(strategy_id) -> Strategy`
  - `enable(strategy_id) / disable(strategy_id)` (audited)
  - `delete(strategy_id)` (soft delete; audit event)
- **`executor.py`** — `StrategyExecutor`:
  - `async execute_one(strategy_id, candle: Candle) -> Signal | None`
  - Loads strategy class from `registry`, instantiates with stored parameters, calls `on_candle`.
  - If signal returned: validates via `RiskEngine`, then either calls `ExecutionService.place_order` (auto) or creates `ApprovalRequest` (semi-auto).
  - Increments `strategy_executions_total{strategy, result}` and `ml_predictions_total{model, signal}` for ML strategies.
- **`run_loop.py`** — APScheduler job that runs every 1 minute (configurable per strategy) and dispatches `executor.execute_one` for every enabled strategy.

### 8.4 Backtest engine — `app/core/strategy/backtest.py`

```python
class BacktestEngine:
    async def run(
        self,
        strategy_class: str,
        parameters: dict,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        # 1. Load OHLCV from `ohlcv_candles` for each symbol.
        # 2. Iterate candle by candle, call strategy.on_candle.
        # 3. Simulate fills at next-bar open (no lookahead).
        # 4. Compute metrics: total return, Sharpe, Sortino, Calmar, max DD, win rate, # trades.
        # 5. Persist result as a Report row + JSON artifact at `reports/backtest/{id}.json`.
        # 6. Return BacktestResult with metrics + equity curve + trade list.
```

CLI: `python -m app.scripts.backtest --strategy template.momentum.v1 --from 2024-01-01 --to 2024-12-31 --symbol RELIANCE --timeframe 5m`.

REST: `POST /api/v1/strategies/{id}/backtest` with body `{from, to, symbols, timeframe}` → returns `BacktestResult`.

### 8.5 Strategy REST API — `app/api/rest/v1/strategies.py`

```
POST   /api/v1/strategies                                 → create
GET    /api/v1/strategies?account_id=...                  → list
GET    /api/v1/strategies/{id}                            → get
PATCH  /api/v1/strategies/{id}                            → update parameters
POST   /api/v1/strategies/{id}/enable                     → enable
POST   /api/v1/strategies/{id}/disable                    → disable
DELETE /api/v1/strategies/{id}                            → soft-delete
POST   /api/v1/strategies/{id}/backtest                   → run backtest
GET    /api/v1/strategies/registry                        → list available strategy classes
```

### 8.6 Day-6 tests

- `tests/unit/test_momentum_strategy.py` — synthetic candle stream produces expected signals.
- `tests/unit/test_xgboost_signal_dummy.py` — without a model file, predict returns HOLD.
- `tests/integration/test_backtest_runs.py` — backtest on canned OHLCV completes and returns plausible metrics.
- `tests/integration/test_strategy_lifecycle.py` — create → enable → executor produces signal → ApprovalRequest created (when requires_approval=true).

### 8.7 Day-6 acceptance

- `GET /api/v1/strategies/registry` lists momentum, mean_reversion, breakout, ml.xgboost_signal.v1.
- A backtest of momentum on canned 5m RELIANCE data returns a result with all metrics non-null.
- Strategy executor scheduled and visible in logs every minute.

---

## 9. Day 6.5 — Indian Market Essentials (ChartInk + TradingView + Telegram)

**Goal**: Receive external strategy signals via webhooks and push order/position updates to Telegram.

### 9.1 ChartInk webhook — `app/api/rest/v1/webhooks/chartink.py`

```
POST /api/v1/webhooks/chartink/{secret_token}
Body: {"stocks": "RELIANCE,TCS", "trigger_prices": "2890.50,3990.00",
       "triggered_at": "...", "scan_name": "...", "scan_url": "..."}
```

Steps:
1. Look up `WebhookSource` by `secret_token` (encrypted lookup). 404 if not found or inactive.
2. Persist raw payload as `WebhookEvent`.
3. Parse: split `stocks` and `trigger_prices` by comma; create one `Signal` per stock.
4. For each signal: look up the `Strategy` linked to this `WebhookSource` (account_id stored on source); call `StrategyExecutor.execute_signal_directly(strategy, signal)`.
5. Mark event `processed`.
6. Return 200 within 1 second (process synchronously; ChartInk retries on 5xx).

### 9.2 TradingView webhook — `app/api/rest/v1/webhooks/tradingview.py`

```
POST /api/v1/webhooks/tradingview/{secret_token}
Body: free-form JSON; we standardize on:
  {"action": "BUY"|"SELL"|"CLOSE", "symbol": "RELIANCE",
   "exchange": "NSE", "quantity": 10, "price": 2890.50, "comment": "..."}
```

Same flow as ChartInk. Persist raw payload, parse into a Signal, execute.

### 9.3 Webhook management endpoints — `app/api/rest/v1/webhook_sources.py`

```
POST   /api/v1/webhook-sources                  {account_id, source, strategy_id}  → returns secret_token (one-time)
GET    /api/v1/webhook-sources?account_id=...   → list (token redacted)
DELETE /api/v1/webhook-sources/{id}             → revoke
GET    /api/v1/webhook-events?source_id=...     → list received events
```

### 9.4 Telegram bot — `app/core/notifications/telegram.py`

Use `python-telegram-bot` or implement minimal client with `httpx` (no extra dep needed; pick whichever is simpler — if adding a dep, add `python-telegram-bot>=21` to `requirements.txt` and document in README).

```python
class TelegramNotifier:
    def __init__(self, bot_token: str): ...
    async def send_text(self, chat_id: str, text: str) -> None
    async def send_order_filled(self, chat_id: str, order: Order) -> None
    async def send_risk_alert(self, chat_id: str, alert: RiskAlert) -> None
    async def send_daily_summary(self, chat_id: str, summary: DailySummary) -> None
```

Persistent listener (long-poll or webhook):
- Subscribe to commands: `/positions`, `/orders`, `/holdings`, `/pnl`, `/help`.
- Each command resolves `chat_id` → user_id via `notification_configs` and calls the relevant service.
- Inline keyboard: "Approve" / "Reject" buttons on `RiskAlert` messages and on `ApprovalRequest` notifications.

Wire emission points:
- `ExecutionService.place_order` (after fill) → `TelegramNotifier.send_order_filled` if user has a Telegram config.
- `RiskEngine` → `send_risk_alert` on every alert created.
- Daily 16:30 IST job → `send_daily_summary`.

### 9.5 Notification config endpoints

```
POST /api/v1/notifications/telegram     {chat_id}        → links Telegram chat to user
GET  /api/v1/notifications              → list current configs
DELETE /api/v1/notifications/{id}       → unlink
```

### 9.6 Day-6.5 tests

- `tests/integration/test_chartink_webhook.py` — POST sample payload → WebhookEvent persisted → Order created.
- `tests/integration/test_tradingview_webhook.py` — same.
- `tests/unit/test_telegram_message_format.py` — order-filled message has expected fields.
- `tests/integration/test_webhook_secret_rejected.py` — bad secret returns 404.

### 9.7 Day-6.5 acceptance

- POST with curl to `/api/v1/webhooks/chartink/{token}` with sample payload places a paper order.
- Telegram notifier sends a message in a test chat (set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_TEST_CHAT_ID` env vars; skip test if absent).

---

## 10. Cross-cutting fixes that span all days

These are easy to forget. Do them as you go.

1. **Argon2 swap** — `app/core/auth/password.py` uses `passlib.hash.argon2` not bcrypt.
2. **All money is `Decimal`** — never accept `float` in any DTO. Use `Decimal | str` at the API boundary if needed, validate via Pydantic v2 `field_validator`.
3. **Every service constructor takes its dependencies explicitly** (no global state). Wire via FastAPI `Depends` factories in `app/api/dependencies.py`.
4. **Every external HTTP call** uses a single shared `httpx.AsyncClient` from `app/infrastructure/http.py` (singleton, configured timeouts).
5. **APScheduler** lives at `app/infrastructure/scheduler.py`. Started in `lifespan` startup, gracefully shut down in shutdown.
6. **Update `app/db/migrations/env.py`** — uncomment the model imports as you create them, otherwise Alembic won't see the tables.
7. **Update `app/main.py`** — register every router as you add it. Order:
   ```python
   app.include_router(health.router, prefix="/health", tags=["health"])
   app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
   app.include_router(orders.router, prefix="/api/v1", tags=["orders"])
   app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
   app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
   app.include_router(instruments.router, prefix="/api/v1", tags=["instruments"])
   app.include_router(calendar.router, prefix="/api/v1/calendar", tags=["calendar"])
   app.include_router(webhooks_chartink.router, prefix="/api/v1/webhooks/chartink", tags=["webhooks"])
   app.include_router(webhooks_tv.router, prefix="/api/v1/webhooks/tradingview", tags=["webhooks"])
   app.include_router(webhook_sources.router, prefix="/api/v1/webhook-sources", tags=["webhooks"])
   app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
   ```
8. **Strategy auto-discovery** — call `app.strategies.registry.import_strategies()` in lifespan startup so all `@register_strategy` decorators run.

---

## 11. Final acceptance checklist (run before declaring done)

Run these in order; do not stop on first failure — fix all and re-run.

### Build / install
- [ ] `bash scripts/install.sh` completes on fresh repo clone (test in a fresh git worktree).
- [ ] `bash scripts/run.sh` starts uvicorn on :8000 with no exceptions in logs.
- [ ] `docker ps` shows postgres, redis, jaeger, envoy, prometheus, grafana healthy.

### Lint / types / tests
- [ ] `cd backend && ruff check .` returns 0.
- [ ] `mypy app/core app/brokers app/strategies` returns 0.
- [ ] `pytest tests/` returns 0; coverage ≥ 70% on `app/core/`.

### REST endpoints (smoke via curl)
- [ ] `POST /api/v1/auth/register` → 201
- [ ] `POST /api/v1/auth/login` → 200 with token pair
- [ ] `POST /api/v1/auth/refresh` → 200; old refresh returns 401 second time
- [ ] `GET /api/v1/auth/me` with bearer → 200
- [ ] `POST /api/v1/orders` (paper account, valid payload) → 201
- [ ] `POST /api/v1/orders/smart` → 201 with computed delta
- [ ] `POST /api/v1/orders/basket` (atomic) — 1 bad order rolls all back
- [ ] `GET /api/v1/positions?account_id=...` → contains the placed position
- [ ] `GET /api/v1/instruments/search?q=REL` → returns matches
- [ ] `GET /api/v1/calendar/is-open?exchange=NSE` → boolean
- [ ] `POST /api/v1/strategies` → 201; enable; signal generated within 1 minute
- [ ] `POST /api/v1/strategies/{id}/backtest` → result with non-null metrics
- [ ] `POST /api/v1/webhooks/chartink/{token}` (sample payload) → places order

### Observability
- [ ] Jaeger UI shows full trace for `place_order` with 6+ spans.
- [ ] `/metrics` returns text with `dhruva_orders_placed_total` > 0.
- [ ] Grafana shows non-zero data on the API Overview dashboard (provisioned from `deploy/grafana/dashboards/`).
- [ ] DB query `SELECT broker_id, operation, AVG(latency_ms) FROM latency_samples GROUP BY 1,2;` returns rows.

### Risk / compliance
- [ ] Order quantity > qty freeze → 422 with `risk_rejected:qty_freeze_exceeded`.
- [ ] Order on holiday or outside session → 422 with `risk_rejected:market_closed`.
- [ ] Order on unknown symbol → 422 with `risk_rejected:symbol_not_found`.
- [ ] Audit row exists for every successful order placement.
- [ ] Trying `UPDATE audit_events ...` in psql returns the trigger error.

### Strategy
- [ ] Strategy with `requires_approval=true` creates `ApprovalRequest`, no order placed yet.
- [ ] Approving the request places the order.
- [ ] Rejecting marks it rejected; no order placed.

---

## 12. Common pitfalls — avoid these

1. **Mixing sync and async SQLAlchemy.** Use `AsyncSession` everywhere. Don't use `session.query()`; use `await session.execute(select(...))`.
2. **Forgetting to `await`.** Linter will catch most; check `RuntimeWarning: coroutine ... was never awaited`.
3. **Float for money.** `Decimal("100.50")`, not `100.50`. Pydantic v2: `Annotated[Decimal, Field(decimal_places=4)]`.
4. **Hardcoding cache keys** — always use `app/cache/keys.py`.
5. **Logging plaintext credentials or JWT tokens.** Never. Audit log `new_value_jsonb` must scrub these fields.
6. **Audit not in same transaction.** If the order write succeeds but audit fails, you have unauditable state. Pass the same `AsyncSession` and let the outer `commit()` handle both.
7. **Background jobs holding DB sessions across `await`s.** Always `async with SessionLocal() as session:` per job invocation.
8. **APScheduler running before lifespan startup.** Start it inside `lifespan()`, not at import time.
9. **Master contract sync running at import time.** It should be a scheduled job, not at startup. Startup should only verify the most recent sync is < 24h old and log a warning if stale.
10. **Forgetting `op.execute("CREATE EXTENSION timescaledb")`** in the first migration — hypertables fail otherwise.
11. **Using the same Redis DB for cache and rate-limit token buckets** — fine, but use different key prefixes (already enforced via `cache/keys.py`).
12. **Leaving `NotImplementedError` adapters unwrapped in tests** — mark integration tests for the 4 unfilled brokers with `pytest.mark.skip(reason="adapter stub — Day 10")`.
13. **Forgetting Argon2 dependency** — add `argon2-cffi>=23.1` to `requirements.txt` and run `pip install -r requirements.txt` after editing.
14. **Not registering routers in `main.py`** — Swagger will be empty; remember §10.7.
15. **Running tests against the dev DB.** Use a separate test DB (`dhruva_test`) and a `pytest` fixture that creates/drops it. Never run tests against `dhruva`.

---

## 13. What is OUT OF SCOPE for this run

Do NOT implement (these are later phases):

- Frontend React work (Phase 4).
- Portfolio analytics service (Sharpe/Sortino/Calmar) — that's Phase 2 Day 8.
- Reports (PDF/Excel) — Phase 2 Day 11.
- Scanner module — Phase 2 Day 12.
- gRPC servicers — Phase 3 Day 13. (The proto contracts already exist; you can generate stubs but don't implement servicers.)
- WebSocket hub for streaming prices — Phase 3 Day 14.
- 4 of the 5 broker adapter implementations (Upstox/Dhan/Fyers/5Paisa) — only Zerodha needs to work end-to-end this run; the others are stubbed.
- ML training scripts (the model loading + predict path must work; the actual training CLI is a stub with a TODO).
- Visual Strategy Builder, Options analytics, Excel/Sheets, MCP server — all out of scope.

---

## 14. Reference documents

In the repo:
- **`docs/prompts/DHRUVA_Python_React_Master_Prompt.md`** — full design (architecture, stack, repo layout, Phase 4-5 frontend spec). Use as authoritative reference for anything not explicitly covered above.
- `backend/app/strategies/ml/README.md` — ML strategy plugin contract (must be respected exactly).
- `proto/dhruva/v1/*.proto` — gRPC contracts; the REST DTOs above must be wire-compatible (same field names where possible) with these proto messages.
- `backend/README.md` — backend quick-start.

External (read before implementing the relevant section):
- Zerodha Kite Connect v3: https://kite.trade/docs/connect/v3/
- ChartInk webhook docs: https://chartink.com/articles/help/webhook-alerts
- TradingView webhook docs: https://www.tradingview.com/support/solutions/43000529348-webhooks/
- TimescaleDB hypertables: https://docs.timescale.com/use-timescale/latest/hypertables/
- structlog: https://www.structlog.org/
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- python-telegram-bot v21: https://docs.python-telegram-bot.org/

---

## 15. How to deliver

When done:

1. All checks in §11 pass.
2. Commit in logical chunks per Day (one commit per Day, message format: `feat(phase1): Day N — <summary>`).
3. Update `backend/README.md` with any new env vars introduced.
4. Update root `README.md` "Status" section to show Phase 1 done.
5. Open a PR titled `Phase 1 + Indian Market Essentials` with the §11 checklist in the description, ticked.

**Do not skip §11 items.** If you cannot complete one, add a `// FIXME(phase1):` comment in the relevant file and call it out explicitly in the PR description.

---

**Begin with Day 1 (§3). Implement strictly in order — each day depends on the previous.**
