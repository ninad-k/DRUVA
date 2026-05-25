"""Unit tests for the calendar provider — Phase H."""

from __future__ import annotations

import pytest
from datetime import date, time

from app.data.calendar.provider import (
    CalendarEvent,
    NullCalendarProvider,
    StaticCalendarProvider,
    build_calendar_provider,
)


def make_event(
    event_date: str,
    event_type: str = "earnings",
    title: str = "Test",
    symbol: str | None = None,
    impact: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        event_date=date.fromisoformat(event_date),
        event_type=event_type,
        title=title,
        symbol=symbol,
        impact=impact,
    )


FROM = date(2024, 1, 1)
TO = date(2024, 1, 31)


class TestNullCalendarProvider:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        p = NullCalendarProvider()
        events = await p.upcoming(from_date=FROM, to_date=TO)
        assert events == []

    @pytest.mark.asyncio
    async def test_filters_dont_matter(self):
        p = NullCalendarProvider()
        events = await p.upcoming(from_date=FROM, to_date=TO, event_types=["earnings"], symbol="INFY")
        assert events == []


class TestStaticCalendarProvider:
    def _make_provider(self) -> StaticCalendarProvider:
        return StaticCalendarProvider(events=[
            make_event("2024-01-10", "earnings", "INFY Q3", symbol="INFY"),
            make_event("2024-01-15", "dividend", "RELIANCE Div", symbol="RELIANCE"),
            make_event("2024-01-20", "rbi_mpc", "RBI MPC", symbol=None),
            make_event("2024-02-05", "earnings", "TCS Q3", symbol="TCS"),  # outside window
        ])

    @pytest.mark.asyncio
    async def test_returns_events_in_window(self):
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO)
        assert len(events) == 3
        assert all(FROM <= e.event_date <= TO for e in events)

    @pytest.mark.asyncio
    async def test_filters_by_event_type(self):
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO, event_types=["earnings"])
        assert len(events) == 1
        assert events[0].title == "INFY Q3"

    @pytest.mark.asyncio
    async def test_filters_by_symbol(self):
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO, symbol="RELIANCE")
        assert len(events) == 1
        assert events[0].event_type == "dividend"

    @pytest.mark.asyncio
    async def test_symbol_filter_is_case_insensitive(self):
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO, symbol="infy")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_symbol_none_events_pass_symbol_filter(self):
        # RBI MPC event has no symbol — should appear when no symbol filter
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO)
        titles = [e.title for e in events]
        assert "RBI MPC" in titles

    @pytest.mark.asyncio
    async def test_results_sorted_by_date(self):
        p = self._make_provider()
        events = await p.upcoming(from_date=FROM, to_date=TO)
        dates = [e.event_date for e in events]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_empty_provider_returns_empty(self):
        p = StaticCalendarProvider(events=[])
        assert await p.upcoming(from_date=FROM, to_date=TO) == []

    @pytest.mark.asyncio
    async def test_boundary_dates_inclusive(self):
        events = [
            make_event("2024-01-01"),
            make_event("2024-01-31"),
        ]
        p = StaticCalendarProvider(events=events)
        result = await p.upcoming(from_date=date(2024, 1, 1), to_date=date(2024, 1, 31))
        assert len(result) == 2


class TestBuildCalendarProvider:
    def test_null_default(self):
        p = build_calendar_provider(cfg=None)
        assert isinstance(p, NullCalendarProvider)

    def test_null_explicit(self):
        class Cfg:
            calendar_provider = "null"
        assert isinstance(build_calendar_provider(cfg=Cfg()), NullCalendarProvider)

    def test_static(self):
        class Cfg:
            calendar_provider = "static"
        assert isinstance(build_calendar_provider(cfg=Cfg()), StaticCalendarProvider)

    def test_http(self):
        from app.data.calendar.provider import HttpCalendarProvider

        class Cfg:
            calendar_provider = "http"
            calendar_http_base_url = "http://localhost:9000"
            calendar_http_api_key = "secret"
            calendar_http_timeout_s = 30.0

        p = build_calendar_provider(cfg=Cfg())
        assert isinstance(p, HttpCalendarProvider)
        assert p._base_url == "http://localhost:9000"
        assert p._api_key == "secret"
