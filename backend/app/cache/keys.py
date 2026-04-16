"""Redis cache-key builders.

Do NOT hardcode cache keys anywhere else in the codebase — always import from
here so TTLs and naming stay consistent.
"""

from __future__ import annotations

# --- TTLs (seconds) ---------------------------------------------------------
TTL_POSITION = 1
TTL_PRICE = 5
TTL_EQUITY = 30
TTL_HOLDINGS = 60
TTL_ANALYTICS = 300
TTL_STRATEGY_PERF = 300
TTL_RISK = 600


def position(account_id: str, symbol: str) -> str:
    return f"position:{account_id}:{symbol}"


def position_pattern(account_id: str) -> str:
    return f"position:{account_id}:*"


def price(symbol: str) -> str:
    return f"price:{symbol}"


def holdings(account_id: str) -> str:
    return f"holdings:{account_id}"


def equity(account_id: str) -> str:
    return f"equity:{account_id}"


def strategy_perf(strategy_id: str) -> str:
    return f"strategy:perf:{strategy_id}"


def analytics(account_id: str, period: str, metric: str) -> str:
    return f"analytics:{account_id}:{period}:{metric}"


def risk_metrics(account_id: str) -> str:
    return f"risk:{account_id}:metrics"


def ratelimit_user(user_id: str) -> str:
    return f"ratelimit:{user_id}"


def ratelimit_orders(account_id: str) -> str:
    return f"ratelimit:orders:{account_id}"
