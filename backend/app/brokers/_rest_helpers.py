"""Shared helpers for REST broker adapters.

These keep boilerplate (timing, error wrapping, header building) consistent
across every broker. Each adapter still owns its endpoint shapes and payload
mapping — only the plumbing is shared.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.brokers.base import BrokerHealth
from app.core.errors import BrokerError


async def safe_json(response: httpx.Response, broker_id: str, op: str) -> dict[str, Any]:
    """Return parsed JSON or raise BrokerError with a helpful message.

    Centralised so we never silently swallow a 4xx/5xx — if the broker
    returned anything other than a 2xx, the order/quote/etc. is treated as
    failed and the error message is preserved for audit.
    """
    if response.status_code >= 400:
        raise BrokerError(f"{broker_id}_{op}_failed:{response.status_code}:{response.text[:200]}")
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        raise BrokerError(f"{broker_id}_{op}_bad_json:{exc}") from exc


async def health_probe(
    http: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> BrokerHealth:
    """Hit ``url`` and report wall-clock latency.

    Used by every adapter's ``health()`` method so the dashboard sees an
    apples-to-apples comparison across brokers.
    """
    started = time.perf_counter()
    try:
        response = await http.get(url, headers=headers, timeout=timeout)
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code >= 500:
            return BrokerHealth(
                is_healthy=False,
                latency_ms=latency_ms,
                message=f"http_{response.status_code}",
            )
        return BrokerHealth(is_healthy=True, latency_ms=latency_ms)
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000
        return BrokerHealth(is_healthy=False, latency_ms=latency_ms, message=str(exc))
