"""News REST endpoints — Phase I.

GET  /api/v1/news/feed       → recent news items (with optional sentiment)
GET  /api/v1/news/sentiment  → aggregate sentiment score for a symbol
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.auth.dependencies import get_current_user
from app.data.news.provider import NewsItem, build_news_provider
from app.data.news.sentiment import NewsSentimentScorer

router = APIRouter()


class NewsItemDTO(BaseModel):
    headline: str
    published_at: str
    source: str = ""
    url: str = ""
    symbol: str | None = None
    body_snippet: str = ""
    sentiment_score: float | None = None


class SentimentSummaryDTO(BaseModel):
    symbol: str
    aggregate_score: float
    label: str
    n_items: int


def _to_dto(item: NewsItem) -> NewsItemDTO:
    return NewsItemDTO(
        headline=item.headline,
        published_at=item.published_at.isoformat(),
        source=item.source,
        url=item.url,
        symbol=item.symbol,
        body_snippet=item.body_snippet,
        sentiment_score=item.sentiment_score,
    )


@router.get("/feed", summary="Fetch recent news")
async def feed(
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _user=Depends(get_current_user),
) -> list[NewsItemDTO]:
    provider = build_news_provider()
    items = await provider.fetch(symbol=symbol, limit=limit)
    return [_to_dto(it) for it in items]


@router.get("/sentiment", summary="Aggregate sentiment score for a symbol")
async def sentiment(
    symbol: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
) -> SentimentSummaryDTO:
    provider = build_news_provider()
    items = await provider.fetch(symbol=symbol, limit=limit)

    scorer = NewsSentimentScorer()
    results = await scorer.score_batch(items, symbol=symbol)
    agg = scorer.aggregate_score(results)
    label = "positive" if agg > 0.2 else ("negative" if agg < -0.2 else "neutral")

    return SentimentSummaryDTO(
        symbol=symbol,
        aggregate_score=agg,
        label=label,
        n_items=len(results),
    )
