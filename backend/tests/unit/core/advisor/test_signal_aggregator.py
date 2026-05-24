"""Unit tests for the multi-agent signal aggregator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.ai.portfolio_advisor import AdvisorResponse, PortfolioContext
from app.core.advisor.signal_aggregator import (
    PortfolioState,
    SignalAggregator,
    compact_signals,
    compute_allowed_actions,
)


def _context() -> PortfolioContext:
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


class TestCompactSignals:
    def test_drops_extra_keys(self) -> None:
        signals = {
            "RELIANCE": {
                "buffett": {
                    "signal": "bullish",
                    "confidence": 80,
                    "reasoning": "Strong moat",
                    "intrinsic_value": 3000,
                    "irrelevant_blob": [1, 2, 3],
                },
            },
        }
        compact = compact_signals(signals)
        assert compact["RELIANCE"]["buffett"] == {
            "signal": "bullish",
            "confidence": 80,
            "reasoning": "Strong moat",
        }

    def test_truncates_long_reasoning(self) -> None:
        long_reason = "x" * 1_000
        signals = {"A": {"agent": {"signal": "neutral", "reasoning": long_reason}}}
        compact = compact_signals(signals)
        assert len(compact["A"]["agent"]["reasoning"]) == 240

    def test_drops_empty_agents(self) -> None:
        signals = {"A": {"agent": {"unrelated": True}}}
        assert compact_signals(signals) == {}


class TestComputeAllowedActions:
    def test_buy_only_when_cap_and_cash_allow(self) -> None:
        state = PortfolioState(
            cash_inr=100_000.0,
            positions={},
            max_single_position_pct=10.0,
        )
        allowed = compute_allowed_actions(
            portfolio_state=state,
            tickers=["RELIANCE"],
            prices={"RELIANCE": 2_500.0},
        )
        envelope = allowed["RELIANCE"]
        assert envelope["actions"] == ["hold", "buy"]
        # Cap = 10% * 100_000 = 10_000. Buying power = 100_000. So buy room = 10_000.
        # Max qty = floor(10_000 / 2_500) = 4.
        assert envelope["max_qty"] == 4

    def test_sell_when_holding_position(self) -> None:
        state = PortfolioState(
            cash_inr=0.0,
            positions={"RELIANCE": {"quantity": 50, "ltp": 2_500.0}},
            max_single_position_pct=10.0,
        )
        allowed = compute_allowed_actions(
            portfolio_state=state,
            tickers=["RELIANCE"],
            prices={"RELIANCE": 2_500.0},
        )
        envelope = allowed["RELIANCE"]
        # Existing position already at cap (125k vs 10% of 125k = 12.5k) → no buy.
        assert "buy" not in envelope["actions"]
        assert "sell" in envelope["actions"]
        assert envelope["max_qty"] >= 50

    def test_short_only_with_margin(self) -> None:
        cash_state = PortfolioState(cash_inr=100_000.0, margin_multiplier=1.0)
        margin_state = PortfolioState(cash_inr=100_000.0, margin_multiplier=3.0)
        cash_allowed = compute_allowed_actions(
            portfolio_state=cash_state, tickers=["X"], prices={"X": 100.0}
        )
        margin_allowed = compute_allowed_actions(
            portfolio_state=margin_state, tickers=["X"], prices={"X": 100.0}
        )
        assert "short" not in cash_allowed["X"]["actions"]
        assert "short" in margin_allowed["X"]["actions"]

    def test_zero_price_returns_hold_only(self) -> None:
        state = PortfolioState(cash_inr=100_000.0)
        allowed = compute_allowed_actions(
            portfolio_state=state, tickers=["ZZZ"], prices={"ZZZ": 0.0}
        )
        assert allowed["ZZZ"]["actions"] == ["hold"]
        assert allowed["ZZZ"]["max_qty"] == 0


# ---------------------------------------------------------------------------
# Aggregator integration (LLM mocked)
# ---------------------------------------------------------------------------


@dataclass
class _FakeAdvisor:
    """Minimal stand-in for ``PortfolioAdvisor`` — exposes only ``ask``."""

    payload: dict[str, Any]

    async def ask(self, question: str, context: PortfolioContext) -> AdvisorResponse:  # noqa: D401
        body = json.dumps(self.payload)
        return AdvisorResponse(answer=body, confidence=0.8)


class TestSignalAggregator:
    @pytest.mark.asyncio
    async def test_prefills_hold_for_zero_envelope(self) -> None:
        signals = {
            "ILLIQUID": {
                "buffett": {"signal": "bearish", "confidence": 70},
            }
        }
        state = PortfolioState(cash_inr=0.0)
        aggregator = SignalAggregator(advisor=_FakeAdvisor(payload={}))
        result = await aggregator.aggregate(
            signals=signals,
            portfolio_state=state,
            context=_context(),
            prices={"ILLIQUID": 1.0},
        )
        assert len(result.decisions) == 1
        assert result.decisions[0].action == "hold"

    @pytest.mark.asyncio
    async def test_merges_llm_decisions(self) -> None:
        signals = {
            "RELIANCE": {
                "buffett": {"signal": "bullish", "confidence": 80},
                "regime_trader": {"signal": "bullish", "confidence": 65},
            }
        }
        state = PortfolioState(cash_inr=1_000_000.0)
        llm_payload = {
            "answer": "ok",
            "recommended_actions": [],
            "risk_level": "Medium",
            "confidence": 0.7,
            "sources": [],
            "decisions": {
                "RELIANCE": {
                    "action": "buy",
                    "quantity": 10,
                    "confidence": 80,
                    "reasoning": "Quality + regime tailwind.",
                }
            },
        }
        aggregator = SignalAggregator(advisor=_FakeAdvisor(payload=llm_payload))
        result = await aggregator.aggregate(
            signals=signals,
            portfolio_state=state,
            context=_context(),
            prices={"RELIANCE": 2_500.0},
        )
        assert len(result.decisions) == 1
        d = result.decisions[0]
        assert d.action == "buy"
        assert d.quantity == 10
        assert d.confidence == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_unknown_action_falls_back_to_hold(self) -> None:
        signals = {"X": {"agent": {"signal": "neutral", "confidence": 50}}}
        state = PortfolioState(cash_inr=100_000.0)
        llm_payload = {
            "answer": "ok",
            "recommended_actions": [],
            "risk_level": "Medium",
            "confidence": 0.5,
            "sources": [],
            "decisions": {
                "X": {"action": "yolo", "quantity": 50, "confidence": 99},
            },
        }
        aggregator = SignalAggregator(advisor=_FakeAdvisor(payload=llm_payload))
        result = await aggregator.aggregate(
            signals=signals,
            portfolio_state=state,
            context=_context(),
            prices={"X": 100.0},
        )
        assert result.decisions[0].action == "hold"
        assert result.decisions[0].quantity == 0
