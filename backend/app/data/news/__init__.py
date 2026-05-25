"""News aggregator + LLM sentiment — Phase I."""

from app.data.news.provider import (
    NewsItem,
    NewsProvider,
    HttpNewsProvider,
    NullNewsProvider,
    StaticNewsProvider,
    build_news_provider,
)
from app.data.news.sentiment import NewsSentimentScorer, SentimentResult

__all__ = [
    "HttpNewsProvider",
    "NewsItem",
    "NewsProvider",
    "NewsSentimentScorer",
    "NullNewsProvider",
    "SentimentResult",
    "StaticNewsProvider",
    "build_news_provider",
]
