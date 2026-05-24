"""Council mode — fan a question out to multiple investor personas in parallel.

The Council layer sits on top of ``PortfolioAdvisor`` and ``Persona``. It does
two things:

  • ``ask_as`` — run a single persona over a question; returns a
    ``PersonaSignal`` plus the underlying ``AdvisorResponse`` for prose.
  • ``run_council`` — fan out to N personas, collect signals, and synthesise
    a consensus verdict using simple confidence-weighted voting.

The synthesis is deterministic (no extra LLM round-trip) — keeps the call
fast and the output explainable. The LLM does the per-persona reasoning;
the math fuses the votes.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.advisor.personas.base import Persona, PersonaSignal, resolve_persona
from app.core.advisor.valuation import (
    FundamentalsProvider,
    FundamentalsView,
    NullFundamentalsProvider,
    three_stage_dcf,
)
from app.core.ai.portfolio_advisor import (
    AdvisorResponse,
    PortfolioAdvisor,
    PortfolioContext,
)
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PersonaVerdict:
    persona: Persona
    signal: PersonaSignal
    raw: AdvisorResponse


@dataclass(frozen=True)
class CouncilVerdict:
    symbol: str
    consensus: str                     # bullish / bearish / neutral
    consensus_confidence: float        # 0..100 weighted average
    vote_distribution: dict[str, int]  # {"bullish": 3, "bearish": 1, "neutral": 1}
    verdicts: list[PersonaVerdict]
    fundamentals: dict[str, Any] = field(default_factory=dict)
    intrinsic_value: dict[str, Any] | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Council
# ---------------------------------------------------------------------------


class Council:
    """Orchestrates persona prompts on top of an existing ``PortfolioAdvisor``."""

    def __init__(
        self,
        advisor: PortfolioAdvisor,
        fundamentals_provider: FundamentalsProvider | None = None,
    ) -> None:
        self._advisor = advisor
        self._fundamentals = fundamentals_provider or NullFundamentalsProvider()

    # ---- Single persona --------------------------------------------------

    async def ask_as(
        self,
        *,
        persona: Persona,
        question: str,
        context: PortfolioContext,
        fundamentals: FundamentalsView | None = None,
    ) -> PersonaVerdict:
        prompt = _render_persona_question(persona, question, fundamentals)
        response = await self._advisor.ask(_persona_overlay(persona, prompt), context)
        signal = _parse_persona_signal(persona.slug, response)
        return PersonaVerdict(persona=persona, signal=signal, raw=response)

    # ---- Council ---------------------------------------------------------

    async def run_council(
        self,
        *,
        symbol: str,
        question: str,
        context: PortfolioContext,
        persona_slugs: list[str] | None = None,
    ) -> CouncilVerdict:
        from app.core.advisor.personas import list_personas

        if persona_slugs:
            personas = [p for p in (resolve_persona(s) for s in persona_slugs) if p is not None]
        else:
            personas = list_personas()
        if not personas:
            raise ValueError("Council requires at least one persona")

        fundamentals = await self._fundamentals.get(symbol)
        dcf = three_stage_dcf(fundamentals) if fundamentals else None

        verdicts = await asyncio.gather(
            *[
                self.ask_as(
                    persona=p,
                    question=question,
                    context=context,
                    fundamentals=fundamentals,
                )
                for p in personas
            ],
            return_exceptions=True,
        )

        clean_verdicts: list[PersonaVerdict] = []
        for v in verdicts:
            if isinstance(v, Exception):
                logger.warning("council.persona_error", error=str(v))
                continue
            clean_verdicts.append(v)

        consensus, confidence, distribution = _synthesise(clean_verdicts)
        return CouncilVerdict(
            symbol=symbol,
            consensus=consensus,
            consensus_confidence=confidence,
            vote_distribution=distribution,
            verdicts=clean_verdicts,
            fundamentals=_fundamentals_to_dict(fundamentals),
            intrinsic_value=_dcf_to_dict(dcf) if dcf else None,
            notes=(
                "Fundamentals unavailable — personas reasoned without DCF inputs."
                if fundamentals is None
                else ""
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persona_overlay(persona: Persona, user_question: str) -> str:
    """Wrap the user question with a per-persona instruction header."""
    return (
        f"You are channelling **{persona.display_name}** ({persona.style}).\n"
        f"{persona.system_prompt}\n\n"
        f"## User question / target\n{user_question}\n\n"
        "Respond with JSON exactly:\n"
        "{\n"
        '  "answer": "<short rationale in the persona\'s voice>",\n'
        '  "recommended_actions": ["<concrete action>", ...],\n'
        '  "risk_level": "Low|Medium|High",\n'
        '  "confidence": <0..1>,\n'
        '  "sources": ["<data point used>", ...],\n'
        '  "persona_signal": {\n'
        '    "signal": "bullish|bearish|neutral",\n'
        '    "confidence": <0..100>,\n'
        '    "reasoning": "<one paragraph>"\n'
        "  }\n"
        "}"
    )


def _render_persona_question(
    persona: Persona,
    question: str,
    fundamentals: FundamentalsView | None,
) -> str:
    parts: list[str] = [question.strip()]
    if fundamentals is not None:
        parts.append("Fundamentals snapshot:")
        parts.append(json.dumps(_fundamentals_to_dict(fundamentals), indent=2, default=str))
    if persona.checklist:
        parts.append("Apply this checklist to your reasoning:")
        for item in persona.checklist:
            parts.append(f"  - {item}")
    return "\n\n".join(parts)


def _parse_persona_signal(slug: str, response: AdvisorResponse) -> PersonaSignal:
    """Try to extract the nested ``persona_signal`` block; fall back gracefully."""
    raw_text = response.answer or ""
    payload = _find_persona_signal_dict(raw_text)
    if payload is None:
        # Fall back: synthesise from risk_level + confidence.
        signal = _infer_signal_from_risk_level(response.risk_level)
        return PersonaSignal(
            signal=signal,
            confidence=int(round((response.confidence or 0.0) * 100)),
            reasoning=raw_text[:600] if raw_text else "Unable to extract structured signal.",
            persona=slug,
        )
    try:
        signal_val = str(payload.get("signal", "neutral")).lower()
        if signal_val not in {"bullish", "bearish", "neutral"}:
            signal_val = "neutral"
        confidence_val = int(round(float(payload.get("confidence", 0))))
        confidence_val = max(0, min(100, confidence_val))
        return PersonaSignal(
            signal=signal_val,                       # type: ignore[arg-type]
            confidence=confidence_val,
            reasoning=str(payload.get("reasoning", "")),
            persona=slug,
        )
    except (TypeError, ValueError) as exc:
        logger.warning("council.persona_signal_parse_error", persona=slug, error=str(exc))
        return PersonaSignal(
            signal="neutral",
            confidence=0,
            reasoning="Persona signal parse failure; defaulting to neutral.",
            persona=slug,
        )


def _find_persona_signal_dict(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # Direct JSON parse first.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("persona_signal"), dict):
            return obj["persona_signal"]
    except json.JSONDecodeError:
        pass
    # Fenced JSON.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict) and isinstance(obj.get("persona_signal"), dict):
                return obj["persona_signal"]
        except json.JSONDecodeError:
            pass
    # Look for an inline ``persona_signal`` object.
    m = re.search(
        r'"persona_signal"\s*:\s*(\{.*?\})\s*(?:,|\})', text, re.DOTALL,
    )
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _infer_signal_from_risk_level(risk_level: str | None) -> str:
    rl = (risk_level or "").lower()
    if rl == "low":
        return "bullish"
    if rl == "high":
        return "bearish"
    return "neutral"


def _synthesise(verdicts: list[PersonaVerdict]) -> tuple[str, float, dict[str, int]]:
    """Confidence-weighted voting across persona signals."""
    if not verdicts:
        return "neutral", 0.0, {"bullish": 0, "bearish": 0, "neutral": 0}
    distribution = {"bullish": 0, "bearish": 0, "neutral": 0}
    weighted = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    total_conf = 0.0
    for v in verdicts:
        sig = v.signal.signal
        conf = float(v.signal.confidence or 0.0)
        distribution[sig] = distribution.get(sig, 0) + 1
        weighted[sig] = weighted.get(sig, 0.0) + conf
        total_conf += conf
    consensus = max(weighted, key=lambda k: weighted[k])
    avg_conf = (total_conf / len(verdicts)) if verdicts else 0.0
    return consensus, round(avg_conf, 2), distribution


def _fundamentals_to_dict(view: FundamentalsView | None) -> dict[str, Any]:
    if view is None:
        return {}
    return {
        "symbol": view.symbol,
        "exchange": view.exchange,
        "as_of": view.as_of.isoformat() if view.as_of else None,
        "market_cap": view.market_cap,
        "current_price": view.current_price,
        "shares_outstanding": view.shares_outstanding,
        "sector": view.sector,
        "industry": view.industry,
        "pe_ratio": view.pe_ratio,
        "pb_ratio": view.pb_ratio,
        "roe": view.roe,
        "roce": view.roce,
        "debt_to_equity": view.debt_to_equity,
        "operating_margin": view.operating_margin,
        "current_ratio": view.current_ratio,
        "promoter_holding": view.promoter_holding,
        "history_years": len(view.net_income) or len(view.free_cash_flow),
        "source": view.source,
    }


def _dcf_to_dict(dcf: Any) -> dict[str, Any]:
    return {
        "intrinsic_value_total": dcf.intrinsic_value_total,
        "intrinsic_value_per_share": dcf.intrinsic_value_per_share,
        "margin_of_safety_pct": dcf.margin_of_safety_pct,
        "owner_earnings": dcf.owner_earnings,
        "maintenance_capex": dcf.maintenance_capex,
        "stage1_pv": dcf.stage1_pv,
        "stage2_pv": dcf.stage2_pv,
        "terminal_pv": dcf.terminal_pv,
        "inputs": dcf.inputs,
        "degraded": dcf.degraded,
    }
