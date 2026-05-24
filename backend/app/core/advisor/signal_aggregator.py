"""Aggregate multi-source signals into a single trading verdict via the LLM.

Adapted from virattt/ai-hedge-fund (MIT) portfolio-manager agent. The idea:

  • Many DRUVA strategies and persona agents emit ``(signal, confidence)`` pairs
    per ticker. Feeding raw blobs into the LLM wastes tokens and confuses it.
  • Compact the signals to the smallest JSON shape that preserves intent.
  • Compute the *deterministic* envelope of allowed actions (cash, margin,
    position-cap limits) outside the LLM — the LLM only picks within that
    envelope.
  • Ask the LLM for a single ``PortfolioDecision`` per ticker plus a
    rationale.

Usage::

    aggregator = SignalAggregator(advisor=PortfolioAdvisor())
    decision = await aggregator.aggregate(
        signals={"RELIANCE": {"buffett": {...}, "regime_trader": {...}}},
        portfolio_state=PortfolioState(cash=..., positions=[...], ...),
        context=PortfolioContext(...),
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.ai.portfolio_advisor import PortfolioAdvisor, PortfolioContext
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class PortfolioState:
    """Snapshot of cash and per-ticker exposure used to compute allowed actions."""

    cash_inr: float
    """Liquid INR available for new buys."""

    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    """``{symbol: {"quantity": int, "avg_cost": float, "ltp": float}}``."""

    max_single_position_pct: float = 10.0
    """Hard cap per name (DRUVA default 10%)."""

    margin_multiplier: float = 1.0
    """1.0 = cash only. 5.0 = 5x intraday MTF, etc."""


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


VALID_ACTIONS = ("buy", "sell", "short", "cover", "hold")


@dataclass(frozen=True)
class TickerDecision:
    ticker: str
    action: str            # one of VALID_ACTIONS
    quantity: int          # 0 for hold
    confidence: float      # 0..100
    reasoning: str


@dataclass(frozen=True)
class AggregateDecision:
    decisions: list[TickerDecision]
    raw_response: str
    allowed_actions: dict[str, dict[str, Any]]


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class SignalAggregator:
    """Combines compact agent signals + deterministic guards into one decision."""

    def __init__(self, advisor: PortfolioAdvisor) -> None:
        self._advisor = advisor

    # ---- Public ----------------------------------------------------------

    async def aggregate(
        self,
        *,
        signals: dict[str, dict[str, dict[str, Any]]],
        portfolio_state: PortfolioState,
        context: PortfolioContext,
        prices: dict[str, float] | None = None,
    ) -> AggregateDecision:
        """Fuse per-agent signals into a single per-ticker decision set.

        ``signals`` shape::

            {
                "RELIANCE": {
                    "buffett":        {"signal": "bullish", "confidence": 80, "reasoning": "..."},
                    "regime_trader":  {"signal": "neutral", "confidence": 55, ...},
                    "vwap_scalper":   {"signal": "bearish", "confidence": 30, ...},
                },
                ...
            }

        ``prices`` is an optional ``{symbol: price}`` map used to translate INR
        caps into share quantities — when omitted, ``signals`` should already
        contain ``"price"`` in any of the inner dicts.
        """
        tickers = list(signals.keys())
        compact = compact_signals(signals)
        allowed = compute_allowed_actions(
            portfolio_state=portfolio_state,
            tickers=tickers,
            prices=_resolve_prices(signals, prices),
        )

        # Pre-fill HOLDs for tickers with zero allowed quantity across the
        # board — no point spending LLM tokens on them.
        prefilled, to_decide = _prefill_holds(allowed, tickers)
        if not to_decide:
            return AggregateDecision(
                decisions=list(prefilled.values()),
                raw_response="",
                allowed_actions=allowed,
            )

        question = self._render_prompt(
            tickers=to_decide,
            compact=compact,
            allowed=allowed,
        )
        response = await self._advisor.ask(question, context)
        decisions = _merge_decisions(prefilled, response.answer, to_decide)
        return AggregateDecision(
            decisions=decisions,
            raw_response=response.answer,
            allowed_actions=allowed,
        )

    # ---- Internal --------------------------------------------------------

    def _render_prompt(
        self,
        *,
        tickers: list[str],
        compact: dict[str, dict[str, dict[str, Any]]],
        allowed: dict[str, dict[str, Any]],
    ) -> str:
        sub_compact = {t: compact[t] for t in tickers if t in compact}
        sub_allowed = {t: allowed[t] for t in tickers if t in allowed}
        return (
            "You are DRUVA's signal aggregator. Below are compact agent signals "
            "and the *deterministic* allowed actions per ticker (already adjusted "
            "for cash, margin and the 10% single-name cap). You MUST stay inside "
            "the allowed envelope — never exceed ``max_qty`` and never propose an "
            "action not present in ``actions``.\n\n"
            f"Signals:\n```json\n{json.dumps(sub_compact, indent=2)}\n```\n\n"
            f"Allowed actions:\n```json\n{json.dumps(sub_allowed, indent=2)}\n```\n\n"
            "Respond with JSON only, no prose around it, exactly:\n"
            "{\n"
            '  "answer": "<one-sentence rationale across all tickers>",\n'
            '  "recommended_actions": [],\n'
            '  "risk_level": "Low|Medium|High",\n'
            '  "confidence": <0-1>,\n'
            '  "sources": [],\n'
            '  "decisions": {\n'
            '    "<TICKER>": {\n'
            '      "action": "buy|sell|short|cover|hold",\n'
            '      "quantity": <int >= 0>,\n'
            '      "confidence": <0-100>,\n'
            '      "reasoning": "<short>"\n'
            "    }, ...\n"
            "  }\n"
            "}"
        )


# ---------------------------------------------------------------------------
# Public helpers — exported for unit tests + reuse from other modules
# ---------------------------------------------------------------------------


def compact_signals(
    signals: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Drop everything except ``signal``, ``confidence`` and ``reasoning``."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for ticker, agents in signals.items():
        per_ticker: dict[str, dict[str, Any]] = {}
        for agent, payload in agents.items():
            if not isinstance(payload, dict):
                continue
            entry: dict[str, Any] = {}
            if "signal" in payload:
                entry["signal"] = payload["signal"]
            if "confidence" in payload:
                entry["confidence"] = payload["confidence"]
            # Keep a tiny reasoning hint (truncated) — useful for the LLM.
            reasoning = payload.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                entry["reasoning"] = reasoning[:240]
            if entry:
                per_ticker[agent] = entry
        if per_ticker:
            out[ticker] = per_ticker
    return out


def compute_allowed_actions(
    *,
    portfolio_state: PortfolioState,
    tickers: list[str],
    prices: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """Return the deterministic envelope of trades the LLM may pick from.

    Each value is::

        {
            "actions": ["buy", "hold", ...],
            "max_qty": int,
            "current_qty": int,
            "single_position_cap_inr": float,
            "remaining_room_inr": float,
        }
    """
    portfolio_value = portfolio_state.cash_inr + sum(
        (pos.get("quantity", 0) or 0) * (pos.get("ltp", 0.0) or 0.0)
        for pos in portfolio_state.positions.values()
    )
    cap_inr = portfolio_state.max_single_position_pct / 100.0 * portfolio_value
    margin = max(1.0, portfolio_state.margin_multiplier)
    buying_power = portfolio_state.cash_inr * margin

    out: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        pos = portfolio_state.positions.get(ticker, {})
        current_qty = int(pos.get("quantity", 0) or 0)
        price = float(prices.get(ticker, pos.get("ltp", 0.0) or 0.0))
        position_value = current_qty * (pos.get("ltp", price) or price)
        room = max(cap_inr - max(position_value, 0.0), 0.0)

        actions: list[str] = ["hold"]
        max_qty = 0
        if price > 0:
            # BUY — limited by min(room, buying_power).
            buy_cap = min(room, buying_power)
            buy_qty = int(buy_cap // price) if buy_cap > 0 else 0
            if buy_qty > 0:
                actions.append("buy")
                max_qty = max(max_qty, buy_qty)
            # SELL — only if we hold the name.
            if current_qty > 0:
                actions.append("sell")
                max_qty = max(max_qty, current_qty)
            # SHORT / COVER — only when margin > 1, mirrors ai-hedge-fund.
            if margin > 1.0:
                short_qty = int(buying_power // price)
                if short_qty > 0 and current_qty <= 0:
                    actions.append("short")
                    max_qty = max(max_qty, short_qty)
                if current_qty < 0:
                    actions.append("cover")
                    max_qty = max(max_qty, -current_qty)

        out[ticker] = {
            "actions": actions,
            "max_qty": max_qty,
            "current_qty": current_qty,
            "single_position_cap_inr": round(cap_inr, 2),
            "remaining_room_inr": round(room, 2),
            "price": round(price, 4),
        }
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_prices(
    signals: dict[str, dict[str, dict[str, Any]]],
    explicit_prices: dict[str, float] | None,
) -> dict[str, float]:
    if explicit_prices:
        return dict(explicit_prices)
    prices: dict[str, float] = {}
    for ticker, agents in signals.items():
        for payload in agents.values():
            if isinstance(payload, dict) and "price" in payload:
                try:
                    prices[ticker] = float(payload["price"])
                    break
                except (TypeError, ValueError):
                    continue
    return prices


def _prefill_holds(
    allowed: dict[str, dict[str, Any]], tickers: list[str]
) -> tuple[dict[str, TickerDecision], list[str]]:
    prefilled: dict[str, TickerDecision] = {}
    to_decide: list[str] = []
    for ticker in tickers:
        envelope = allowed.get(ticker)
        if envelope is None or envelope.get("max_qty", 0) == 0:
            prefilled[ticker] = TickerDecision(
                ticker=ticker,
                action="hold",
                quantity=0,
                confidence=0.0,
                reasoning="No allowed action (cap or cash exhausted).",
            )
        else:
            to_decide.append(ticker)
    return prefilled, to_decide


def _merge_decisions(
    prefilled: dict[str, TickerDecision], raw_answer: str, expected: list[str]
) -> list[TickerDecision]:
    """Parse the LLM's nested ``decisions`` dict and merge with prefilled holds."""
    parsed = _extract_decisions_block(raw_answer)
    out: dict[str, TickerDecision] = dict(prefilled)
    for ticker in expected:
        entry = parsed.get(ticker)
        if not isinstance(entry, dict):
            out[ticker] = TickerDecision(
                ticker=ticker,
                action="hold",
                quantity=0,
                confidence=0.0,
                reasoning="LLM returned no decision for this ticker; defaulting to hold.",
            )
            continue
        action = str(entry.get("action", "hold")).lower()
        if action not in VALID_ACTIONS:
            action = "hold"
        try:
            qty = max(0, int(entry.get("quantity", 0) or 0))
        except (TypeError, ValueError):
            qty = 0
        try:
            conf = max(0.0, min(100.0, float(entry.get("confidence", 0) or 0)))
        except (TypeError, ValueError):
            conf = 0.0
        out[ticker] = TickerDecision(
            ticker=ticker,
            action=action,
            quantity=qty if action != "hold" else 0,
            confidence=conf,
            reasoning=str(entry.get("reasoning", "")),
        )
    # Preserve input order.
    return [out[t] for t in expected if t in out] + [
        out[t] for t in out if t not in expected
    ]


def _extract_decisions_block(text: str) -> dict[str, Any]:
    """Best-effort decode of the ``decisions`` key from the LLM's JSON answer.

    Returns an empty dict if the response can't be parsed.
    """
    if not text:
        return {}
    # Try a direct decode first.
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if obj is None:
        # Strip markdown fences.
        start = text.find("{")
        if start < 0:
            return {}
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            return {}
        try:
            obj = json.loads(text[start:end])
        except json.JSONDecodeError:
            return {}
    if isinstance(obj, dict):
        decisions = obj.get("decisions")
        if isinstance(decisions, dict):
            return decisions
    return {}
