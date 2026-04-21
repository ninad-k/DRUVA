"""Market-cycle regime controller (Strategy 1 — Harsh).

Not a stock picker. Each daily run computes Nifty 18m / SmallCap 20m ROC,
classifies regime, and upserts today's ``MarketCycleState`` row. Emits one
synthetic ``__PORTFOLIO__`` candidate so the UI can surface a banner.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scanner.base import ScanCandidate, ScanContext, Scanner
from app.core.scanner.market_cycle import MarketCycleRegimeDetector
from app.core.scanner.registry import register_scanner


@register_scanner("scanner.market_cycle_allocator.v1")
class MarketCycleAllocatorScanner(Scanner):

    async def scan(self, context: ScanContext) -> list[ScanCandidate]:
        # Hack: fish out the session via the runner's internal ctx. We accept
        # only _DbScanContext today, but keeping the dependency loose lets
        # alternate runners (tests, backtests) swap in their own.
        session: AsyncSession = getattr(context, "session", None)  # type: ignore[assignment]
        if session is None:
            return []
        detector = MarketCycleRegimeDetector(session=session)
        result = await detector.compute()
        await detector.upsert_today(result)

        score = 1.0 if result.regime.value == "bull" else (
            0.5 if result.regime.value == "neutral" else 0.2
        )
        return [
            ScanCandidate(
                symbol="__PORTFOLIO__",
                exchange="NSE",
                score=score,
                stage=result.regime.value,
                reason=(
                    f"regime={result.regime.value} | nifty_roc_18m={result.nifty_roc} "
                    f"| smallcap_roc_20m={result.smallcap_roc}"
                ),
                suggested_entry=None,
                suggested_stop=None,
                suggested_target=None,
                metadata={
                    "regime": result.regime.value,
                    "nifty_roc_18m": (
                        float(result.nifty_roc) if result.nifty_roc is not None else None
                    ),
                    "smallcap_roc_20m": (
                        float(result.smallcap_roc) if result.smallcap_roc is not None else None
                    ),
                    "suggested_allocation_pct": float(result.suggested_allocation_pct),
                },
            )
        ]
