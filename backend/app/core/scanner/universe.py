"""Universe provider — lists NSE + BSE tradable equity instruments.

Reads the ``instruments`` table (populated by the master-contract sync) and
filters to ``InstrumentType.EQ``. Callers can further filter by exchange,
sector, or market-cap band via the ``filters`` dict.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scanner.base import InstrumentRef
from app.db.models.common import InstrumentType
from app.db.models.instrument import Instrument


@dataclass
class UniverseProvider:
    session: AsyncSession

    async def list(self, filters: dict[str, object] | None = None) -> list[InstrumentRef]:
        filters = filters or {}
        stmt = select(Instrument).where(Instrument.instrument_type == InstrumentType.EQ)

        exchanges = filters.get("exchanges")
        if exchanges:
            stmt = stmt.where(Instrument.exchange.in_(list(exchanges)))  # type: ignore[arg-type]
        else:
            stmt = stmt.where(Instrument.exchange.in_(["NSE", "BSE"]))

        symbol_prefix = filters.get("symbol_prefix")
        if isinstance(symbol_prefix, str) and symbol_prefix:
            stmt = stmt.where(Instrument.symbol.like(f"{symbol_prefix}%"))

        rows = (await self.session.execute(stmt)).scalars().all()
        # Deduplicate on (symbol, exchange) since multiple brokers may list the same ISIN.
        seen: set[tuple[str, str]] = set()
        out: list[InstrumentRef] = []
        for r in rows:
            key = (r.symbol, str(r.exchange))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                InstrumentRef(
                    symbol=r.symbol,
                    exchange=str(r.exchange),
                    isin=r.isin,
                )
            )
        return out
