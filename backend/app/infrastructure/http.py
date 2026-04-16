from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    global _http_client  # noqa: PLW0603
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
    yield _http_client


async def close_http_client() -> None:
    global _http_client  # noqa: PLW0603
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
