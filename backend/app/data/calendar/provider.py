"""Economic and corporate calendar provider — Phase H.

Provides a unified ``CalendarProvider`` Protocol with four implementations:

* ``NullCalendarProvider`` — returns empty lists; safe default when no source
  is configured.
* ``StaticCalendarProvider`` — holds a fixed list of events; ideal for tests
  and UI demos.
* ``HttpCalendarProvider`` — fetches events from a user-supplied REST API that
  returns a JSON array of CalendarEvent-shaped objects.  DHRUVA does not
  bundle a live calendar data source; operators must wire their own (e.g.
  Investingdotcom scraper, NSE corporate actions feed, RBI calendar).
* ``build_calendar_provider()`` — factory that reads ``DHRUVA_CALENDAR_*``
  settings and returns the appropriate implementation.

CalendarEvent shape matches the intersection of:
  - NSE corporate actions (dividend, split, bonus, rights)
  - Economic announcements (RBI MPC, CPI, IIP, GDP)
  - Earnings releases

All timestamps are stored as ``date`` (event date) plus an optional
``time_utc`` for intraday events (e.g. RBI decision at 10:00 IST = 04:30 UTC).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Literal, Protocol, runtime_checkable

CalendarEventType = Literal[
    "dividend",
    "split",
    "bonus",
    "rights",
    "earnings",
    "rbi_mpc",
    "macro",
    "ipo",
    "other",
]


@dataclass(frozen=True)
class CalendarEvent:
    """A single economic or corporate calendar entry."""

    event_date: date
    event_type: CalendarEventType
    title: str
    symbol: str | None = None
    exchange: str | None = None
    description: str = ""
    time_utc: time | None = None
    impact: Literal["low", "medium", "high"] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CalendarProvider(Protocol):
    """Minimal protocol for calendar data sources."""

    async def upcoming(
        self,
        *,
        from_date: date,
        to_date: date,
        event_types: list[CalendarEventType] | None = None,
        symbol: str | None = None,
    ) -> list[CalendarEvent]:
        """Return events in ``[from_date, to_date]``.

        ``event_types=None`` means all types.  ``symbol=None`` means all
        symbols (only relevant for corporate events).
        """
        ...


class NullCalendarProvider:
    """No-op provider — returns empty lists.  Used when calendar is disabled."""

    async def upcoming(
        self,
        *,
        from_date: date,
        to_date: date,
        event_types: list[CalendarEventType] | None = None,
        symbol: str | None = None,
    ) -> list[CalendarEvent]:
        return []


class StaticCalendarProvider:
    """Returns events from a fixed in-memory list — useful for tests and demos."""

    def __init__(self, events: list[CalendarEvent]) -> None:
        self._events = events

    async def upcoming(
        self,
        *,
        from_date: date,
        to_date: date,
        event_types: list[CalendarEventType] | None = None,
        symbol: str | None = None,
    ) -> list[CalendarEvent]:
        results: list[CalendarEvent] = []
        for ev in self._events:
            if not (from_date <= ev.event_date <= to_date):
                continue
            if event_types and ev.event_type not in event_types:
                continue
            # When a symbol filter is active, only include events for that symbol.
            # Global events (symbol=None) are excluded from symbol-filtered queries.
            if symbol and (ev.symbol is None or ev.symbol.upper() != symbol.upper()):
                continue
            results.append(ev)
        results.sort(key=lambda e: (e.event_date, e.time_utc or time.min))
        return results


class HttpCalendarProvider:
    """Fetches calendar events from a user-supplied HTTP API.

    The API must accept::

        GET /events?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD[&event_types=div,earn][&symbol=RELIANCE]

    and return a JSON array of objects with at minimum::

        {"event_date": "YYYY-MM-DD", "event_type": "dividend", "title": "..."}

    All other CalendarEvent fields are optional.
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

    async def upcoming(
        self,
        *,
        from_date: date,
        to_date: date,
        event_types: list[CalendarEventType] | None = None,
        symbol: str | None = None,
    ) -> list[CalendarEvent]:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx is required for HttpCalendarProvider") from exc

        params: dict[str, str] = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
        if event_types:
            params["event_types"] = ",".join(event_types)
        if symbol:
            params["symbol"] = symbol

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.get(f"{self._base_url}/events", params=params, headers=headers)
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()

        events: list[CalendarEvent] = []
        for item in raw:
            try:
                ev = _parse_event(item)
                events.append(ev)
            except (KeyError, ValueError):
                continue  # skip malformed entries
        events.sort(key=lambda e: (e.event_date, e.time_utc or time.min))
        return events


def _parse_event(item: dict[str, Any]) -> CalendarEvent:
    event_date = date.fromisoformat(str(item["event_date"]))
    event_type: CalendarEventType = item.get("event_type", "other")
    title = str(item.get("title", ""))
    time_utc_raw = item.get("time_utc")
    time_utc: time | None = None
    if isinstance(time_utc_raw, str):
        try:
            time_utc = time.fromisoformat(time_utc_raw)
        except ValueError:
            pass
    return CalendarEvent(
        event_date=event_date,
        event_type=event_type,
        title=title,
        symbol=item.get("symbol"),
        exchange=item.get("exchange"),
        description=str(item.get("description", "")),
        time_utc=time_utc,
        impact=item.get("impact"),
        metadata={k: v for k, v in item.items() if k not in {
            "event_date", "event_type", "title", "symbol", "exchange",
            "description", "time_utc", "impact",
        }},
    )


def build_calendar_provider(cfg: Any = None) -> CalendarProvider:
    """Factory that returns the correct ``CalendarProvider`` implementation.

    Reads from the ``DHRUVA_CALENDAR_*`` settings block when ``cfg`` is omitted.
    Pass a ``Settings`` instance (or a duck-typed object) for explicit injection.

    Supported implementations (``calendar_provider`` setting):

    * ``"null"`` — NullCalendarProvider (default if unset)
    * ``"static"`` — StaticCalendarProvider(events=[]) — empty unless seeded
    * ``"http"`` — HttpCalendarProvider(base_url=..., api_key=..., timeout_s=...)
    """
    if cfg is None:
        try:
            from app.config import get_settings
            cfg = get_settings()
        except Exception:
            return NullCalendarProvider()

    provider_name: str = getattr(cfg, "calendar_provider", "null")

    if provider_name == "http":
        return HttpCalendarProvider(
            base_url=getattr(cfg, "calendar_http_base_url", ""),
            api_key=getattr(cfg, "calendar_http_api_key", ""),
            timeout_s=float(getattr(cfg, "calendar_http_timeout_s", 15.0)),
        )
    if provider_name == "static":
        return StaticCalendarProvider(events=[])
    return NullCalendarProvider()
