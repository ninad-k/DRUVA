"""Prometheus metrics definitions.

Exposed on ``/metrics`` via a FastAPI route registered in ``app.main``.
Prefer registering counters/histograms here as module-level singletons and
importing them where needed.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- HTTP -------------------------------------------------------------------
http_requests_total = Counter(
    "dhruva_http_requests_total",
    "Total HTTP requests.",
    labelnames=("method", "route", "status"),
)

http_request_duration_seconds = Histogram(
    "dhruva_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# --- Orders ----------------------------------------------------------------
orders_placed_total = Counter(
    "dhruva_orders_placed_total",
    "Orders placed by outcome.",
    labelnames=("broker", "status"),
)

order_place_duration_seconds = Histogram(
    "dhruva_order_place_duration_seconds",
    "Order placement latency in seconds.",
    labelnames=("broker",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)

# --- Strategies ------------------------------------------------------------
strategy_executions_total = Counter(
    "dhruva_strategy_executions_total",
    "Strategy executions by result.",
    labelnames=("strategy", "result"),
)

ml_predictions_total = Counter(
    "dhruva_ml_predictions_total",
    "ML model predictions emitted.",
    labelnames=("model", "signal"),
)

# --- WebSocket -------------------------------------------------------------
active_websocket_connections = Gauge(
    "dhruva_active_websocket_connections",
    "Currently open WebSocket connections.",
)
