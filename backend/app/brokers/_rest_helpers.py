"""Shared helpers for REST broker adapters.

These keep boilerplate (timing, error wrapping, header building) consistent
across every broker. Each adapter still owns its endpoint shapes and payload
mapping — only the plumbing is shared.
"""

from __future__ import annotations

import codecs
import csv
import json
import time
import zlib
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
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


_IST = timezone(timedelta(hours=5, minutes=30))


def epoch_ms_to_ist_date(value: Any) -> date | None:
    """Convert an epoch-millisecond expiry to a date in IST (exchange-local),
    so midnight-IST stamps do not slip to the previous UTC day."""
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=_IST).date()


async def iter_json_array(
    http: httpx.AsyncClient, url: str, broker_id: str, op: str
) -> AsyncIterator[dict[str, Any]]:
    """Stream a (possibly gzipped) top-level JSON array, yielding one element at a time.

    Public asset hosts are fetched without broker credentials. Gzip is
    detected by magic bytes rather than the URL/headers because some CDNs
    set Content-Encoding (httpx then already inflates it) and others do not.
    """
    decoder = json.JSONDecoder()
    text_dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    inflater: zlib.Decompress | None = None
    first_chunk = True
    buf = ""
    started = False
    async with http.stream("GET", url, follow_redirects=True) as response:
        if response.status_code >= 400:
            raise BrokerError(f"{broker_id}_{op}_failed:{response.status_code}")
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            if first_chunk:
                first_chunk = False
                if chunk[:2] == b"\x1f\x8b":
                    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
            raw = inflater.decompress(chunk) if inflater else chunk
            buf += text_dec.decode(raw)
            if not started:
                buf = buf.lstrip("﻿ \t\r\n")
                if not buf:
                    continue
                if buf[0] != "[":
                    raise BrokerError(f"{broker_id}_{op}_unexpected_format")
                buf = buf[1:]
                started = True
            pos = 0
            while True:
                while pos < len(buf) and buf[pos] in " \t\r\n,":
                    pos += 1
                if pos >= len(buf) or buf[pos] == "]":
                    break
                try:
                    obj, end = decoder.raw_decode(buf, pos)
                except json.JSONDecodeError:
                    break  # element split across chunks; wait for more bytes
                pos = end
                if isinstance(obj, dict):
                    yield obj
            buf = buf[pos:]
    if not started:
        raise BrokerError(f"{broker_id}_{op}_empty_response")
    if buf.strip().strip(",") not in ("", "]"):
        raise BrokerError(f"{broker_id}_{op}_truncated")


async def iter_csv_rows(
    http: httpx.AsyncClient, url: str, broker_id: str, op: str
) -> AsyncIterator[dict[str, str]]:
    """Stream a CSV file line by line, yielding header-keyed dicts."""
    header: list[str] | None = None
    async with http.stream("GET", url, follow_redirects=True) as response:
        if response.status_code >= 400:
            raise BrokerError(f"{broker_id}_{op}_failed:{response.status_code}")
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            row = next(csv.reader([line.lstrip("﻿") if header is None else line]))
            if header is None:
                header = [h.strip() for h in row]
                continue
            yield dict(zip(header, (c.strip() for c in row), strict=False))
    if header is None:
        raise BrokerError(f"{broker_id}_{op}_empty_response")
