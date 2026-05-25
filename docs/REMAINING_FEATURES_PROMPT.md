# Remaining-Features Implementation Prompt

Paste the body of this file into a fresh Claude session inside the DRUVA repo
(`/Users/ninadk/PycharmProjects/DRUVA`). It is self-contained — no prior
session context required.

---

## Project context (read first)

You are working in **DRUVA** (folder name: `DRUVA`, brand spelt *DHRUVA*) —
a production Indian-markets algo-trading platform.

* Backend: Python 3.12 + FastAPI + APScheduler + SQLAlchemy async + Postgres
  + Redis. Settings load from env vars prefixed `DHRUVA_`
  (`backend/app/config.py`).
* Frontend: React 18 + Vite + TanStack Router. Sidebar entries in
  `frontend/src/components/layout/Sidebar.tsx`, routes in
  `frontend/src/routes/router.tsx`.
* All new logger calls use `from app.infrastructure.logging import get_logger`.
* All new REST routes mount under `/api/v1/<name>` from
  `backend/app/main.py` and depend on `get_current_user` from
  `app.core.auth.dependencies`.
* Test runner sandbox (no project venv on this machine):

  ```bash
  cd backend
  PYTHONPATH=. uv run --no-project --python 3.12 \
    --with pytest --with pytest-asyncio --with pytest-cov \
    --with pydantic --with pydantic-settings --with numpy \
    --with structlog --with httpx --with sqlalchemy \
    --with anthropic --with openai \
    pytest <test paths> -q --no-header --no-cov
  ```

  Add `--with pandas`, `--with pandas-ta`, `--with scikit-learn`,
  `--with feedparser`, `--with optuna` to that command as new phases need
  them.

## What's already done in the previous session

These files exist and are tested — **do not rewrite them**:

* `backend/app/core/advisor/personas/` — Buffett, Munger, Lynch, Damodaran,
  Jhunjhunwala, Burry, Druckenmiller personas + `base.py` registry.
* `backend/app/core/advisor/council.py` — Council orchestrator.
* `backend/app/core/advisor/signal_aggregator.py` — multi-agent signal fuse.
* `backend/app/core/advisor/valuation/` — `fundamentals_provider.py`
  (Null/Static/Repository/HTTP impls + `build_provider` factory) and
  `dcf.py` (three-stage DCF).
* `backend/app/core/risk/correlation_sizer.py` — vol-bucket + correlation
  multiplier sizer.
* `backend/app/core/risk/protections/` — `base.py`, `cooldown.py`,
  `stoploss_guard.py`, `max_drawdown.py`, `low_profit_pairs.py`,
  `__init__.py`. **`manager.py` is referenced by `__init__.py` but does
  NOT yet exist** — first task below.
* `backend/app/strategies/optimization/` — `losses.py`, `hyperopt.py`
  (Optuna with random fallback), `lookahead.py`, `monte_carlo.py`,
  `__init__.py`.
* `backend/app/api/rest/v1/council.py` — `GET /personas`,
  `POST /ask-as/{slug}`, `POST /council`, `POST /dcf`,
  `POST /risk/correlation-sizing`, `GET /risk/buckets`.
* `frontend/src/features/council/` — `CouncilPanel.tsx`, `CouncilPage.tsx`.
* `NOTICES.md` already attributes ai-hedge-fund (MIT), Jesse (MIT),
  Freqtrade (GPL-3.0).
* `backend/app/config.py` already has
  `fundamentals_provider`, `fundamentals_http_base_url`,
  `fundamentals_http_api_key`, `fundamentals_http_timeout_s`.

## What's left to implement

Build in order — later phases reuse code from earlier ones.

---

### 0. Finish `ProtectionManager` (unblocks F2 imports)

**File:** `backend/app/core/risk/protections/manager.py`

```
- ProtectionManager(protections: list[Protection])
    - method: should_block(symbol, now, recent_trades, portfolio_state) -> ProtectionDecision
        Iterate every protection. Return the first .blocked=True decision found
        (symbol-scope overrides nothing; global-scope blocks everything).
        If all return allow(), return ProtectionDecision.allow().
    - method: snapshot() -> list[dict[str, Any]]
        Return [{"name": p.name, "type": type(p).__name__} for p in protections]
        for the admin UI.

- build_manager_from_config(config: list[dict[str, Any]]) -> ProtectionManager
    Each dict has a "type" key naming one of:
      "CooldownPeriod" | "StoplossGuard" | "MaxDrawdownProtection" | "LowProfitPairs"
    Remaining keys are passed to the protection's constructor. Unknown types
    log a warning and are skipped (never raise).
```

**Tests** (`backend/tests/unit/core/risk/protections/test_protections.py`):
- CooldownPeriod blocks until window elapses, then allows.
- StoplossGuard global block triggers after N stoploss hits in lookback.
- StoplossGuard per-symbol mode only blocks the affected symbol.
- MaxDrawdownProtection triggers at threshold, allows below.
- LowProfitPairs requires at least `required_trades` before triggering.
- ProtectionManager returns the *first* blocking decision and ignores
  later protections.
- build_manager_from_config skips unknown types without raising.

Add `__init__.py` files in any new test directories (`tests/unit/core/risk/protections/__init__.py`).

---

### F3. Universe / pair-list filter chain

**Directory:** `backend/app/core/scanner/filters/`

Pattern (re-implemented from Freqtrade docs — GPL-3.0, do **not** copy code
verbatim, design from scratch):

```python
# base.py
@dataclass(frozen=True)
class SymbolMetrics:
    symbol: str
    exchange: str = "NSE"
    avg_volume_inr: float | None = None     # 30-day avg
    last_price: float | None = None
    atr_pct: float | None = None             # 14d ATR / price
    listed_days: int | None = None
    lot_size: int | None = None
    market_cap_inr: float | None = None

class UniverseFilter(Protocol):
    name: str
    def keep(self, m: SymbolMetrics) -> bool: ...
```

**Concrete filters** (each in its own module: `volume.py`, `price.py`,
`range_stability.py`, `age.py`, `precision.py`):

| Filter | Defaults |
|---|---|
| `VolumeFilter(min_avg_volume_inr)` | min 1e8 (₹10cr daily turnover) |
| `PriceFilter(min_price, max_price)` | 50 ≤ p ≤ 50_000 |
| `RangeStabilityFilter(max_atr_pct)` | atr_pct ≤ 0.08 (8%) |
| `AgeFilter(min_listed_days)` | 365 |
| `PrecisionFilter(min_lot_size, max_lot_size)` | 1 ≤ lot ≤ 5000 |

Each filter returns `False` when the metric is missing (conservative drop).

**Pipeline** (`pipeline.py`):

```python
class FilterPipeline:
    def __init__(self, filters: list[UniverseFilter]): ...
    def apply(self, symbols: Iterable[SymbolMetrics]) -> list[SymbolMetrics]: ...
    def explain(self, m: SymbolMetrics) -> list[tuple[str, bool]]: ...
    @classmethod
    def from_config(cls, cfg: list[dict]) -> "FilterPipeline":
        # cfg: [{"type": "VolumeFilter", "min_avg_volume_inr": 1e8}, ...]
```

**REST endpoint** in `backend/app/api/rest/v1/scanners.py`
(extend, don't replace):

* `POST /api/v1/scanners/universe-filter` — body
  `{ "metrics": [SymbolMetrics-dict...], "pipeline": [...] }` returns
  `{"kept": [...], "dropped": [{symbol, failed_at}]}`.

**Tests** (`backend/tests/unit/core/scanner/test_universe_filters.py`):
- Each filter passes/fails correctly with edge cases (None → drop).
- Pipeline runs filters in declared order; explain() returns ordered results.
- from_config skips unknown filter types and logs a warning.

---

### H. Economic + corporate calendar provider

**Directory:** `backend/app/data/calendar/`

Mirror the fundamentals-provider pattern that already exists in
`backend/app/core/advisor/valuation/fundamentals_provider.py` — read it
once before starting.

```python
# models.py
EventKind = Literal[
    "rbi_policy", "earnings", "dividend_ex_date", "bonus", "split",
    "agm", "fno_expiry", "index_rebalance", "ipo", "buyback",
    "result_announcement", "circuit_filter_change",
]

@dataclass(frozen=True)
class CalendarEvent:
    event_id: str            # stable hash
    kind: EventKind
    occurs_on: date
    symbol: str | None       # None for macro events (RBI policy)
    exchange: str | None     # "NSE" | "BSE" | None
    title: str
    detail: str = ""
    source: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
```

```python
# provider.py
class CalendarProvider(Protocol):
    name: str
    async def fetch(
        self, *, since: date, until: date,
        symbol: str | None = None, kinds: list[EventKind] | None = None,
    ) -> list[CalendarEvent]: ...

class NullCalendarProvider:
    name = "null"; async def fetch(self, **_): return []

class StaticCalendarProvider:
    name = "static"
    def __init__(self, events: list[CalendarEvent]): ...
    async def fetch(self, **filters): # respect since/until/symbol/kinds

class HTTPCalendarProvider:
    """GET {base_url}/events?since=YYYY-MM-DD&until=YYYY-MM-DD&symbol=...&kinds=...
    Returns JSON list of CalendarEvent payloads."""

def build_provider(*, kind=None, base_url=None, api_key=None, timeout_s=None,
                   static_events=None) -> CalendarProvider:
    """Reads DHRUVA_CALENDAR_* env vars / Settings fields, same pattern as
    fundamentals_provider.build_provider()."""
```

**Settings additions** in `backend/app/config.py` (after the fundamentals block):

```python
calendar_provider: Literal["http", "static", "null"] = "null"
calendar_http_base_url: str = ""
calendar_http_api_key: str = ""
calendar_http_timeout_s: float = 15.0
```

**REST endpoint** — new file `backend/app/api/rest/v1/calendar.py`:

* `GET /api/v1/calendar/events?since=...&until=...&symbol=...&kinds=...`

Mount it in `backend/app/main.py` next to the existing
`include_router(council.router, ...)` line:

```python
app.include_router(calendar.router, prefix="/api/v1/calendar", tags=["calendar"])
```

Add `calendar` to the import block.

**Tests** (`backend/tests/unit/data/calendar/test_provider.py`):
- StaticCalendarProvider respects since/until/symbol/kinds filters.
- build_provider("null") works.
- build_provider("http") without base_url returns NullCalendarProvider.
- build_provider("http") with mock httpx parses a sample payload correctly.

---

### I. News aggregator + LLM sentiment

**Directory:** `backend/app/data/news/`

```python
# feeds.py — registry of RSS feeds.
@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    category: str            # "indian_markets" | "global" | "company_filings"
    weight: float = 1.0

DEFAULT_FEEDS = [
    FeedSource("Mint Markets",  "https://www.livemint.com/rss/markets",       "indian_markets"),
    FeedSource("ET Markets",    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "indian_markets"),
    FeedSource("Moneycontrol",  "https://www.moneycontrol.com/rss/marketreports.xml", "indian_markets"),
    FeedSource("Reuters India", "https://www.reutersagency.com/feed/?best-regions=india&post_type=best", "global"),
    FeedSource("BSE filings",   "https://www.bseindia.com/data/xml/notices.xml", "company_filings"),
]
```

```python
# aggregator.py
@dataclass(frozen=True)
class NewsItem:
    item_id: str             # sha1 of URL
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime
    symbols: list[str] = field(default_factory=list)
    sentiment_score: float | None = None     # -1..+1
    sentiment_label: str | None = None       # "negative"/"neutral"/"positive"

class NewsAggregator:
    def __init__(self, feeds: list[FeedSource] = DEFAULT_FEEDS, *,
                 http: httpx.AsyncClient | None = None): ...
    async def poll(self) -> list[NewsItem]:
        """Fetch each feed concurrently with feedparser; dedupe by sha1(url)."""
    @staticmethod
    def extract_symbols(text: str, universe: set[str]) -> list[str]:
        """Naive: uppercase word-boundary match against the NSE universe."""
```

```python
# sentiment.py
class NewsSentimentScorer:
    def __init__(self, advisor: "PortfolioAdvisor | None" = None): ...
    async def score(self, item: NewsItem) -> NewsItem:
        """Calls advisor with a tight prompt: returns -1..+1; degrades to 0.0
        if no advisor configured."""
    async def score_batch(self, items: list[NewsItem]) -> list[NewsItem]:
        """Asyncio.gather over .score()."""
```

```python
# backend/app/db/models/news.py
class NewsItemRow(Base, TimestampMixin):
    __tablename__ = "news_items"
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title, summary, url, source, published_at, sentiment_score,
    sentiment_label, symbols_jsonb (JSON), raw_jsonb (JSON)
```

**REST endpoint** — `backend/app/api/rest/v1/news.py`:

* `GET /api/v1/news/latest?limit=50&symbol=...&since=...`
* `POST /api/v1/news/refresh` — admin-only background task that polls all
  feeds and scores sentiment.

Mount in `main.py`.

**Settings additions:**

```python
news_aggregator_enabled: bool = True
news_refresh_cron_utc_hour: int = 1
news_refresh_cron_utc_minute: int = 30
news_sentiment_model: Literal["llm", "none"] = "llm"
```

Add a daily refresh job in `backend/app/infrastructure/jobs.py`.

**Tests** (`backend/tests/unit/data/news/test_aggregator.py`):
- Aggregator dedupes the same URL across two feeds.
- Symbol extraction matches case-insensitive tokens against a NIFTY-50 set.
- Sentiment scorer with no advisor returns 0.0 / "neutral".
- Sentiment scorer with a fake advisor parses scores out of valid LLM responses
  and degrades gracefully on malformed JSON.

Dependency: `feedparser` — add to `backend/requirements.txt`.

---

### J. Four more personas + three broker adapter stubs

**Personas** (one file each in `backend/app/core/advisor/personas/`):

* `graham.py` — Benjamin Graham. NCAV, Mr. Market, 50/50 stocks-bonds anchor,
  P/E ≤ 15, P/B ≤ 1.5, current ratio ≥ 2, positive earnings for 10y.
  Indian adaptation: include caveat that NCAV opportunities are very rare in
  India and require careful balance-sheet scrubbing.
* `klarman.py` — Seth Klarman. Margin of safety above all, special situations,
  spin-offs, distressed debt. Indian adaptation: PSU divestments, demerger
  arbitrage.
* `marks.py` — Howard Marks. Second-level thinking, market cycles, risk =
  probability of permanent loss, contrarian timing. Indian adaptation: NIFTY
  P/E percentile, FII risk-on/risk-off cycles.
* `rajan.py` — Raghuram Rajan (macro persona, original to DRUVA). RBI policy
  framework, inflation targeting, twin-balance-sheet problem, capital flows.
  Trade in macro view, not individual stocks — typically opines on
  rate-sensitives (banks, NBFCs) and currency-sensitives (IT, pharma).

Each persona follows the same dataclass shape used in the existing
`buffett.py` — `Persona(slug=, display_name=, style=, system_prompt=,
checklist=)` — and gets registered in
`backend/app/core/advisor/personas/__init__.py` via `register_persona()`.

Update the existing
`backend/tests/unit/core/advisor/test_personas.py` to include the four new
slugs in `EXPECTED_SLUGS` and the import list.

**Broker adapters** (each in `backend/app/brokers/`):

* `angel_one.py` — Angel One SmartAPI (TOTP login flow).
* `groww.py`    — Groww (recent public API).
* `alice_blue.py` — AliceBlue Ant API.

Each adapter subclasses `BrokerAdapter` from `app/brokers/base.py`. Read
`app/brokers/zerodha.py` for the reference implementation pattern. For this
phase, ship **stubs** that:

1. Implement the full method surface (`authenticate`, `place_order`,
   `cancel_order`, `get_positions`, `get_holdings`, `quote`,
   `historical_candles`, `websocket_ticks`).
2. Raise `NotImplementedError("...waiting on credentials...")` from each
   network method.
3. Successfully construct from a credentials dict and pass `BrokerFactory`
   smoke tests.
4. Are registered in `backend/app/brokers/factory.py` so they appear in the
   admin UI as available but not configured.

**Tests** (`backend/tests/unit/brokers/test_new_adapters.py`):
- Each adapter constructs with valid credentials.
- Each adapter has the full BrokerAdapter method surface.
- Each adapter raises NotImplementedError on network methods with a clear
  message that mentions the broker name.

---

### K. Indicator library (Jesse-style)

**Directory:** `backend/app/strategies/indicators/library/`

Goal: a single unified `IndicatorRegistry` that exposes 60+ indicators with
a consistent call signature `(close: ndarray, **params) -> ndarray` for
single-series indicators and
`(high, low, close, volume, **params) -> ndarray` for multi-series ones.

**Implementation strategy** (do not write 300 files):

```python
# registry.py
@dataclass(frozen=True)
class IndicatorMeta:
    name: str
    category: str    # "momentum" | "trend" | "volatility" | "volume" | "overlap" | "pattern" | "statistical" | "cycle"
    inputs: tuple[str, ...]   # ("close",), ("high","low","close"), etc.
    params: dict[str, type]   # {"period": int, "std": float}
    backend: str              # "native" | "pandas_ta" | "talib"
    fn: Callable

class IndicatorRegistry:
    def register(self, meta: IndicatorMeta) -> None: ...
    def get(self, name: str) -> IndicatorMeta: ...
    def list(self) -> list[IndicatorMeta]: ...
    def compute(self, name: str, **inputs) -> np.ndarray: ...
```

**Native implementations** (`native.py`, pure numpy — no extra deps):

Write at least these 50 indicators with full unit tests:

| Category | Indicators |
|---|---|
| Trend | SMA, EMA, WMA, DEMA, TEMA, KAMA, HMA, VWMA, ALMA, T3 |
| Momentum | RSI, ROC, ROCP, ROCR, MOM, TRIX, CMO, WILLR, ULTOSC, STOCH, STOCHRSI, MFI, CCI, AROON, AROONOSC, DX, ADX, ADXR |
| Volatility | ATR, NATR, TRANGE, BBANDS, KELTNER, DONCHIAN, STDDEV, VAR |
| Volume | OBV, VWAP (session-anchored), AD, ADOSC, CMF, EFI, PVT |
| Overlap | MIDPOINT, MIDPRICE, SAR, MAMA |
| Pattern (binary) | DOJI, HAMMER, ENGULFING, MORNINGSTAR, EVENINGSTAR |

**Bridge** (`pandas_ta_bridge.py`):

```python
def register_pandas_ta(registry: IndicatorRegistry) -> int:
    """Walk pandas_ta and register every public indicator not already
    present (skip duplicates by name). Returns count added."""
```

If `pandas_ta` import fails, log a warning and return 0 — *do not raise*.

**Top-level `__init__.py`**:

```python
_default = IndicatorRegistry()
# populate native indicators
_register_natives(_default)
# augment with pandas_ta
register_pandas_ta(_default)

def get_registry() -> IndicatorRegistry: return _default
```

**REST endpoints** — extend `backend/app/api/rest/v1/strategies.py`:

* `GET /api/v1/strategies/indicators` → list all available
  `{name, category, backend, inputs, params}`
* `POST /api/v1/strategies/indicators/{name}/compute` → body
  `{"close":[...], "high":[...], ...}` returns the computed series.

**Tests** (`backend/tests/unit/strategies/indicators/`):
- One test per native indicator validating numeric output against a known
  pre-computed value (5-bar synthetic series).
- Test that registry.list() returns ≥ 50 entries when pandas_ta is absent
  and ≥ 100 when present.
- Test compute("RSI", close=...) end-to-end.

Add `pandas` and `pandas-ta` to `requirements.txt`.

---

### L. FreqAI-style adaptive ML pipeline

**Directory:** `backend/app/strategies/ml/freq_ai/`

Reimplement (do not copy — Freqtrade is GPL-3.0). The contract:

```python
# feature_engineering.py
class FeatureKitchen:
    """Turns raw OHLCV into a feature matrix.

    Built-ins (toggle each via config):
      - rolling returns at multiple lookbacks
      - normalized indicator outputs (RSI, ATR, EFI, BBands width)
      - day-of-week + hour-of-day one-hots
      - regime-encoded sentiment score (re-uses DRUVA SentimentEngine output)
    """
    def __init__(self, config: FeatureConfig): ...
    def transform(self, ohlcv: pd.DataFrame, *, sentiment: float | None = None) -> pd.DataFrame: ...
    @property
    def feature_names(self) -> list[str]: ...
```

```python
# data_kitchen.py
@dataclass
class TrainEvalSplit:
    X_train, y_train, X_eval, y_eval, scaler

class DataKitchen:
    def __init__(self, *, train_pct=0.8, scaler="standard", use_pca=False, n_components: int | None = None): ...
    def split(self, features: pd.DataFrame, target: pd.Series) -> TrainEvalSplit: ...
```

```python
# models.py
class FreqAIModel(ABC):
    name: str
    def fit(self, split: TrainEvalSplit) -> dict[str, float]: ...
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...
    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path) -> "FreqAIModel": ...

class LightGBMRegressor(FreqAIModel): name = "lgbm_reg"
class LightGBMClassifier(FreqAIModel): name = "lgbm_clf"
class SklearnRandomForest(FreqAIModel): name = "rf_reg"
```

If lightgbm is unavailable, fall back to sklearn.ensemble.GradientBoosting*
with a warning.

```python
# pipeline.py
class FreqAIPipeline:
    """Adaptive retrain orchestrator.

    Per call to .step(now, latest_ohlcv, sentiment):
      1. If retrain interval elapsed -> rebuild features, refit model,
         persist new weights.
      2. Otherwise just transform the latest features and predict.
    """
    def __init__(self, *, model: FreqAIModel, kitchen: FeatureKitchen,
                 data_kitchen: DataKitchen, retrain_every: timedelta,
                 storage_dir: Path): ...
    async def step(self, *, now: datetime, ohlcv: pd.DataFrame,
                   sentiment: float | None = None) -> FreqAIPrediction: ...
```

```python
# strategy.py
class FreqAIStrategy(Strategy):
    """Drop-in Strategy that consumes FreqAIPipeline predictions.

    Behaviour gated by:
      DHRUVA_FREQAI_ENABLED=true   -> this strategy participates
      DHRUVA_FREQAI_MODE="signal"  -> emit BUY/SELL when prediction crosses thresholds
      DHRUVA_FREQAI_MODE="size"    -> always pass-through HMM signal, but scale qty by prediction
    """
```

**Co-existence with HMM Regime Trader**: don't touch the existing
`regime_trader/` package. The FreqAI strategy is *additional*, gated by
`freqai_enabled`. When both are enabled, the SignalAggregator combines them.

**Settings** in `config.py`:

```python
freqai_enabled: bool = False
freqai_mode: Literal["signal", "size", "shadow"] = "shadow"
freqai_model: Literal["lgbm_reg", "lgbm_clf", "rf_reg"] = "lgbm_reg"
freqai_retrain_hours: int = 24
freqai_train_pct: float = 0.8
freqai_storage_dir: str = "data/freqai/"
```

**Background job** in `infrastructure/jobs.py`:

```python
if settings.freqai_enabled:
    scheduler.add_job(freqai_retrain_job, "interval",
                      hours=settings.freqai_retrain_hours,
                      id="freqai_retrain")
```

**REST endpoints** in a new `backend/app/api/rest/v1/freqai.py`:

* `GET  /api/v1/freqai/status` — current model, last retrain, accuracy.
* `POST /api/v1/freqai/retrain` — trigger a retrain background task.
* `POST /api/v1/freqai/predict` — body `{symbol, candles[]}` → prediction.

**Tests** (`backend/tests/unit/strategies/ml/freq_ai/`):
- FeatureKitchen produces stable feature_names.
- DataKitchen split returns matching shapes; scaler is fitted on train only.
- Model fit→predict→save→load round-trip works (use sklearn fallback in
  test sandbox).
- Pipeline.step retrains exactly when interval has elapsed.
- FreqAIStrategy.on_candle with mode="signal" emits BUY when prediction
  ≥ buy threshold; HOLD otherwise.

Add `scikit-learn` to requirements; `lightgbm` optional.

---

### Final wiring

After all phases compile:

1. **Update `backend/app/main.py`** — add to the import block:
   ```python
   from app.api.rest.v1 import calendar, freqai, news
   ```
   and add the includes:
   ```python
   app.include_router(calendar.router, prefix="/api/v1/calendar", tags=["calendar"])
   app.include_router(news.router,     prefix="/api/v1/news",     tags=["news"])
   app.include_router(freqai.router,   prefix="/api/v1/freqai",   tags=["freqai"])
   ```

2. **Update `backend/.env.example`** — append blocks documenting:
   - DHRUVA_CALENDAR_*
   - DHRUVA_NEWS_*
   - DHRUVA_FREQAI_*

3. **Update `NOTICES.md`** — extend the existing Jesse and Freqtrade sections
   to mention the new modules (`indicators/library/native.py`,
   `strategies/ml/freq_ai/`, `core/scanner/filters/`,
   `app/data/calendar/`, `app/data/news/`). Add a Fincept attribution
   noting the macro/geopolitics persona inspiration (Rajan persona).

4. **Update `frontend/src/components/layout/Sidebar.tsx`** + add minimal
   pages for any features that warrant a UI:
   - Calendar — table of upcoming events grouped by date.
   - News — feed list with sentiment badges + symbol filter.
   - FreqAI — small status panel with last retrain time + last accuracy.

5. **Run the full pytest suite** with the sandbox command at the top of
   this prompt. Acceptance: all new tests pass and no previously-passing
   test breaks.

6. **Self-check before declaring done:**
   - `grep -R "TODO\|FIXME" backend/app/core/risk/protections backend/app/core/scanner/filters backend/app/strategies/optimization backend/app/strategies/indicators/library backend/app/strategies/ml/freq_ai backend/app/data/calendar backend/app/data/news` — must be empty.
   - Every new module has a one-paragraph docstring at the top explaining
     intent and pointing at the source repo + license it adapts from.
   - No verbatim copies from Freqtrade / OpenBB / Fincept (the GPL/AGPL/BSL
     repos) — patterns only. Verbatim Jesse adaptation is fine, attribute it.

---

## Coding conventions (match the existing codebase)

- Async functions everywhere data crosses I/O boundaries.
- Dataclasses with `frozen=True` for value types; mutable dataclasses only
  for collectors/managers.
- `from __future__ import annotations` at the top of every new module.
- No inline `pass` for ABCs — use `...` and `@abstractmethod`.
- Pydantic models for request/response schemas; **never** mix Pydantic and
  dataclasses in the same response shape.
- Use the `Settings.<field>` pattern from `app.config.get_settings()` — never
  read `os.environ` directly from feature code.
- Logger calls use structured kwargs: `logger.info("evt.name", key=value)`.

## When stuck

If a referenced module doesn't exist or behaves differently from this
prompt, **do not invent compatibility shims**. Read the actual code at the
referenced path and report the divergence in your final message before
proceeding.
