"""LLM-powered news sentiment scorer — Phase I.

``NewsSentimentScorer`` takes a list of ``NewsItem`` objects and returns
``SentimentResult`` objects with a [-1, +1] score and a brief rationale.

When the LLM is disabled (``news_sentiment_llm_enabled=False``) or unavailable,
the scorer falls back to a simple keyword-based heuristic so the pipeline
remains functional without any external dependency.

The LLM prompt instructs the model to act as a systematic trader evaluating
short-term market impact on the specific symbol.  The model must reply with
a strict JSON object ``{"score": float, "rationale": str}`` so we can parse
it without regex fragility.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.data.news.provider import NewsItem


@dataclass(frozen=True)
class SentimentResult:
    """Sentiment for a single news item."""

    news_item: NewsItem
    score: float        # [-1.0, +1.0]; 0 = neutral
    rationale: str = ""
    model: str = "heuristic"

    @property
    def label(self) -> str:
        if self.score > 0.2:
            return "positive"
        if self.score < -0.2:
            return "negative"
        return "neutral"


# ---------------------------------------------------------------------------
# Keyword heuristic — no external deps
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = frozenset([
    "beat", "beats", "exceeded", "exceeds", "strong", "surge", "record",
    "upgrade", "buy", "outperform", "profit", "growth", "acquisition",
    "partnership", "dividend", "buyback", "expansion", "raise", "raised",
    "rally", "bullish", "positive", "better", "above", "highest",
])

_NEGATIVE_WORDS = frozenset([
    "miss", "misses", "missed", "weak", "drop", "fell", "loss", "losses",
    "downgrade", "sell", "underperform", "decline", "slump", "cut", "cuts",
    "below", "concern", "concerns", "lawsuit", "fraud", "default", "delay",
    "resign", "investigation", "probe", "recall", "crash", "collapse",
    "warning", "caution", "lowest", "slowdown",
])


def _heuristic_score(text: str) -> float:
    tokens = re.findall(r"\w+", text.lower())
    pos = sum(1 for t in tokens if t in _POSITIVE_WORDS)
    neg = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    raw = (pos - neg) / total
    # Dampen toward zero — heuristics are noisy
    return round(raw * 0.6, 3)


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a systematic trader's news-impact evaluator.\n"
    "Your job: assess the SHORT-TERM (1–5 day) price impact of a news item on a specific stock.\n\n"
    "Rules:\n"
    "- Reply ONLY with valid JSON: {\"score\": <float -1 to 1>, \"rationale\": <1-2 sentences>}\n"
    "- score = +1 extremely bullish, -1 extremely bearish, 0 no impact\n"
    "- Be conservative: most news is noise; only extreme events get |score| > 0.6\n"
    "- Do NOT explain your reasoning outside the JSON object\n"
)


def _build_user_prompt(item: NewsItem) -> str:
    parts = [f"Symbol: {item.symbol or 'UNKNOWN'}", f"Headline: {item.headline}"]
    if item.body_snippet:
        parts.append(f"Snippet: {item.body_snippet[:400]}")
    return "\n".join(parts)


def _parse_llm_response(text: str) -> tuple[float, str]:
    """Extract (score, rationale) from LLM JSON response.  Returns (0.0, '') on failure."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```[a-z]*\n?|```", "", text).strip()
    data: dict[str, Any] = json.loads(cleaned)  # raises JSONDecodeError on bad input
    score = float(data.get("score", 0.0))
    score = max(-1.0, min(1.0, score))
    rationale = str(data.get("rationale", ""))
    return score, rationale


class NewsSentimentScorer:
    """Score news items using an LLM or keyword heuristic fallback.

    Usage::

        scorer = NewsSentimentScorer(llm_backend=backend)
        results = await scorer.score_batch(items, symbol="INFY")
    """

    def __init__(
        self,
        *,
        llm_backend: Any | None = None,
        temperature: float = 0.1,
        max_tokens: int = 256,
    ) -> None:
        self._llm = llm_backend
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def score(self, item: NewsItem) -> SentimentResult:
        """Score a single news item."""
        if self._llm is None:
            return SentimentResult(
                news_item=item,
                score=_heuristic_score(f"{item.headline} {item.body_snippet}"),
                model="heuristic",
            )

        try:
            from app.core.advisor.llm import LLMRequest
            req = LLMRequest(
                system=_SYSTEM_PROMPT,
                user=_build_user_prompt(item),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            resp = await self._llm.complete(req)
            score, rationale = _parse_llm_response(resp.text)
            model_name: str = getattr(self._llm, "model", "unknown")
            return SentimentResult(
                news_item=item,
                score=score,
                rationale=rationale,
                model=model_name,
            )
        except Exception:
            # Fall back to heuristic on any LLM failure — never hard-fail
            return SentimentResult(
                news_item=item,
                score=_heuristic_score(f"{item.headline} {item.body_snippet}"),
                model="heuristic_fallback",
            )

    async def score_batch(
        self,
        items: list[NewsItem],
        *,
        symbol: str | None = None,
    ) -> list[SentimentResult]:
        """Score a list of items; optionally filter to ``symbol`` first."""
        targets = items
        if symbol:
            targets = [it for it in items if it.symbol and it.symbol.upper() == symbol.upper()]

        results: list[SentimentResult] = []
        for item in targets:
            results.append(await self.score(item))
        return results

    def aggregate_score(self, results: list[SentimentResult]) -> float:
        """Return average sentiment score across results, or 0.0 if empty."""
        if not results:
            return 0.0
        return round(sum(r.score for r in results) / len(results), 4)
