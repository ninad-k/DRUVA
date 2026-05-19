# DRUVA — Remaining Implementation Gaps

These three items are the only unfinished work in the codebase.
Each section is a self-contained prompt you can hand directly to an LLM.

---

## Gap 1 — Wire WhatsApp into Approval Flow

### Context
`backend/app/core/notifications/whatsapp.py` is fully implemented (`WhatsAppNotifier`
with `send_approval_request()`, `send_circuit_breaker_alert()`, `send_regime_change()`).
It is **not wired anywhere**. Telegram is the current only approval channel.

### What to build

**1. Wire outbound notifications** (`backend/app/core/execution/approval_service.py`)
- Import `WhatsAppNotifier` from `app.core.notifications.whatsapp`
- `ApprovalService.__init__` should accept an optional `whatsapp_notifier: WhatsAppNotifier | None = None`
- In `request_approval()` (the method that sends the approval request to the manager),
  call `await whatsapp_notifier.send_approval_request(...)` alongside the existing
  Telegram send — if `whatsapp_notifier` is not None.

**2. Inject into dependencies** (`backend/app/api/dependencies.py`)
- Add `get_whatsapp_notifier()` helper that reads `TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` from settings and returns a
  `WhatsAppNotifier` or `None` if any credential is missing.
- Pass it when constructing `ApprovalService`.

**3. Inject in lifespan** (`backend/app/main.py`)
- In the `lifespan()` function, instantiate `WhatsAppNotifier` (or `None`)
  the same way `TelegramNotifier` is instantiated.
- Store as `app.state.whatsapp_notifier`.
- Pass it to `register_jobs()` and the `_approval_factory` closure.

**4. Inbound WhatsApp webhook** (new file: `backend/app/api/rest/v1/webhooks_whatsapp.py`)
- Twilio sends a POST to your webhook URL when a manager replies.
- Parse the form body: `Body` field contains the reply text, `From` contains the
  manager's WhatsApp number (e.g. `whatsapp:+911234567890`).
- Extract `APPROVE <approval_id>` or `REJECT <approval_id>` from `Body`.
- Call `ApprovalService.approve(approval_id)` or `ApprovalService.reject(approval_id)`.
- Respond with a TwiML `<Response><Message>...</Message></Response>` XML reply.
- Mount the router at `POST /api/v1/webhooks/whatsapp` in `main.py`.

**5. Settings** (`backend/app/config.py`)
Add to the `Settings` class:
```python
twilio_account_sid: str = ""
twilio_auth_token: str = ""
twilio_whatsapp_from: str = ""   # e.g. "whatsapp:+14155238886"
```

### Files to touch
- `backend/app/core/execution/approval_service.py`
- `backend/app/api/dependencies.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/api/rest/v1/webhooks_whatsapp.py` ← new file
- `backend/app/infrastructure/jobs.py` (pass whatsapp_notifier to jobs that use ApprovalService)

---

## Gap 2 — Frontend Tests for 3 New Components

### Context
The project uses **Vitest + React Testing Library**. Existing tests are in
`frontend/src/features/goals/__tests__/GoalsPage.test.tsx` — use those as a
style reference. There are **no tests** for:

- `frontend/src/features/goals/MonteCarloChart.tsx`
- `frontend/src/features/risk/VaRDashboard.tsx`
- `frontend/src/features/ai-advisor/AiAdvisorPanel.tsx`

### What to build

**`frontend/src/features/goals/__tests__/MonteCarloChart.test.tsx`**

Mock `fetch` to return a minimal simulation result:
```json
{
  "p10": 800000, "p25": 1200000, "p50": 1800000,
  "p75": 2400000, "p90": 3200000,
  "probability_of_success": 0.72,
  "expected_final_value": 1900000,
  "worst_case": 700000, "best_case": 3500000,
  "horizon_months": 120, "target_corpus": 2000000,
  "total_invested": 1200000,
  "fan_data": [
    {"month": 0, "p10": 500000, "p25": 500000, "p50": 500000, "p75": 500000, "p90": 500000},
    {"month": 120, "p10": 800000, "p25": 1200000, "p50": 1800000, "p75": 2400000, "p90": 3200000}
  ]
}
```

Test cases:
1. Renders "Monte Carlo Goal Projection" heading.
2. "Run Simulation" button is present and clickable.
3. After clicking, fetch is called with `POST /api/v1/goals/{goalId}/simulate`.
4. After fetch resolves, success probability badge appears with "72.0%".
5. P50 value rendered as "₹18.00L" (or equivalent formatted value).
6. Target corpus reference line data (check chart renders without crash).

---

**`frontend/src/features/risk/__tests__/VaRDashboard.test.tsx`**

Mock fetch for `POST /api/v1/risk/var`:
```json
{
  "var_95": 0.023, "var_99": 0.038, "cvar_95": 0.031,
  "portfolio_value": 500000,
  "contributions": [
    {"symbol": "NIFTYBEES", "weight": 0.6, "var_contribution": 0.014},
    {"symbol": "GOLDBEES",  "weight": 0.4, "var_contribution": 0.009}
  ]
}
```

Test cases:
1. Renders "VaR" or "Value at Risk" heading.
2. "Calculate VaR" / run button triggers POST to `/api/v1/risk/var`.
3. After response, VaR 95% value is displayed (e.g. "2.30%").
4. Contribution bar for "NIFTYBEES" is present in the DOM.

---

**`frontend/src/features/ai-advisor/__tests__/AiAdvisorPanel.test.tsx`**

Mock fetch for `GET /api/v1/ai-advisor/sentiment` (initial load) and
`POST /api/v1/ai-advisor/ask` (chat message).

Sentiment response:
```json
{
  "score": 42, "label": "Cautiously Bullish",
  "regime": "Bull", "vix": 14.2,
  "components": {"vix": 0.6, "fii": 0.5, "pcr": 0.4, "regime": 0.8, "ad_ratio": 0.6}
}
```

Ask response:
```json
{ "answer": "Based on current Bull regime, maintain 80% equity allocation." }
```

Test cases:
1. Sentiment gauge renders on mount (sentiment fetched automatically).
2. "Bull" regime badge is visible.
3. Typing a message and pressing Send calls `POST /api/v1/ai-advisor/ask`.
4. Response text appears in the chat thread.
5. Input is cleared after send.

---

## Gap 3 — Docker Compose: Expose gRPC Port + Prod Observability

### Context
- `docker-compose.dev.yml` — infrastructure only (Postgres, Redis, Jaeger, Envoy, Prometheus, Grafana). Backend runs natively.
- `docker-compose.prod.yml` — runs the full backend container but is missing gRPC port exposure and observability services.

### What to fix

**`docker-compose.dev.yml`**
- The backend isn't containerised in dev, but Envoy's config (`envoy/envoy.yaml`) routes gRPC-Web on port 8080 to `host.docker.internal:50051`.
  Verify this routing is present. If it isn't, add a cluster entry pointing to the backend's gRPC port.
- No change needed to the compose file itself unless the Envoy cluster target is wrong.

**`docker-compose.prod.yml`**
Add the following to the `backend` service:
```yaml
ports:
  - "8000:8000"   # FastAPI/HTTP (likely already present)
  - "50051:50051" # gRPC (ADD THIS)
```

Add these missing services (copy from dev compose, adjust as needed):
```yaml
  prometheus:
    image: prom/prometheus:v2.55.0
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.3.0
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    ports:
      - "3001:3000"
    depends_on:
      - prometheus
    restart: unless-stopped
```

Add `grafana_data` to the `volumes:` section at the bottom.

Also add these environment variables to the backend service in prod compose
(they are already in `.env.example` but missing from the compose env block):
```yaml
environment:
  - TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID:-}
  - TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN:-}
  - TWILIO_WHATSAPP_FROM=${TWILIO_WHATSAPP_FROM:-}
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
  - OPENAI_API_KEY=${OPENAI_API_KEY:-}
  - DRUVA_SMTP_HOST=${DRUVA_SMTP_HOST:-}
  - DRUVA_SMTP_PORT=${DRUVA_SMTP_PORT:-587}
  - DRUVA_SMTP_USER=${DRUVA_SMTP_USER:-}
  - DRUVA_SMTP_PASS=${DRUVA_SMTP_PASS:-}
  - DRUVA_SMTP_FROM=${DRUVA_SMTP_FROM:-}
  - regime_trader_enabled=${regime_trader_enabled:-false}
  - rebalance_enabled=${rebalance_enabled:-false}
  - regime_alert_chat_id=${regime_alert_chat_id:-}
```

### Files to touch
- `docker-compose.prod.yml`
- `docker-compose.dev.yml` (verify Envoy cluster target only)
- `envoy/envoy.yaml` (if gRPC-Web cluster target needs fixing)

---

*All three gaps are independent — they can be implemented in any order or in parallel.*
