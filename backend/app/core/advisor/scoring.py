"""Composite scoring engine.

Combines four components into a 0..100 composite score:
- fundamental (ROCE/ROE, EPS growth, PE-vs-sector)
- technical   (EMA trend + VCP)
- momentum    (52-week, 3-month price performance)
- llm         (qualitative edge from concall / RHP summarization)

Weights reflect the transcript: technical + momentum matter most for a
trend-follower, fundamentals act as a filter, LLM is a tie-breaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.advisor.indicators import detect_vcp, ema_trend_score, roc


@dataclass
class StockSnapshot:
    symbol: str
    exchange: str = "NSE"
    last_price: float = 0.0
    closes: list[float] = field(default_factory=list)  # daily closes oldest -> newest
    roce: float | None = None      # %
    roe: float | None = None       # %
    eps_growth_yoy: float | None = None  # %
    pe_ratio: float | None = None
    sector_median_pe: float | None = None
    sector: str | None = None
    is_recent_ipo: bool = False
    market_cap_cr: float | None = None


@dataclass
class ComponentScores:
    fundamental: float = 0.0
    technical: float = 0.0
    momentum: float = 0.0
    llm: float | None = None
    composite: float = 0.0
    tier: str = "C"
    features: dict[str, Any] = field(default_factory=dict)


def score_fundamental(s: StockSnapshot) -> tuple[float, dict[str, Any]]:
    score = 0.0
    feats: dict[str, Any] = {}
    if s.roce is not None:
        feats["roce"] = s.roce
        if s.roce >= 20: score += 25
        elif s.roce >= 15: score += 15
        elif s.roce >= 10: score += 7
    if s.roe is not None:
        feats["roe"] = s.roe
        if s.roe >= 20: score += 20
        elif s.roe >= 15: score += 12
        elif s.roe >= 10: score += 5
    if s.eps_growth_yoy is not None:
        feats["eps_growth_yoy"] = s.eps_growth_yoy
        if s.eps_growth_yoy >= 30: score += 25
        elif s.eps_growth_yoy >= 15: score += 15
        elif s.eps_growth_yoy >= 5: score += 7
    if s.pe_ratio is not None and s.sector_median_pe:
        rel = s.pe_ratio / s.sector_median_pe if s.sector_median_pe > 0 else None
        feats["pe_vs_sector"] = rel
        if rel is not None:
            if rel <= 0.8: score += 20  # cheap vs sector
            elif rel <= 1.2: score += 12
            elif rel <= 1.5: score += 5
    if s.is_recent_ipo:
        feats["is_recent_ipo"] = True
        score += 10  # transcript: IPO trading edge
    return min(100.0, score), feats


def score_technical(s: StockSnapshot) -> tuple[float, dict[str, Any]]:
    if len(s.closes) < 70:
        return 0.0, {"reason": "insufficient_history"}
    trend = ema_trend_score(s.closes)
    vcp = detect_vcp(s.closes, window=60)
    bonus = 0.0
    if vcp.is_vcp: bonus += 15
    if vcp.breakout: bonus += 10
    bonus += vcp.tightness * 10
    raw = trend * 0.65 + bonus
    return min(100.0, raw), {
        "ema_trend": trend,
        "vcp_is_vcp": vcp.is_vcp,
        "vcp_contractions": vcp.contractions,
        "vcp_tightness": round(vcp.tightness, 3),
        "vcp_breakout": vcp.breakout,
        "pivot_high": vcp.pivot_high,
    }


def score_momentum(s: StockSnapshot) -> tuple[float, dict[str, Any]]:
    if len(s.closes) < 252:
        r3m = roc(s.closes, 63)
        r12m = None
    else:
        r3m = roc(s.closes, 63)
        r12m = roc(s.closes, 252)
    score = 0.0
    if r3m is not None:
        if r3m >= 30: score += 40
        elif r3m >= 15: score += 25
        elif r3m >= 5: score += 10
        elif r3m <= -10: score -= 10
    if r12m is not None:
        if r12m >= 50: score += 40
        elif r12m >= 25: score += 25
        elif r12m >= 10: score += 10
        elif r12m <= -10: score -= 10
    # New all-time high near the recent bar = "leadership" per transcript.
    if s.closes and s.closes[-1] >= max(s.closes) * 0.98:
        score += 20
    return max(0.0, min(100.0, score)), {"roc_3m": r3m, "roc_12m": r12m}


def composite(
    fundamental: float,
    technical: float,
    momentum: float,
    llm: float | None,
    macro_aggressive: bool,
) -> float:
    # Weights: technical 35%, momentum 30%, fundamental 25%, LLM 10% (or 0 if absent).
    if llm is not None:
        raw = technical * 0.35 + momentum * 0.30 + fundamental * 0.25 + llm * 0.10
    else:
        raw = technical * 0.40 + momentum * 0.33 + fundamental * 0.27
    # Macro gate: in defensive regime, halve anything below 70.
    if not macro_aggressive and raw < 70:
        raw *= 0.75
    return round(raw, 2)


def tier_for(score: float) -> str:
    if score >= 80: return "S"
    if score >= 65: return "A"
    if score >= 50: return "B"
    return "C"


def score_snapshot(
    s: StockSnapshot, *, llm: float | None = None, macro_aggressive: bool = True,
) -> ComponentScores:
    f_s, f_feat = score_fundamental(s)
    t_s, t_feat = score_technical(s)
    m_s, m_feat = score_momentum(s)
    comp = composite(f_s, t_s, m_s, llm, macro_aggressive)
    return ComponentScores(
        fundamental=f_s,
        technical=t_s,
        momentum=m_s,
        llm=llm,
        composite=comp,
        tier=tier_for(comp),
        features={**f_feat, **t_feat, **m_feat},
    )
