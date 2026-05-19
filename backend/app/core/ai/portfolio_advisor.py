"""AI-powered portfolio advisor using Claude API.

Provides:
  1. Natural language Q&A about the portfolio
  2. Regime-aware rebalancing suggestions
  3. Multibagger candidate evaluation
  4. Risk assessment and action recommendations

Uses claude-sonnet-4-6 with prompt caching on the system context.
System prompt includes: current regime, sentiment score, portfolio state, risk limits.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import anthropic

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS_QA = 1024
_MAX_TOKENS_BRIEFING = 2048
_MAX_TOKENS_EVALUATE = 1536

# Risk-limit constants (SEBI / DRUVA platform defaults)
_MAX_POSITION_PCT = 10.0
_MAX_SECTOR_PCT = 30.0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PortfolioContext:
    """Snapshot of the user's portfolio and market conditions."""

    regime: str
    """Current macro regime: Crash / Bear / Neutral / Bull / Euphoria."""

    confidence: float
    """Regime model confidence [0, 1]."""

    sentiment_score: float
    """Composite sentiment score [-100, +100]."""

    sentiment_label: str
    """Human-readable sentiment label (e.g. 'Fear', 'Greed')."""

    total_value: float
    """Portfolio total value in INR."""

    positions: list[dict[str, Any]]
    """List of current positions. Each dict has: symbol, exchange, qty, avg_cost, ltp, pnl_pct."""

    cash_pct: float
    """Cash as a percentage of total portfolio value [0, 100]."""

    daily_pnl_pct: float
    """Today's P&L as a percentage of portfolio value."""

    top_holdings: list[dict[str, Any]]
    """Top 5 holdings by weight. Each dict: symbol, weight_pct, pnl_pct."""


@dataclass
class AdvisorResponse:
    """Structured response from the AI portfolio advisor."""

    answer: str
    """Primary natural-language response text."""

    recommended_actions: list[str] = field(default_factory=list)
    """Bulleted list of concrete action items."""

    risk_level: str = "Medium"
    """Overall risk assessment: Low / Medium / High."""

    confidence: float = 0.75
    """Model's self-assessed confidence in the response [0, 1]."""

    sources: list[str] = field(default_factory=list)
    """Data sources / signals used (e.g. 'India VIX', 'FII activity')."""


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------


class PortfolioAdvisor:
    """Conversational AI advisor backed by Claude claude-sonnet-4-6.

    Each method constructs a tailored prompt, calls the Anthropic messages API
    with prompt-caching enabled on the system message, and parses the response
    into a structured AdvisorResponse.

    Usage::

        advisor = PortfolioAdvisor()
        response = await advisor.ask("Should I add more HDFC Bank?", context)
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set and no api_key was provided."
            )
        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def ask(self, question: str, context: PortfolioContext) -> AdvisorResponse:
        """Answer a free-form portfolio question using the current market context.

        Args:
            question: The user's natural-language question.
            context:  Current portfolio and market snapshot.

        Returns:
            AdvisorResponse with the answer and optional action items.
        """
        logger.info("portfolio_advisor.ask", question_len=len(question), regime=context.regime)

        system_blocks = self._build_system_prompt_blocks(context)
        user_content = (
            f"User question: {question}\n\n"
            "Please respond in JSON with this exact schema:\n"
            "{\n"
            '  "answer": "<main response text>",\n'
            '  "recommended_actions": ["<action 1>", ...],\n'
            '  "risk_level": "Low|Medium|High",\n'
            '  "confidence": <float 0-1>,\n'
            '  "sources": ["<source 1>", ...]\n'
            "}"
        )

        raw = await self._call_api(
            system_blocks=system_blocks,
            user_content=user_content,
            max_tokens=_MAX_TOKENS_QA,
        )
        return self._parse_response(raw)

    async def suggest_rebalance(self, context: PortfolioContext) -> AdvisorResponse:
        """Generate regime-aware rebalancing suggestions for the current portfolio.

        The advisor considers the current macro regime, sentiment score, and
        individual position weights to produce specific buy/reduce/hold actions.

        Args:
            context: Current portfolio and market snapshot.

        Returns:
            AdvisorResponse with concrete rebalancing actions.
        """
        logger.info(
            "portfolio_advisor.suggest_rebalance",
            regime=context.regime,
            positions=len(context.positions),
        )

        system_blocks = self._build_system_prompt_blocks(context)
        user_content = (
            "Task: Suggest a portfolio rebalancing plan based on the current macro regime, "
            "sentiment conditions, and existing positions. "
            "Consider SEBI regulations, T+1 settlement, and circuit-limit risks on small-caps.\n\n"
            "Respond in JSON with this schema:\n"
            "{\n"
            '  "answer": "<summary of rebalancing rationale>",\n'
            '  "recommended_actions": [\n'
            '    "<specific action: BUY/SELL/REDUCE/HOLD symbol and why>",\n'
            "    ...\n"
            "  ],\n"
            '  "risk_level": "Low|Medium|High",\n'
            '  "confidence": <float 0-1>,\n'
            '  "sources": ["<signal or data used>", ...]\n'
            "}"
        )

        raw = await self._call_api(
            system_blocks=system_blocks,
            user_content=user_content,
            max_tokens=_MAX_TOKENS_QA,
        )
        return self._parse_response(raw)

    async def evaluate_stock(
        self,
        symbol: str,
        fundamentals: dict[str, Any],
        context: PortfolioContext,
    ) -> AdvisorResponse:
        """Evaluate a stock for portfolio fit given current regime and portfolio state.

        Args:
            symbol:       NSE/BSE ticker symbol (e.g. "RELIANCE").
            fundamentals: Dict of fundamental metrics (P/E, ROCE, EPS growth, etc.).
            context:      Current portfolio and market snapshot.

        Returns:
            AdvisorResponse with buy/hold/avoid recommendation and reasoning.
        """
        logger.info(
            "portfolio_advisor.evaluate_stock",
            symbol=symbol,
            regime=context.regime,
        )

        system_blocks = self._build_system_prompt_blocks(context)
        fund_str = json.dumps(fundamentals, indent=2) if fundamentals else "{}"
        user_content = (
            f"Task: Evaluate {symbol} for potential inclusion in the portfolio.\n\n"
            f"Available fundamental data:\n```json\n{fund_str}\n```\n\n"
            "Assess: valuation, quality (ROCE, debt), momentum fit, sector concentration risk, "
            "and alignment with current macro regime. Apply SEBI position-sizing rules.\n\n"
            "Respond in JSON:\n"
            "{\n"
            '  "answer": "<BUY/HOLD/AVOID + detailed rationale>",\n'
            '  "recommended_actions": ["<specific step if any>", ...],\n'
            '  "risk_level": "Low|Medium|High",\n'
            '  "confidence": <float 0-1>,\n'
            '  "sources": ["<data point used>", ...]\n'
            "}"
        )

        raw = await self._call_api(
            system_blocks=system_blocks,
            user_content=user_content,
            max_tokens=_MAX_TOKENS_EVALUATE,
        )
        return self._parse_response(raw)

    async def daily_briefing(self, context: PortfolioContext) -> str:
        """Generate a concise daily market briefing as 3-5 bullet points.

        Covers: market regime, sentiment, FII/DII activity, NIFTY trend,
        portfolio performance, and key watch items for the day.

        Args:
            context: Current portfolio and market snapshot.

        Returns:
            A Markdown-formatted string with 3-5 bullet points.
        """
        logger.info(
            "portfolio_advisor.daily_briefing",
            regime=context.regime,
            sentiment_score=context.sentiment_score,
        )

        system_blocks = self._build_system_prompt_blocks(context)
        user_content = (
            "Task: Write a concise daily market briefing for the portfolio manager.\n"
            "Format: 3 to 5 Markdown bullet points.\n"
            "Cover: market regime assessment, sentiment reading, FII/DII implication, "
            "top portfolio movers, and one specific watch item for today.\n"
            "Keep each bullet under 25 words. Be direct, data-driven, and actionable.\n"
            "Do NOT include JSON — respond with plain Markdown bullet points only."
        )

        raw = await self._call_api(
            system_blocks=system_blocks,
            user_content=user_content,
            max_tokens=_MAX_TOKENS_BRIEFING,
        )
        return raw.strip()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt_blocks(self, context: PortfolioContext) -> list[dict[str, Any]]:
        """Build the Anthropic messages-API system content blocks.

        The large contextual system prompt is marked with cache_control so that
        repeated calls with the same portfolio snapshot hit the prompt cache
        and reduce latency and cost.
        """
        prompt_text = self._build_system_prompt(context)
        return [
            {
                "type": "text",
                "text": prompt_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _build_system_prompt(self, context: PortfolioContext) -> str:
        """Build a rich system prompt embedding all portfolio and market context."""
        import datetime as _dt
        ist_offset = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
        ist_now = datetime.now(timezone.utc).astimezone(ist_offset)
        date_str = ist_now.strftime("%A, %d %B %Y %H:%M IST")

        if context.positions:
            positions_lines = []
            for p in context.positions:
                symbol = p.get("symbol", "?")
                exchange = p.get("exchange", "NSE")
                qty = p.get("qty", 0)
                avg_cost = p.get("avg_cost", 0.0)
                ltp = p.get("ltp", 0.0)
                pnl_pct = p.get("pnl_pct", 0.0)
                positions_lines.append(
                    f"  • {symbol} ({exchange}): qty={qty}, avg_cost=₹{avg_cost:,.2f}, "
                    f"ltp=₹{ltp:,.2f}, pnl={pnl_pct:+.1f}%"
                )
            positions_str = "\n".join(positions_lines)
        else:
            positions_str = "  (no open positions)"

        if context.top_holdings:
            holdings_lines = [
                f"  • {h.get('symbol', '?')}: {h.get('weight_pct', 0):.1f}% of portfolio, "
                f"pnl={h.get('pnl_pct', 0):+.1f}%"
                for h in context.top_holdings
            ]
            holdings_str = "\n".join(holdings_lines)
        else:
            holdings_str = "  (none)"

        return (
            "You are DRUVA's AI Portfolio Advisor — an expert in Indian equity markets (NSE/BSE).\n\n"
            "## Platform Context\n"
            f"- Platform: DRUVA Algo-Trading System (Indian markets only)\n"
            f"- Date/Time: {date_str}\n"
            "- Exchanges: NSE, BSE (equities & derivatives)\n"
            "- Settlement: T+1 (SEBI mandate, effective 2023)\n"
            "- Market hours: 09:15 – 15:30 IST (Monday–Friday)\n\n"
            "## Regulatory & Risk Framework\n"
            f"- Max single-position size: {_MAX_POSITION_PCT}% of portfolio value (DRUVA risk limit)\n"
            f"- Max sector concentration: {_MAX_SECTOR_PCT}% of portfolio value (DRUVA risk limit)\n"
            "- SEBI Insider Trading Regulations apply\n"
            "- Circuit limits: ±5% / ±10% / ±20% depending on stock category\n"
            "- F&O positions carry additional SEBI margin requirements\n"
            "- LTCG (>1 yr) taxed at 10% above ₹1L; STCG at 15% (FY 2024-25)\n\n"
            "## Current Market Regime\n"
            f"- Regime: {context.regime}\n"
            f"- Regime confidence: {context.confidence * 100:.1f}%\n"
            "- Source: HMM model trained on NSE/BSE price history\n\n"
            "## Sentiment Dashboard\n"
            f"- Composite sentiment: {context.sentiment_score:+.1f} / 100 ({context.sentiment_label})\n"
            "  (Scale: -100 = Extreme Fear, 0 = Neutral, +100 = Extreme Greed)\n\n"
            "## Portfolio State\n"
            f"- Total value: ₹{context.total_value:,.0f}\n"
            f"- Cash / liquid: {context.cash_pct:.1f}%\n"
            f"- Today's P&L: {context.daily_pnl_pct:+.2f}%\n\n"
            "### Open Positions\n"
            f"{positions_str}\n\n"
            "### Top Holdings by Weight\n"
            f"{holdings_str}\n\n"
            "## Advisory Guidelines\n"
            "1. Ground all recommendations in the regime and sentiment data above.\n"
            "2. Respect 10% single-stock and 30% sector concentration limits.\n"
            "3. Bear/Crash: preserve capital; favour cash, gold ETFs, defensive large-caps.\n"
            "4. Bull/Euphoria: deploy cautiously; watch for overbought signals.\n"
            "5. Flag trades that may breach circuit limits or need intra-day square-off.\n"
            "6. Mention T+1 implications when same-day proceeds are discussed.\n"
            "7. Do not give tax advice; recommend consulting a CA.\n"
            "8. Disclaimer: This is NOT SEBI-registered investment advice.\n\n"
            "Respond concisely, factually, and with quantified reasoning wherever possible."
        )

    async def _call_api(
        self,
        *,
        system_blocks: list[dict[str, Any]],
        user_content: str,
        max_tokens: int,
    ) -> str:
        """Call the Anthropic Messages API with prompt caching on the system blocks.

        Returns the raw text content of the first text block in the response.
        Raises anthropic.APIError subclasses on failure.
        """
        message = await self._client.beta.prompt_caching.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,  # type: ignore[arg-type]
            messages=[{"role": "user", "content": user_content}],
        )
        usage = getattr(message, "usage", None)
        if usage:
            logger.info(
                "portfolio_advisor.api_call",
                model=_MODEL,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                cache_read=getattr(usage, "cache_read_input_tokens", None),
                cache_write=getattr(usage, "cache_creation_input_tokens", None),
            )

        for block in message.content:
            if block.type == "text":
                return block.text

        return ""

    def _parse_response(self, raw: str) -> AdvisorResponse:
        """Extract a structured AdvisorResponse from the raw Claude response.

        Claude is instructed to reply in JSON. We try to parse the JSON block
        first; if that fails we fall back to using the raw text as the answer
        with default values for the structured fields.
        """
        # Try to extract JSON from the response (may be wrapped in markdown)
        json_data = _extract_json(raw)
        if json_data:
            return AdvisorResponse(
                answer=str(json_data.get("answer", raw)),
                recommended_actions=list(json_data.get("recommended_actions", [])),
                risk_level=str(json_data.get("risk_level", "Medium")),
                confidence=float(json_data.get("confidence", 0.75)),
                sources=list(json_data.get("sources", [])),
            )

        # Fallback: treat full raw text as the answer
        logger.warning("portfolio_advisor.json_parse_failed", raw_len=len(raw))
        return AdvisorResponse(
            answer=raw,
            recommended_actions=[],
            risk_level="Medium",
            confidence=0.5,
            sources=[],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first well-formed JSON object from a string.

    Handles responses wrapped in markdown code fences (```json ... ```) and
    bare JSON objects anywhere in the text.
    """
    if not text:
        return None

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Scan for first balanced {...} block
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
