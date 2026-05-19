# DRUVA — Pending Work Tracker

Last updated: 2026-05-19

---

## P1 — Frontend Navigation (quick wiring, 1-2 hours)

These components are fully built but not yet linked in the sidebar / route tree.

| Component | File | Where to add |
|-----------|------|--------------|
| AI Advisor chat panel | `frontend/src/features/ai-advisor/AiAdvisorPanel.tsx` | Sidebar nav + `/ai-advisor` route |
| Greeks Dashboard widget | `frontend/src/features/options/GreeksDashboard.tsx` | Options page or dashboard tab |

**Steps:**
1. Add routes in `frontend/src/app/routes.tsx` (or equivalent router file).
2. Add sidebar menu entries (icon + label) in the nav component.
3. Wire `AiAdvisorPanel` to `GET /api/v1/ai-advisor/sentiment` on mount for initial data.

---

## P2 — Environment / Config (before first live run)

| Variable | Purpose | Where |
|----------|---------|-------|
| `ANTHROPIC_API_KEY` | Claude AI advisor (preferred LLM) | `backend/.env` |
| `OPENAI_API_KEY` | GPT-4o fallback if no Anthropic key | `backend/.env` |
| `DRUVA_SMTP_HOST` | Email alerts (order fills, circuit breakers) | `backend/.env` |
| `DRUVA_SMTP_PORT` | SMTP port (usually 587 TLS or 465 SSL) | `backend/.env` |
| `DRUVA_SMTP_USER` | SMTP login username | `backend/.env` |
| `DRUVA_SMTP_PASS` | SMTP login password | `backend/.env` |
| `DRUVA_SMTP_FROM` | Sender address shown in alerts | `backend/.env` |
| `regime_trader_enabled` | Activates daily HMM bar job | Settings / `backend/.env` |
| `rebalance_enabled` | Activates drift-check cron | Settings / `backend/.env` |
| `regime_alert_chat_id` | Telegram chat for circuit-breaker alerts | Settings / `backend/.env` |
| `regime_alert_emails` | Email list for circuit-breaker alerts | Settings / `backend/.env` |

---

## P3 — Walk-Forward Backtester (Phase 5 of regime-trader roadmap)

**Goal:** Validate the HMM model on out-of-sample data using a rolling train/eval window.

- Train window: 252 trading days (~1 year)
- Eval window: 126 trading days (~6 months)
- Roll forward 21 days per iteration (monthly)
- Metrics: Sharpe, max drawdown, regime detection latency
- Benchmarks: Buy & Hold, SMA-200, Random Entry
- Crash injection: randomly inject 10–15% price drops; measure bars-to-detection

**Files to create:**
- `backend/app/strategies/ml/regime_trader/backtester/walk_forward.py`
- `backend/app/strategies/ml/regime_trader/backtester/crash_injector.py`
- `backend/app/strategies/ml/regime_trader/backtester/metrics.py`
- `backend/scripts/run_walk_forward.py` (CLI entrypoint)

**Entry point:**
```bash
cd backend
python scripts/run_walk_forward.py --data data/nifty50_2020_2026.csv \
  --train-window 252 --eval-window 126 --output results/walk_forward/
```

---

## P4 — WhatsApp Approval Flow

**Goal:** Alternative approval channel to Telegram for portfolio managers who prefer WhatsApp.

- Provider: Twilio WhatsApp API (or Meta Cloud API)
- Trigger: Approval requests for large orders, rebalance plans, regime-driven trades
- Flow: DRUVA sends WhatsApp message with order details → manager replies "APPROVE" / "REJECT"
- Timeout: 15 minutes (same as Telegram TTL)

**Files to create:**
- `backend/app/core/notifications/whatsapp.py` — `WhatsAppNotifier` class
- Wire into `ApprovalService` alongside `TelegramNotifier`
- Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` env vars

---

## P5 — VaR / CVaR Portfolio Risk Dashboard

**Goal:** Show portfolio-level Value at Risk and Conditional VaR (Expected Shortfall).

**Calculations:**
- Historical VaR (95%, 99%) using 252-day rolling returns
- CVaR (Expected Shortfall) at 95%
- Per-position contribution to portfolio VaR
- Sector-level VaR concentration

**Files to create:**
- `backend/app/core/risk/var_engine.py` — Historical + parametric VaR/CVaR
- `backend/app/api/rest/v1/risk.py` — REST endpoint `GET /api/v1/risk/var`
- `frontend/src/features/risk/VaRDashboard.tsx` — VaR gauge + contribution chart

---

## P6 — Monte Carlo Goal Projection

**Goal:** Simulate 1000+ portfolio paths to show probability of reaching a savings/corpus goal.

**Inputs:** current portfolio value, monthly SIP amount, target corpus, time horizon (years)
**Output:** probability distribution of final portfolio value, P10/P50/P90 outcomes

**Files to create:**
- `backend/app/core/portfolio/monte_carlo.py` — simulation engine (NumPy-based)
- `backend/app/api/rest/v1/goals.py` — add `POST /api/v1/goals/{id}/simulate` endpoint
- `frontend/src/features/goals/MonteCarloChart.tsx` — fan chart (Recharts)

---

## P7 — Mobile PWA Shell

**Goal:** Make DRUVA accessible as a Progressive Web App on iOS/Android.

**Steps:**
1. Add `frontend/public/manifest.json` with DRUVA branding (name, icons, theme_color)
2. Register a service worker (`frontend/src/sw.ts`) for offline caching of static assets
3. Add `<meta name="viewport">` and Apple Touch icon tags in `index.html`
4. Test "Add to Home Screen" on Chrome Android and Safari iOS

**Nice-to-have:** Push notifications for circuit-breaker alerts via Web Push API.

---

## P8 — HMM Model Retrain Schedule

**Goal:** Keep the regime detector current as market conditions evolve.

**Options:**
- **Weekly retrain** (recommended): every Sunday, fetch last 5 years of NIFTY 50 + SENSEX via yfinance, retrain, diff model output vs previous week, alert if regime has shifted.
- **Monthly retrain**: lower compute, less responsive to regime shifts.
- **Manual trigger**: `POST /api/v1/strategies/regime-trader/retrain` endpoint.

**Files to create / update:**
- `backend/scripts/train_regime_hmm.py` — already exists; add `--schedule weekly` flag
- `backend/app/api/rest/v1/strategies.py` — add `retrain` endpoint (async job)
- `backend/app/infrastructure/jobs.py` — add `regime_weekly_retrain` cron (Sunday 01:00 UTC)

---

## P9 — End-to-End Integration Test (Zerodha Sandbox)

**Goal:** Verify the full order flow from signal to execution on a paper trading account.

**Steps:**
1. Set up Zerodha Kite sandbox credentials in `backend/.env.zerodha` (paper account).
2. Enable `regime_trader_enabled=true` and set `rebalance_enabled=true`.
3. Run the backend and trigger a manual `regime_daily_bar` job via `POST /api/v1/jobs/trigger`.
4. Verify: HMM predicts regime → VIX modifier applied → circuit breaker check → approval request sent → order placed on sandbox → position updated in DB.
5. Check Telegram notification and email alert delivery.
6. Write `backend/tests/integration/test_regime_executor_e2e.py`.

---

## Done (this sprint)

- [x] HMM Regime Trader — engine + strategy + 90 tests
- [x] India VIX fetcher + regime modifier
- [x] Email notifier (SMTP, DRUVA-branded HTML)
- [x] Rebalance scheduler (drift-check + APScheduler, NSE 2026 holidays)
- [x] Regime executor (HMM → VIX → 3-tier circuit breaker → ExecutionService)
- [x] Kelly Criterion position sizing (half-Kelly, portfolio normalization)
- [x] Indian tax manager (STCG 20% / LTCG 12.5%, ₹1.25L exemption, Budget 2024)
- [x] Smart SIP engine (regime-aware, step-up compounding, weekday clamping)
- [x] IV Rank / IV Percentile / PCR (NSE option chain)
- [x] NSE option chain feed + Greeks (delta/gamma/theta/vega)
- [x] Iron Condor strategy (5-criterion entry, 4-criterion exit, NIFTY grid strikes)
- [x] Greeks Dashboard React widget (risk badges, portfolio totals)
- [x] VWAP reversion scalping strategy (IST 09:30–14:30 window, max 3 trades/day)
- [x] Tick aggregator with session VWAP
- [x] Auto square-off at 15:15 IST (APScheduler cron)
- [x] Capital ring-fence (7% scalping pool, 20% daily loss limit, profit lock)
- [x] Composite sentiment engine (VIX + FII + PCR + regime + advance/decline)
- [x] AI portfolio advisor — Claude (primary) + GPT-4o (fallback) with prompt caching
- [x] 6 AI advisor REST endpoints (`/ask`, `/rebalance-suggest`, `/evaluate-stock`, `/daily-briefing`, `/sentiment`, `/regime-status`)
- [x] AI Advisor chat UI (`AiAdvisorPanel.tsx`) with regime badge + sentiment gauge
- [x] All modules wired into FastAPI lifespan + APScheduler (jobs 6–9)
- [x] `anthropic>=0.40.0` + `openai>=1.30.0` added to requirements.txt
