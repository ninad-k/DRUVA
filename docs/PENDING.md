# DRUVA — Pending Work Tracker

Last updated: 2026-05-19

---

## ~~P1 — Frontend Navigation~~ ✅ DONE

- `/ai-advisor` route + sidebar entry wired
- `/options/greeks` route + sidebar entry wired
- `AiAdvisorPage.tsx` and `OptionsGreeksPage.tsx` route wrappers created

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

## ~~P3 — Walk-Forward Backtester~~ ✅ DONE

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

## ~~P4 — WhatsApp Approval Flow~~ ✅ DONE

- `backend/app/core/notifications/whatsapp.py` — Twilio WhatsApp notifier
- Approval request, regime alert, circuit breaker alert, daily summary message types
- Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` to `backend/.env`

---

## ~~P5 — VaR / CVaR Portfolio Risk Dashboard~~ ✅ DONE

- `backend/app/core/risk/var_engine.py` — Historical VaR 95%/99%, CVaR, per-position contribution
- `backend/app/api/rest/v1/risk.py` — `POST /api/v1/risk/var`, `GET /api/v1/risk/var/nifty-benchmark`
- `frontend/src/features/risk/VaRDashboard.tsx` — VaR gauge + contribution chart

---

## ~~P6 — Monte Carlo Goal Projection~~ ✅ DONE

**Goal:** Simulate 1000+ portfolio paths to show probability of reaching a savings/corpus goal.

**Inputs:** current portfolio value, monthly SIP amount, target corpus, time horizon (years)
**Output:** probability distribution of final portfolio value, P10/P50/P90 outcomes

**Files to create:**
- `backend/app/core/portfolio/monte_carlo.py` — simulation engine (NumPy-based)
- `backend/app/api/rest/v1/goals.py` — add `POST /api/v1/goals/{id}/simulate` endpoint
- `frontend/src/features/goals/MonteCarloChart.tsx` — fan chart (Recharts)

---

## ~~P7 — Mobile PWA Shell~~ ✅ DONE

- `frontend/public/manifest.json` — DRUVA amber theme, standalone display
- `frontend/src/sw.ts` — service worker (cache-first static, network-first `/api/`)
- `frontend/index.html` — viewport meta, Apple Touch icon tags, manifest link

---

## ~~P8 — HMM Model Retrain Schedule~~ ✅ DONE

- APScheduler cron: Sunday 01:00 UTC (`regime_weekly_retrain` job in `jobs.py`)
- On-demand endpoint: `POST /api/v1/strategies/regime-trader/retrain` (async background job)
- `backend/app/strategies/ml/regime_trader/retrain.py` — shared `retrain_regime_hmm()` function

---

## ~~P9 — End-to-End Integration Test~~ ✅ DONE

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

- [x] P1 Frontend nav — AI Advisor + Greeks sidebar + routes
- [x] P3 Walk-forward backtester — 252/126/21 windows, crash injection, 3 benchmarks, CLI
- [x] P4 WhatsApp notifier — Twilio approval flow
- [x] P5 VaR/CVaR engine + REST + React dashboard
- [x] P6 Monte Carlo goal projection — 1000 paths, fan chart, simulate endpoint
- [x] P7 PWA — manifest, service worker, iOS meta tags
- [x] P8 HMM weekly retrain — Sunday cron + on-demand REST endpoint
- [x] P9 E2E integration tests — 8 RegimeExecutor test cases, all mocked
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
