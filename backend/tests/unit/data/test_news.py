"""Unit tests for news provider + sentiment scorer — Phase I."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.data.news.provider import (
    NewsItem,
    NullNewsProvider,
    StaticNewsProvider,
    build_news_provider,
)
from app.data.news.sentiment import NewsSentimentScorer, SentimentResult, _heuristic_score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def item(
    headline: str = "Test headline",
    symbol: str | None = "INFY",
    published_at: str = "2024-01-10T10:00:00",
    source: str = "NSE",
) -> NewsItem:
    return NewsItem(
        headline=headline,
        published_at=utc(published_at),
        source=source,
        symbol=symbol,
    )


# ---------------------------------------------------------------------------
# NullNewsProvider
# ---------------------------------------------------------------------------

class TestNullNewsProvider:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        p = NullNewsProvider()
        assert await p.fetch() == []

    @pytest.mark.asyncio
    async def test_with_filters_returns_empty(self):
        p = NullNewsProvider()
        assert await p.fetch(symbol="INFY", limit=10) == []


# ---------------------------------------------------------------------------
# StaticNewsProvider
# ---------------------------------------------------------------------------

class TestStaticNewsProvider:
    def _provider(self) -> StaticNewsProvider:
        return StaticNewsProvider(items=[
            item("INFY Q3 beat", symbol="INFY", published_at="2024-01-10T10:00:00"),
            item("TCS revenues drop", symbol="TCS", published_at="2024-01-11T08:00:00"),
            item("Market rally", symbol=None, published_at="2024-01-12T09:00:00"),
        ])

    @pytest.mark.asyncio
    async def test_fetch_all(self):
        p = self._provider()
        result = await p.fetch()
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_filter_by_symbol(self):
        p = self._provider()
        result = await p.fetch(symbol="INFY")
        assert len(result) == 1
        assert result[0].symbol == "INFY"

    @pytest.mark.asyncio
    async def test_symbol_filter_is_case_insensitive(self):
        p = self._provider()
        result = await p.fetch(symbol="tcs")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_null_symbol_items_excluded_by_symbol_filter(self):
        p = self._provider()
        result = await p.fetch(symbol="INFY")
        # "Market rally" (symbol=None) should not appear
        assert all(it.symbol is not None for it in result)

    @pytest.mark.asyncio
    async def test_filter_by_from_dt(self):
        p = self._provider()
        result = await p.fetch(from_dt=utc("2024-01-11T00:00:00"))
        assert all(it.published_at >= utc("2024-01-11T00:00:00") for it in result)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_sorted_newest_first(self):
        p = self._provider()
        result = await p.fetch()
        dates = [it.published_at for it in result]
        assert dates == sorted(dates, reverse=True)

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        p = self._provider()
        result = await p.fetch(limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_provider(self):
        p = StaticNewsProvider(items=[])
        assert await p.fetch() == []


# ---------------------------------------------------------------------------
# build_news_provider
# ---------------------------------------------------------------------------

class TestBuildNewsProvider:
    def test_null_default(self):
        assert isinstance(build_news_provider(cfg=None), NullNewsProvider)

    def test_explicit_null(self):
        class Cfg:
            news_provider = "null"
        assert isinstance(build_news_provider(cfg=Cfg()), NullNewsProvider)

    def test_static(self):
        class Cfg:
            news_provider = "static"
        assert isinstance(build_news_provider(cfg=Cfg()), StaticNewsProvider)

    def test_http(self):
        from app.data.news.provider import HttpNewsProvider

        class Cfg:
            news_provider = "http"
            news_http_base_url = "http://localhost:9001"
            news_http_api_key = "key"
            news_http_timeout_s = 20.0

        p = build_news_provider(cfg=Cfg())
        assert isinstance(p, HttpNewsProvider)
        assert p._base_url == "http://localhost:9001"


# ---------------------------------------------------------------------------
# Heuristic sentiment
# ---------------------------------------------------------------------------

class TestHeuristicScore:
    def test_positive_headline(self):
        score = _heuristic_score("Company beats earnings estimates with record profit")
        assert score > 0

    def test_negative_headline(self):
        score = _heuristic_score("Company misses estimates, stock drops on weak guidance")
        assert score < 0

    def test_neutral_headline(self):
        score = _heuristic_score("Company announces new product lineup")
        assert score == 0.0

    def test_score_in_range(self):
        for text in [
            "surge record beat expansion dividend buyback",
            "fraud lawsuit default collapse crash investigation",
        ]:
            s = _heuristic_score(text)
            assert -1.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# NewsSentimentScorer (heuristic mode — no LLM)
# ---------------------------------------------------------------------------

class TestNewsSentimentScorer:
    @pytest.mark.asyncio
    async def test_score_returns_result(self):
        scorer = NewsSentimentScorer()
        it = item("Company beats earnings estimates")
        result = await scorer.score(it)
        assert isinstance(result, SentimentResult)
        assert result.model == "heuristic"
        assert -1.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_score_batch_filters_by_symbol(self):
        scorer = NewsSentimentScorer()
        items = [
            item("INFY beats", symbol="INFY"),
            item("TCS drops", symbol="TCS"),
        ]
        results = await scorer.score_batch(items, symbol="INFY")
        assert len(results) == 1
        assert results[0].news_item.symbol == "INFY"

    @pytest.mark.asyncio
    async def test_aggregate_empty(self):
        scorer = NewsSentimentScorer()
        assert scorer.aggregate_score([]) == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_average(self):
        scorer = NewsSentimentScorer()
        items_list = [
            item("Company beats earnings"),
            item("Stock drops on miss"),
        ]
        results = await scorer.score_batch(items_list)
        agg = scorer.aggregate_score(results)
        assert isinstance(agg, float)

    def test_label_positive(self):
        r = SentimentResult(news_item=item(), score=0.5)
        assert r.label == "positive"

    def test_label_negative(self):
        r = SentimentResult(news_item=item(), score=-0.5)
        assert r.label == "negative"

    def test_label_neutral(self):
        r = SentimentResult(news_item=item(), score=0.0)
        assert r.label == "neutral"

    @pytest.mark.asyncio
    async def test_llm_fallback_on_bad_response(self):
        """If LLM returns garbage JSON, scorer falls back to heuristic silently."""

        class BadLLM:
            model = "bad-llm"

            async def complete(self, req):
                from app.core.advisor.llm import LLMResponse
                return LLMResponse(text="not json at all", provider="bad", model="bad-llm")

        scorer = NewsSentimentScorer(llm_backend=BadLLM())
        result = await scorer.score(item("Company beats earnings"))
        # Falls back to heuristic (score may differ from 0 but is valid)
        assert -1.0 <= result.score <= 1.0
        assert result.model in ("heuristic", "heuristic_fallback")
