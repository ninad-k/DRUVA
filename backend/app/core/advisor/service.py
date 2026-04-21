"""Orchestrates a full advisor run for one user.

Pipeline:
1. Load watchlist (or seed from Nifty-200 defaults if empty).
2. Load OHLCV history from the ``ohlcv_candles`` hypertable (daily).
3. Load fundamentals from the ``advisor_watchlist`` note column as a JSON
   fallback — in production you'd plug a proper fundamentals feed (Tickertape,
   Screener.in scrape, broker research). We keep the surface typed so the
   feed is swappable.
4. Run the rules-based scorer.
5. Optionally ask the configured LLM for a qualitative edge score.
6. Compute macro regime from Nifty / Smallcap monthly closes.
7. Persist ``AdvisorRun`` + ``AdvisorScore`` rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.advisor.allocator import Candidate, allocate
from app.core.advisor.llm import (
    LLMBackend,
    LLMRequest,
    NoOpBackend,
    backend_from_config,
    parse_llm_json,
)
from app.core.advisor.macro import classify
from app.core.advisor.scoring import StockSnapshot, score_snapshot
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.advisor import (
    AdvisorLLMConfig,
    AdvisorLLMProvider,
    AdvisorRun,
    AdvisorScore,
    AdvisorWatchlist,
    MacroRegime,
)
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


DEFAULT_NIFTY_SEED = [
    ("RELIANCE", "NSE"), ("TCS", "NSE"), ("HDFCBANK", "NSE"), ("INFY", "NSE"),
    ("ICICIBANK", "NSE"), ("ITC", "NSE"), ("LT", "NSE"), ("SBIN", "NSE"),
    ("KOTAKBANK", "NSE"), ("HINDUNILVR", "NSE"),
]

LLM_SYSTEM_PROMPT = (
    "You are an equity research assistant focused on Indian stocks (NSE/BSE). "
    "Given a stock snapshot, return a JSON object with keys: "
    "score (0-100 integer), rationale (string <=200 chars), risks (array of short strings). "
    "Score reflects multibagger potential over 2-3 years based on business quality, "
    "earnings growth outlook, and valuation. Be conservative — default below 60 unless "
    "the snapshot clearly supports high conviction. Output ONLY the JSON, no prose."
)


@dataclass
class AdvisorRunResult:
    run_id: UUID
    regime: MacroRegime
    scored: int
    top_picks: list[dict[str, Any]]


class AdvisorService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        http: httpx.AsyncClient,
        fallback_llm: dict[str, Any],
        capital_inr: float = 100_000.0,
        max_positions: int = 8,
        per_position_sl_pct: float = 10.0,
    ):
        self.session = session
        self.http = http
        self.fallback_llm = fallback_llm
        self.capital_inr = capital_inr
        self.max_positions = max_positions
        self.sl_pct = per_position_sl_pct
        self.ohlcv = OhlcvRepository(session=session)

    async def _load_llm_backend(self, user_id: UUID) -> LLMBackend:
        cfg = (
            await self.session.execute(
                select(AdvisorLLMConfig).where(AdvisorLLMConfig.user_id == user_id)
            )
        ).scalar_one_or_none()
        if cfg is None:
            return backend_from_config(http=self.http, config=None, fallback=self.fallback_llm)
        # api_key_encrypted field holds the plain key today (encryption plumbing
        # is available via app.infrastructure.encryption but opt-in per-user
        # and out of scope for this MVP).
        return backend_from_config(http=self.http, config=cfg, fallback=self.fallback_llm)

    async def _load_watchlist(self, user_id: UUID) -> list[AdvisorWatchlist]:
        rows = (
            await self.session.execute(
                select(AdvisorWatchlist).where(
                    AdvisorWatchlist.user_id == user_id,
                    AdvisorWatchlist.is_active.is_(True),
                )
            )
        ).scalars().all()
        if rows:
            return list(rows)
        # Seed a default watchlist if empty so first run produces something.
        seeded: list[AdvisorWatchlist] = []
        for sym, exch in DEFAULT_NIFTY_SEED:
            w = AdvisorWatchlist(user_id=user_id, symbol=sym, exchange=exch, is_active=True)
            self.session.add(w)
            seeded.append(w)
        await self.session.flush()
        return seeded

    async def _load_closes(self, symbol: str, exchange: str, limit: int) -> list[float]:
        candles = await self.ohlcv.latest(
            symbol=symbol, exchange=exchange, timeframe="1d", limit=limit,
        )
        return [float(c.close) for c in candles]

    async def _load_monthly_closes(self, symbol: str, exchange: str) -> list[float]:
        candles = await self.ohlcv.latest(
            symbol=symbol, exchange=exchange, timeframe="1M", limit=40,
        )
        if candles:
            return [float(c.close) for c in candles]
        # Fallback: resample daily to monthly-end.
        daily = await self.ohlcv.latest(
            symbol=symbol, exchange=exchange, timeframe="1d", limit=800,
        )
        monthly: list[float] = []
        current_month = None
        last_close = None
        for c in daily:
            m = (c.ts.year, c.ts.month)
            if current_month is None:
                current_month = m
            if m != current_month and last_close is not None:
                monthly.append(float(last_close))
                current_month = m
            last_close = c.close
        if last_close is not None:
            monthly.append(float(last_close))
        return monthly

    def _parse_fundamentals(self, notes: str | None) -> dict[str, Any]:
        if not notes:
            return {}
        try:
            data = json.loads(notes)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _llm_score(self, backend: LLMBackend, snap: StockSnapshot) -> tuple[float | None, str | None]:
        if isinstance(backend, NoOpBackend):
            return None, None
        user_msg = json.dumps({
            "symbol": snap.symbol,
            "exchange": snap.exchange,
            "last_price": snap.last_price,
            "sector": snap.sector,
            "roce": snap.roce,
            "roe": snap.roe,
            "eps_growth_yoy": snap.eps_growth_yoy,
            "pe_ratio": snap.pe_ratio,
            "sector_median_pe": snap.sector_median_pe,
            "is_recent_ipo": snap.is_recent_ipo,
            "market_cap_cr": snap.market_cap_cr,
            "price_12m_return_pct": (
                (snap.closes[-1] / snap.closes[-252] - 1) * 100
                if len(snap.closes) >= 252 else None
            ),
        })
        try:
            resp = await backend.complete(LLMRequest(
                system=LLM_SYSTEM_PROMPT,
                user=user_msg,
                temperature=0.2,
                max_tokens=400,
            ))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("advisor.llm_call_failed", error=str(exc), symbol=snap.symbol)
            return None, None
        parsed = parse_llm_json(resp.text)
        if not parsed:
            return None, resp.text[:300] if resp.text else None
        try:
            score = float(parsed.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(100.0, score))
        rationale = str(parsed.get("rationale", ""))[:500] or None
        return score, rationale

    async def run(self, *, user_id: UUID) -> AdvisorRunResult:
        now = datetime.now(timezone.utc)
        watchlist = await self._load_watchlist(user_id)

        # Macro regime — use Nifty-50 and Nifty Smallcap 100 symbols.
        nifty_monthly = await self._load_monthly_closes("NIFTY 50", "NSE")
        small_monthly = await self._load_monthly_closes("NIFTY SMLCAP 100", "NSE")
        reading = classify(nifty_monthly, small_monthly)
        aggressive = reading.regime == MacroRegime.AGGRESSIVE

        backend = await self._load_llm_backend(user_id)

        run = AdvisorRun(
            user_id=user_id,
            ran_at=now,
            macro_regime=reading.regime,
            nifty_roc=Decimal(str(round(reading.nifty_roc, 2))) if reading.nifty_roc is not None else None,
            smallcap_roc=Decimal(str(round(reading.smallcap_roc, 2))) if reading.smallcap_roc is not None else None,
            llm_provider=backend.provider,
            llm_model=backend.model,
            symbols_scanned=0,
        )
        self.session.add(run)
        await self.session.flush()

        candidates: list[Candidate] = []
        scored_rows: list[AdvisorScore] = []
        for w in watchlist:
            closes = await self._load_closes(w.symbol, w.exchange, limit=300)
            if not closes:
                continue
            fundamentals = self._parse_fundamentals(w.notes)
            snap = StockSnapshot(
                symbol=w.symbol,
                exchange=w.exchange,
                last_price=closes[-1],
                closes=closes,
                sector=w.sector or fundamentals.get("sector"),
                roce=fundamentals.get("roce"),
                roe=fundamentals.get("roe"),
                eps_growth_yoy=fundamentals.get("eps_growth_yoy"),
                pe_ratio=fundamentals.get("pe_ratio"),
                sector_median_pe=fundamentals.get("sector_median_pe"),
                is_recent_ipo=bool(fundamentals.get("is_recent_ipo", False)),
                market_cap_cr=fundamentals.get("market_cap_cr"),
            )
            llm_score, llm_reason = await self._llm_score(backend, snap)
            comp = score_snapshot(snap, llm=llm_score, macro_aggressive=aggressive)

            candidates.append(Candidate(
                symbol=snap.symbol,
                exchange=snap.exchange,
                composite_score=comp.composite,
                tier=comp.tier,
                last_price=snap.last_price,
            ))
            scored_rows.append(AdvisorScore(
                run_id=run.id,
                user_id=user_id,
                symbol=snap.symbol,
                exchange=snap.exchange,
                last_price=Decimal(str(round(snap.last_price, 4))),
                composite_score=Decimal(str(comp.composite)),
                fundamental_score=Decimal(str(round(comp.fundamental, 2))),
                technical_score=Decimal(str(round(comp.technical, 2))),
                momentum_score=Decimal(str(round(comp.momentum, 2))),
                llm_score=Decimal(str(round(comp.llm, 2))) if comp.llm is not None else None,
                multibagger_tier=comp.tier,
                rationale=llm_reason,
                features=comp.features,
            ))

        # Allocation pass — updates stop_loss/target/suggested_allocation_pct.
        allocs = allocate(
            candidates,
            capital_inr=self.capital_inr,
            regime=reading.regime,
            max_positions=self.max_positions,
            stop_loss_pct=self.sl_pct,
        )
        alloc_by_sym = {(a.symbol, a.exchange): a for a in allocs}
        for row in scored_rows:
            a = alloc_by_sym.get((row.symbol, row.exchange))
            if a:
                row.stop_loss = Decimal(str(a.stop_loss))
                row.target_price = Decimal(str(a.target_price))
                row.suggested_allocation_pct = Decimal(str(a.suggested_pct))
            self.session.add(row)

        run.symbols_scanned = len(scored_rows)
        await self.session.flush()
        await self.session.commit()

        top = sorted(scored_rows, key=lambda r: float(r.composite_score), reverse=True)[:10]
        return AdvisorRunResult(
            run_id=run.id,
            regime=reading.regime,
            scored=len(scored_rows),
            top_picks=[
                {
                    "symbol": r.symbol,
                    "exchange": r.exchange,
                    "composite_score": float(r.composite_score),
                    "tier": r.multibagger_tier,
                    "last_price": float(r.last_price) if r.last_price is not None else None,
                    "stop_loss": float(r.stop_loss) if r.stop_loss is not None else None,
                    "target_price": float(r.target_price) if r.target_price is not None else None,
                    "suggested_allocation_pct": float(r.suggested_allocation_pct),
                    "rationale": r.rationale,
                }
                for r in top
            ],
        )

    # --- watchlist CRUD helpers -----------------------------------------
    async def add_to_watchlist(
        self, *, user_id: UUID, symbol: str, exchange: str = "NSE",
        sector: str | None = None, notes: str | None = None,
    ) -> AdvisorWatchlist:
        existing = (
            await self.session.execute(
                select(AdvisorWatchlist).where(
                    AdvisorWatchlist.user_id == user_id,
                    AdvisorWatchlist.symbol == symbol,
                    AdvisorWatchlist.exchange == exchange,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.is_active = True
            if sector: existing.sector = sector
            if notes is not None: existing.notes = notes
            await self.session.commit()
            return existing
        row = AdvisorWatchlist(
            user_id=user_id, symbol=symbol, exchange=exchange,
            sector=sector, notes=notes, is_active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def remove_from_watchlist(self, *, user_id: UUID, watchlist_id: UUID) -> None:
        await self.session.execute(
            delete(AdvisorWatchlist).where(
                AdvisorWatchlist.id == watchlist_id,
                AdvisorWatchlist.user_id == user_id,
            )
        )
        await self.session.commit()


def fallback_llm_from_settings(settings) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "provider": AdvisorLLMProvider(settings.advisor_llm_provider),
        "model": settings.advisor_llm_model,
        "base_url": settings.advisor_llm_base_url,
        "api_key": settings.advisor_llm_api_key or None,
        "timeout_s": settings.advisor_llm_timeout_s,
    }
