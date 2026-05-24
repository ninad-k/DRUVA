"""Tests for the Council orchestrator (LLM mocked)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.core.advisor.council import Council
from app.core.advisor.personas import WARREN_BUFFETT, CHARLIE_MUNGER
from app.core.advisor.valuation import (
    FundamentalsView,
    LineItem,
    StaticFundamentalsProvider,
)
from app.core.ai.portfolio_advisor import AdvisorResponse, PortfolioContext


def _ctx() -> PortfolioContext:
    return PortfolioContext(
        regime="Neutral",
        confidence=0.8,
        sentiment_score=0.0,
        sentiment_label="Neutral",
        total_value=1_000_000.0,
        positions=[],
        cash_pct=20.0,
        daily_pnl_pct=0.0,
        top_holdings=[],
    )


def _view() -> FundamentalsView:
    from datetime import date

    return FundamentalsView(
        symbol="HDFCBANK",
        exchange="NSE",
        net_income=[LineItem(period_end=date(2024, 3, 31), value=600.0)],
        market_cap=10_000.0,
        pe_ratio=18.0,
        shares_outstanding=100.0,
        roe=17.5,
        debt_to_equity=0.4,
    )


@dataclass
class _ScriptedAdvisor:
    """Returns a different payload per call, keyed by call count."""

    payloads: list[dict[str, Any]]
    _idx: int = 0

    async def ask(self, question: str, context: PortfolioContext) -> AdvisorResponse:  # noqa: D401
        payload = self.payloads[self._idx % len(self.payloads)]
        self._idx += 1
        return AdvisorResponse(answer=json.dumps(payload), confidence=0.8)


@pytest.mark.asyncio
async def test_ask_as_extracts_persona_signal() -> None:
    payload = {
        "answer": "Looks like a moat.",
        "recommended_actions": ["Hold for the long term"],
        "risk_level": "Low",
        "confidence": 0.85,
        "sources": ["ROE"],
        "persona_signal": {
            "signal": "bullish",
            "confidence": 82,
            "reasoning": "ROE > 15%, durable franchise.",
        },
    }
    advisor = _ScriptedAdvisor(payloads=[payload])
    provider = StaticFundamentalsProvider()
    provider.add(_view())
    council = Council(advisor=advisor, fundamentals_provider=provider)  # type: ignore[arg-type]
    verdict = await council.ask_as(
        persona=WARREN_BUFFETT, question="Own HDFCBANK?", context=_ctx(), fundamentals=_view()
    )
    assert verdict.signal.signal == "bullish"
    assert verdict.signal.confidence == 82
    assert verdict.persona.slug == "buffett"


@pytest.mark.asyncio
async def test_council_synthesises_consensus_by_weighted_vote() -> None:
    payloads = [
        {
            "answer": "Buy.",
            "recommended_actions": [],
            "risk_level": "Low",
            "confidence": 0.8,
            "sources": [],
            "persona_signal": {"signal": "bullish", "confidence": 80, "reasoning": "..."},
        },
        {
            "answer": "Avoid.",
            "recommended_actions": [],
            "risk_level": "High",
            "confidence": 0.5,
            "sources": [],
            "persona_signal": {"signal": "bearish", "confidence": 30, "reasoning": "..."},
        },
    ]
    advisor = _ScriptedAdvisor(payloads=payloads)
    provider = StaticFundamentalsProvider()
    provider.add(_view())
    council = Council(advisor=advisor, fundamentals_provider=provider)  # type: ignore[arg-type]
    verdict = await council.run_council(
        symbol="HDFCBANK",
        question="Own HDFCBANK?",
        context=_ctx(),
        persona_slugs=["buffett", "munger"],
    )
    assert verdict.consensus == "bullish"
    assert verdict.vote_distribution == {"bullish": 1, "bearish": 1, "neutral": 0}
    assert verdict.consensus_confidence == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_council_fallback_without_fundamentals() -> None:
    payload = {
        "answer": "Skipping — outside circle.",
        "recommended_actions": [],
        "risk_level": "Medium",
        "confidence": 0.4,
        "sources": [],
        "persona_signal": {"signal": "neutral", "confidence": 40, "reasoning": "No data"},
    }
    advisor = _ScriptedAdvisor(payloads=[payload, payload])
    provider = StaticFundamentalsProvider()   # empty.
    council = Council(advisor=advisor, fundamentals_provider=provider)  # type: ignore[arg-type]
    verdict = await council.run_council(
        symbol="UNKNOWN",
        question="Worth a look?",
        context=_ctx(),
        persona_slugs=["buffett", "munger"],
    )
    assert verdict.fundamentals == {}
    assert verdict.intrinsic_value is None
    assert verdict.notes
