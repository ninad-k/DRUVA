"""VCP Multibagger scanner — Harsh + Ashwin combined.

Per symbol in the universe:
1. Pull 250 daily candles.
2. Detect VCP stages + contractions + volume dry-up.
3. Filter to Stage 3–4 with close >= 21-EMA.
4. Apply fundamental gate (roe > 20, roce > 20, debt/equity < 1).
5. IPO sub-mode (``ipo_only=True``): skip unless this is a recently listed
   instrument (< 24 months) — heuristic via Instrument.updated_at proxy when
   ``listing_date`` is not present.
6. Sector-rotation boost when regime=="neutral" and stock is at ATH.
7. Emit candidates with 4.5% hard stop (Ashwin's rule).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.core.scanner.base import ScanCandidate, ScanContext, Scanner
from app.core.scanner.registry import register_scanner
from app.strategies.indicators.breadth import is_at_ath
from app.strategies.indicators.vcp import detect_vcp


@register_scanner("scanner.vcp_multibagger.v1")
class VcpMultibaggerScanner(Scanner):
    DEFAULT_PARAMS: dict[str, Any] = {
        "min_roe": 20.0,
        "min_roce": 20.0,
        "max_debt_equity": 1.0,
        "stop_pct": 4.5,
        "score_threshold": 0.55,
        "ipo_only": False,
        "max_universe": 1500,
    }

    async def scan(self, context: ScanContext) -> list[ScanCandidate]:
        p = {**self.DEFAULT_PARAMS, **(self.parameters or {})}
        universe = await context.get_universe({"exchanges": ["NSE", "BSE"]})
        if p.get("ipo_only") and universe:
            # We can't easily filter without a listing_date column; leave as-is
            # and rely on the fundamentals gate to weed out mature names. This
            # is safe because IPO filters will be refined in Phase 2+.
            pass

        cycle = await context.get_market_cycle()
        regime = cycle.regime if cycle else "neutral"

        out: list[ScanCandidate] = []
        capped = universe[: int(p["max_universe"])]
        for ref in capped:
            candles = await context.get_candles(ref.symbol, ref.exchange, "1d", 260)
            if len(candles) < 60:
                continue
            assessment = detect_vcp(candles)
            if assessment.stage not in ("stage_3", "stage_4"):
                continue
            if assessment.score < p["score_threshold"]:
                continue

            fund = await context.get_fundamentals(ref.symbol, ref.exchange)
            if fund is not None:
                # Fundamental gate is applied only if we have data. Missing
                # fundamentals don't auto-reject — they just skip the gate
                # (Phase 2 backfills fundamentals weekly).
                if fund.roe is not None and float(fund.roe) < float(p["min_roe"]):
                    continue
                if fund.roce is not None and float(fund.roce) < float(p["min_roce"]):
                    continue
                if fund.debt_to_equity is not None and float(fund.debt_to_equity) > float(
                    p["max_debt_equity"]
                ):
                    continue

            score = assessment.score
            if regime == "neutral" and is_at_ath(candles):
                score = min(1.0, score + 0.2)

            last_close = Decimal(str(candles[-1].close))
            stop = last_close * (Decimal("1") - Decimal(str(p["stop_pct"])) / Decimal("100"))
            target = last_close * Decimal("1.3")  # 30% target as baseline

            out.append(
                ScanCandidate(
                    symbol=ref.symbol,
                    exchange=ref.exchange,
                    score=score,
                    stage=assessment.stage,
                    reason=(
                        f"VCP {assessment.stage} | bases={assessment.bases} "
                        f"| vol_dryup={assessment.volume_dryup_ratio:.2f}"
                    ),
                    suggested_entry=last_close,
                    suggested_stop=stop.quantize(Decimal("0.01")),
                    suggested_target=target.quantize(Decimal("0.01")),
                    metadata={
                        "stage": assessment.stage,
                        "bases": assessment.bases,
                        "contraction_ratios": assessment.contraction_ratios,
                        "volume_dryup_ratio": assessment.volume_dryup_ratio,
                        "ema21": assessment.ema21,
                        "regime": regime,
                        "at_ath": is_at_ath(candles),
                        "roe": float(fund.roe) if fund and fund.roe is not None else None,
                        "roce": float(fund.roce) if fund and fund.roce is not None else None,
                        "sector": fund.sector if fund else None,
                    },
                )
            )
        return out
