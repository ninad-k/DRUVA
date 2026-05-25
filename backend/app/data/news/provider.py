"""News provider — Phase I.

Four implementations following the same provider-pattern as calendar:

* ``NullNewsProvider`` — returns empty lists; safe default.
* ``StaticNewsProvider`` — fixed in-memory items; for tests and demos.
* ``HttpNewsProvider`` — fetches from a user-supplied REST endpoint.
* ``build_news_provider()`` — factory reading ``DHRUVA_NEWS_*`` settings.

``NewsItem`` is the canonical news object carried through the system.  It is
intentionally lightweight — callers that need sentiment attach it separately
via ``NewsSentimentScorer`` (``sentiment.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class NewsItem:
    """A single news headline + snippet."""

    headline: str
    published_at: datetime
    source: str = ""
    url: str = ""
    symbol: str | None = None
    body_snippet: str = ""
    sentiment_score: float | None = None
    """Pre-scored sentiment in [-1, +1]; None if not yet scored."""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class NewsProvider(Protocol):
    """Minimal protocol for news data sources."""

    async def fetch(
        self,
        *,
        symbol: str | None = None,
        from_dt: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """Return up to ``limit`` news items, newest-first.

        ``symbol=None`` means all symbols.  ``from_dt=None`` means no lower
        bound on publication time.
        """
        ...


class NullNewsProvider:
    """No-op provider — returns empty lists."""

    async def fetch(
        self,
        *,
        symbol: str | None = None,
        from_dt: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        return []


class StaticNewsProvider:
    """Returns items from a fixed in-memory list — useful for tests and demos."""

    def __init__(self, items: list[NewsItem]) -> None:
        self._items = items

    async def fetch(
        self,
        *,
        symbol: str | None = None,
        from_dt: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        results = list(self._items)
        if symbol:
            results = [
                it for it in results
                if it.symbol and it.symbol.upper() == symbol.upper()
            ]
        if from_dt:
            # Normalise to aware datetime for comparison
            tz = from_dt.tzinfo or timezone.utc
            results = [
                it for it in results
                if it.published_at.replace(tzinfo=it.published_at.tzinfo or tz) >= from_dt
            ]
        results.sort(key=lambda it: it.published_at, reverse=True)
        return results[:limit]


class HttpNewsProvider:
    """Fetches news from a user-supplied HTTP API.

    Expected endpoint::

        GET /news?symbol=RELIANCE&from_dt=ISO8601&limit=50

    Returns a JSON array of objects with at minimum::

        {"headline": "...", "published_at": "ISO8601", "source": "..."}
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_s: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def fetch(
        self,
        *,
        symbol: str | None = None,
        from_dt: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx is required for HttpNewsProvider") from exc

        params: dict[str, str | int] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if from_dt:
            params["from_dt"] = from_dt.isoformat()

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.get(f"{self._base_url}/news", params=params, headers=headers)
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()

        items: list[NewsItem] = []
        for item in raw:
            try:
                items.append(_parse_item(item))
            except (KeyError, ValueError):
                continue
        items.sort(key=lambda it: it.published_at, reverse=True)
        return items[:limit]


def _parse_item(item: dict[str, Any]) -> NewsItem:
    published_at = datetime.fromisoformat(str(item["published_at"]))
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return NewsItem(
        headline=str(item.get("headline", "")),
        published_at=published_at,
        source=str(item.get("source", "")),
        url=str(item.get("url", "")),
        symbol=item.get("symbol"),
        body_snippet=str(item.get("body_snippet", "")),
        sentiment_score=item.get("sentiment_score"),
        metadata={k: v for k, v in item.items() if k not in {
            "headline", "published_at", "source", "url", "symbol",
            "body_snippet", "sentiment_score",
        }},
    )


def build_news_provider(cfg: Any = None) -> NewsProvider:
    """Factory returning the correct ``NewsProvider`` implementation.

    Reads from ``DHRUVA_NEWS_*`` settings when ``cfg`` is omitted.

    Supported ``news_provider`` values:

    * ``"null"`` — NullNewsProvider (default)
    * ``"static"`` — StaticNewsProvider([])
    * ``"http"`` — HttpNewsProvider
    """
    if cfg is None:
        try:
            from app.config import get_settings
            cfg = get_settings()
        except Exception:
            return NullNewsProvider()

    provider_name: str = getattr(cfg, "news_provider", "null")

    if provider_name == "http":
        return HttpNewsProvider(
            base_url=getattr(cfg, "news_http_base_url", ""),
            api_key=getattr(cfg, "news_http_api_key", ""),
            timeout_s=float(getattr(cfg, "news_http_timeout_s", 15.0)),
        )
    if provider_name == "static":
        return StaticNewsProvider(items=[])
    return NullNewsProvider()
