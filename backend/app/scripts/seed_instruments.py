"""One-shot bulk seed of the ``instruments`` table.

Pulls Zerodha Kite's public instrument master (``https://api.kite.trade/instruments``).
That endpoint is unauthenticated, ships a single CSV covering NSE/BSE/NFO/BFO/MCX,
and is the de-facto reference master used across the Indian retail trading
ecosystem. Run from ``backend/``:

    python -m app.scripts.seed_instruments

Idempotent — upserts on the ``(broker_id, symbol, exchange)`` unique key, so
re-running picks up new listings and refreshes expiring derivatives.

Notes
-----
* CSV is ~30 MB / ~140k rows; the whole file is held in memory while
  parsing. Fine for a one-shot CLI, not appropriate for a hot path.
* ``broker_id`` is stamped as ``"zerodha"`` (the source). The instrument
  search endpoint searches across all broker_ids, so the picker finds rows
  regardless of which broker the user actually trades with.
* Zerodha publishes index rows (NIFTY 50, NIFTY BANK, …) with ``lot_size=0``
  and ``tick_size=0``. We coerce those to sensible defaults so the
  ``Instrument`` validation doesn't reject them.
* Human-readable name + segment land in ``extra_jsonb`` so the search API
  can echo them back without a schema migration.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.common import Exchange, InstrumentType, MasterContractSyncStatus
from app.db.models.instrument import Instrument, MasterContractStatus
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

SOURCE_URL = "https://api.kite.trade/instruments"
SOURCE_BROKER_ID = "zerodha"
BATCH_SIZE = 1000

# Zerodha's `exchange` column → our Exchange enum. Anything not listed here
# (e.g. GLOBAL, NCO, NSEIX) is dropped silently.
_EXCHANGE_MAP: dict[str, Exchange] = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "BFO": Exchange.BFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.CDS,
    "BCD": Exchange.BCD,
}

# Zerodha's `instrument_type` already aligns with our enum (EQ, FUT, CE, PE),
# but it doesn't expose "IDX" — index rows come through as EQ with segment
# "INDICES". We rewrite those so the picker can distinguish indices.
_INSTRUMENT_TYPE_MAP: dict[str, InstrumentType] = {
    "EQ": InstrumentType.EQ,
    "FUT": InstrumentType.FUT,
    "CE": InstrumentType.CE,
    "PE": InstrumentType.PE,
}


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw or raw == "0":
        return None
    try:
        value = Decimal(raw)
    except (ValueError, ArithmeticError):
        return None
    if value <= 0:
        return None
    return value


def _parse_expiry(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _classify(row: dict[str, str]) -> InstrumentType:
    raw_type = (row.get("instrument_type") or "").upper()
    segment = (row.get("segment") or "").upper()
    if raw_type in _INSTRUMENT_TYPE_MAP:
        if raw_type == "EQ" and segment == "INDICES":
            return InstrumentType.IDX
        return _INSTRUMENT_TYPE_MAP[raw_type]
    return InstrumentType.EQ


def _to_row(item: dict[str, str]) -> dict[str, Any] | None:
    exch_raw = (item.get("exchange") or "").upper()
    exchange = _EXCHANGE_MAP.get(exch_raw)
    if exchange is None:
        return None

    trading_symbol = (item.get("tradingsymbol") or "").strip()
    name = (item.get("name") or "").strip().strip('"')
    token = (item.get("instrument_token") or "").strip()
    if not trading_symbol or not token:
        return None

    instrument_type = _classify(item)
    tick_size = _parse_decimal(item.get("tick_size")) or Decimal("0.05")
    lot_size_raw = item.get("lot_size") or "1"
    try:
        lot_size = max(1, int(Decimal(lot_size_raw)))
    except (ValueError, ArithmeticError):
        lot_size = 1

    return {
        # `tradingsymbol` IS the unique identifier across both equities and
        # derivatives (RELIANCE, NIFTY26MAY24500CE, BANKEX26MAYFUT). Using it
        # as `symbol` keeps every expiry/strike as its own row.
        "symbol": trading_symbol[:64],
        "exchange": exchange,
        "broker_token": token[:128],
        "broker_id": SOURCE_BROKER_ID,
        "instrument_type": instrument_type,
        "expiry": _parse_expiry(item.get("expiry")),
        "strike": _parse_decimal(item.get("strike")),
        "lot_size": lot_size,
        "tick_size": tick_size,
        "isin": None,
        "trading_symbol": trading_symbol[:64],
        "exchange_token": (item.get("exchange_token") or "")[:64] or None,
        # Name + segment stash here so /v1/instruments/search can return them
        # without a schema migration.
        "extra_jsonb": {
            "source": "zerodha_kite",
            "name": name,
            "segment": (item.get("segment") or "").strip(),
        },
        "updated_at": datetime.now(UTC),
    }


async def _download(url: str) -> list[dict[str, str]]:
    logger.info("instruments.seed.fetch_start", url=url)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    logger.info("instruments.seed.fetched", records=len(rows))
    return rows


async def _flush(session: AsyncSession, batch: list[dict[str, Any]]) -> None:
    stmt = insert(Instrument).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["broker_id", "symbol", "exchange"],
        set_={
            "broker_token": stmt.excluded.broker_token,
            "instrument_type": stmt.excluded.instrument_type,
            "lot_size": stmt.excluded.lot_size,
            "tick_size": stmt.excluded.tick_size,
            "expiry": stmt.excluded.expiry,
            "strike": stmt.excluded.strike,
            "trading_symbol": stmt.excluded.trading_symbol,
            "exchange_token": stmt.excluded.exchange_token,
            "extra_jsonb": stmt.excluded.extra_jsonb,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def _upsert_batches(
    session: AsyncSession, rows: Iterable[dict[str, Any]]
) -> int:
    buffer: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        buffer.append(row)
        if len(buffer) >= BATCH_SIZE:
            await _flush(session, buffer)
            total += len(buffer)
            buffer.clear()
            if total % (BATCH_SIZE * 10) == 0:
                logger.info("instruments.seed.progress", upserted=total)
    if buffer:
        await _flush(session, buffer)
        total += len(buffer)
    return total


async def _update_status(session: AsyncSession, *, count: int, error: str | None) -> None:
    row = await session.scalar(
        select(MasterContractStatus).where(MasterContractStatus.broker_id == SOURCE_BROKER_ID)
    )
    if row is None:
        row = MasterContractStatus(broker_id=SOURCE_BROKER_ID)
        session.add(row)
    row.status = MasterContractSyncStatus.FAILED if error else MasterContractSyncStatus.OK
    row.last_synced_at = datetime.now(UTC)
    row.record_count = count
    row.error_message = error


async def seed(
    *,
    url: str = SOURCE_URL,
    exchanges: set[str] | None = None,
    limit: int | None = None,
) -> int:
    raw = await _download(url)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for item in raw:
        if exchanges is not None and (item.get("exchange") or "").upper() not in exchanges:
            continue
        parsed = _to_row(item)
        if parsed is None:
            skipped += 1
            continue
        rows.append(parsed)
        if limit is not None and len(rows) >= limit:
            break

    logger.info("instruments.seed.parsed", kept=len(rows), skipped=skipped)

    total = 0
    async with SessionLocal() as session:
        async with session.begin():
            try:
                total = await _upsert_batches(session, rows)
                await _update_status(session, count=total, error=None)
            except Exception as exc:  # noqa: BLE001
                await _update_status(session, count=0, error=str(exc))
                raise

    logger.info("instruments.seed.done", upserted=total)
    return total


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchanges",
        default="NSE,BSE,NFO,BFO",
        help=(
            "Comma-separated exchange filter. Default keeps equities + listed "
            "derivatives but skips MCX commodities and currency derivatives. "
            "Pass 'NSE,BSE,NFO,BFO,MCX,CDS,BCD' for the full set."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on rows (for testing). Default: load everything.",
    )
    parser.add_argument(
        "--url",
        default=SOURCE_URL,
        help="Override source URL (e.g. a local file copy of the CSV).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    exchanges = {e.strip().upper() for e in args.exchanges.split(",") if e.strip()}
    total = asyncio.run(seed(url=args.url, exchanges=exchanges, limit=args.limit))
    print(f"\nSeeded {total} instruments from Zerodha Kite (kite.trade/instruments).\n")
