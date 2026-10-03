"""Instrument-master download for Upstox, Dhan and Groww (respx, no network)."""

from __future__ import annotations

import gzip
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from app.brokers.base import BrokerCredentials, OrderRequest
from app.brokers.dhan import INSTRUMENT_URL as DHAN_URL
from app.brokers.dhan import DhanAdapter
from app.brokers.groww import INSTRUMENT_URL as GROWW_URL
from app.brokers.groww import GrowwAdapter
from app.brokers.upstox import INSTRUMENT_URLS, UpstoxAdapter
from app.core.errors import BrokerError

NSE_URL, BSE_URL = INSTRUMENT_URLS

NSE_ROWS = [
    {
        "segment": "NSE_EQ",
        "name": "RELIANCE INDUSTRIES LTD",
        "exchange": "NSE",
        "isin": "INE002A01018",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE002A01018",
        "lot_size": 1,
        "exchange_token": "2885",
        "tick_size": 5.0,
        "trading_symbol": "RELIANCE",
    },
    {
        "segment": "NSE_FO",
        "name": "NIFTY",
        "instrument_type": "CE",
        "instrument_key": "NSE_FO|12345",
        "lot_size": 75,
        "exchange_token": "12345",
        "tick_size": 5.0,
        "trading_symbol": "NIFTY 24500 CE 26 DEC 24",
        "expiry": 1735216200000,  # 2024-12-26 18:00 IST
        "strike_price": 24500.0,
        "underlying_symbol": "NIFTY",
    },
    {"segment": "NSE_EQ", "trading_symbol": "NOKEY"},  # no instrument_key -> skipped
    {"segment": "WEIRD_SEG", "instrument_key": "X|1", "trading_symbol": "X"},  # skipped
]
BSE_ROWS = [
    {
        "segment": "BSE_EQ",
        "instrument_type": "EQ",
        "instrument_key": "BSE_EQ|INE002A01018",
        "exchange_token": "500325",
        "lot_size": 1,
        "tick_size": 5.0,
        "trading_symbol": "RELIANCE",
        "isin": "INE002A01018",
    }
]


class _Chunked(httpx.AsyncByteStream):
    def __init__(self, data: bytes, size: int):
        self._chunks = [data[i : i + size] for i in range(0, len(data), size)]

    async def __aiter__(self):
        for c in self._chunks:
            yield c


async def _collect(agen):
    return [r async for r in agen]


@pytest.fixture
def http():
    return httpx.AsyncClient()


@respx.mock
async def test_upstox_master_gzipped_json_split_across_tiny_chunks(http):
    # 7-byte chunks force JSON elements and gzip frames to straddle chunk edges.
    respx.get(NSE_URL).mock(
        return_value=httpx.Response(
            200, stream=_Chunked(gzip.compress(json.dumps(NSE_ROWS).encode()), 7)
        )
    )
    respx.get(BSE_URL).mock(
        return_value=httpx.Response(200, content=gzip.compress(json.dumps(BSE_ROWS).encode()))
    )
    recs = await _collect(UpstoxAdapter(http).download_master_contract())
    assert [(r.exchange, r.symbol) for r in recs] == [
        ("NSE", "RELIANCE"),
        ("NFO", "NIFTY 24500 CE 26 DEC 24"),
        ("BSE", "RELIANCE"),
    ]
    eq, opt, bse = recs
    assert eq.broker_token == "NSE_EQ|INE002A01018"
    assert eq.isin == "INE002A01018"
    assert eq.tick_size == Decimal("0.05")
    assert eq.expiry is None and eq.strike is None
    assert opt.instrument_type == "CE"
    assert opt.lot_size == 75
    assert opt.expiry == date(2024, 12, 26)
    assert opt.strike == Decimal("24500.0")
    assert opt.extra["underlying_symbol"] == "NIFTY"
    assert bse.exchange_token == "500325"


@respx.mock
async def test_upstox_master_accepts_plain_json_and_sends_no_auth(http):
    route = respx.get(NSE_URL).mock(return_value=httpx.Response(200, json=NSE_ROWS[:1]))
    respx.get(BSE_URL).mock(return_value=httpx.Response(200, json=[]))
    adapter = UpstoxAdapter(http)
    await adapter.authenticate(BrokerCredentials("k", "s", {"access_token": "tok"}))
    recs = await _collect(adapter.download_master_contract())
    assert len(recs) == 1
    assert "authorization" not in route.calls[0].request.headers


@respx.mock
async def test_upstox_master_http_error_and_truncation(http):
    respx.get(NSE_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(BrokerError, match="upstox_instruments_failed:503"):
        await _collect(UpstoxAdapter(http).download_master_contract())

    respx.get(NSE_URL).mock(
        return_value=httpx.Response(200, content=b'[{"segment": "NSE_EQ", "instrument_key')
    )
    with pytest.raises(BrokerError, match="truncated"):
        await _collect(UpstoxAdapter(http).download_master_contract())


@respx.mock
async def test_upstox_master_url_override(http):
    respx.get("https://example.test/x.json").mock(
        return_value=httpx.Response(200, json=NSE_ROWS[:1])
    )
    adapter = UpstoxAdapter(http, instrument_urls=("https://example.test/x.json",))
    assert len(await _collect(adapter.download_master_contract())) == 1


DHAN_CSV = (
    "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,"
    "SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,"
    "SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,"
    "SEM_SYMBOL_NAME\r\n"
    "NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,-0.01000,,5.0000,NA,ES,EQ,RELIANCE\r\n"
    "NSE,D,45001,OPTIDX,0,NIFTY-Dec2024-24500-CE,75.0,NIFTY 26 DEC 24500 CALL,"
    "2024-12-26 14:30:00,24500.00000,CE,5.0000,W,OP,NA,NIFTY\r\n"
    "NSE,D,45002,FUTIDX,0,NIFTY-Dec2024-FUT,75.0,NIFTY DEC FUT,2024-12-26 14:30:00,"
    "-0.01000,XX,10.0000,M,FUT,NA,NIFTY\r\n"
    "NSE,I,13,INDEX,0,NIFTY,1.0,Nifty 50,,0,,0,NA,I,NA,NIFTY\r\n"
    "MCX,M,999,FUTCOM,0,CRUDEOIL-Dec2024-FUT,100.0,CRUDE,2024-12-19 23:30:00,0,,1.0,M,FUT,NA,"
    "CRUDEOIL\r\n"
    "XXX,Z,1,EQUITY,0,BOGUS,1.0,x,,0,,5,NA,ES,EQ,x\r\n"
)


@respx.mock
async def test_dhan_master_csv(http):
    respx.get(DHAN_URL).mock(
        return_value=httpx.Response(200, stream=_Chunked(("﻿" + DHAN_CSV).encode(), 13))
    )
    recs = await _collect(DhanAdapter(http).download_master_contract())
    by_sym = {r.symbol: r for r in recs}
    assert set(by_sym) == {
        "RELIANCE",
        "NIFTY-Dec2024-24500-CE",
        "NIFTY-Dec2024-FUT",
        "NIFTY",
        "CRUDEOIL-Dec2024-FUT",
    }
    eq = by_sym["RELIANCE"]
    assert (eq.exchange, eq.broker_token, eq.instrument_type) == ("NSE", "2885", "EQ")
    assert eq.strike is None and eq.expiry is None
    assert eq.tick_size == Decimal("0.05")
    ce = by_sym["NIFTY-Dec2024-24500-CE"]
    assert (ce.exchange, ce.instrument_type, ce.lot_size) == ("NFO", "CE", 75)
    assert ce.expiry == date(2024, 12, 26) and ce.strike == Decimal("24500")
    fut = by_sym["NIFTY-Dec2024-FUT"]
    assert fut.instrument_type == "FUT" and fut.strike is None
    assert by_sym["NIFTY"].instrument_type == "INDEX"
    assert by_sym["CRUDEOIL-Dec2024-FUT"].exchange == "MCX"


@respx.mock
async def test_dhan_master_errors(http):
    respx.get(DHAN_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(BrokerError, match="dhan_instruments_failed:500"):
        await _collect(DhanAdapter(http).download_master_contract())
    respx.get(DHAN_URL).mock(return_value=httpx.Response(200, content=b""))
    with pytest.raises(BrokerError, match="empty_response"):
        await _collect(DhanAdapter(http).download_master_contract())


GROWW_CSV = (
    "exchange,exchange_token,trading_symbol,groww_symbol,name,instrument_type,segment,series,"
    "isin,underlying_symbol,underlying_exchange_token,expiry_date,strike_price,lot_size,"
    "tick_size,freeze_quantity,is_reserved,buy_allowed,sell_allowed\n"
    "NSE,2885,RELIANCE,NSE-RELIANCE,Reliance,EQ,CASH,EQ,INE002A01018,,,,,1,0.05,,0,1,1\n"
    "NSE,45001,NIFTY24DEC24500CE,NSE-NIFTY-26Dec24-24500-CE,Nifty,CE,FNO,,,NIFTY,,"
    "2024-12-26,24500,75,0.05,,0,1,1\n"
    "NSE,,NOTOKEN,x,x,EQ,CASH,,,,,,,1,0.05,,0,1,1\n"
)


@respx.mock
async def test_groww_master_csv(http):
    respx.get(GROWW_URL).mock(return_value=httpx.Response(200, text=GROWW_CSV))
    recs = await _collect(GrowwAdapter(http).download_master_contract())
    assert [(r.exchange, r.symbol, r.instrument_type) for r in recs] == [
        ("NSE", "RELIANCE", "EQ"),
        ("NFO", "NIFTY24DEC24500CE", "CE"),
    ]
    assert recs[0].isin == "INE002A01018"
    assert recs[1].expiry == date(2024, 12, 26)
    assert recs[1].strike == Decimal("24500") and recs[1].lot_size == 75


@respx.mock
async def test_groww_authenticate_and_place_order(http):
    base = "https://growwapi.groww.in/v1"
    tok = respx.post(f"{base}/token/api/access").mock(
        return_value=httpx.Response(
            200, json={"status": "SUCCESS", "payload": {"token": "T123", "expiry": "2026-10-04T06:00:00"}}
        )
    )
    order = respx.post(f"{base}/order/create").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "SUCCESS",
                "payload": {"groww_order_id": "GMK1", "order_status": "OPEN", "remark": "ok"},
            },
        )
    )
    adapter = GrowwAdapter(http)
    sess = await adapter.authenticate(BrokerCredentials("KEY", "SECRET"))
    assert sess.access_token == "T123"
    sent = json.loads(tok.calls[0].request.content)
    assert sent["key_type"] == "approval" and len(sent["checksum"]) == 64
    assert tok.calls[0].request.headers["authorization"] == "Bearer KEY"

    ack = await adapter.place_order(
        OrderRequest("RELIANCE", "NSE", "BUY", Decimal(1), "LIMIT", "CNC", price=Decimal("2500"))
    )
    assert ack.broker_order_id == "GMK1" and ack.status == "open"
    req = order.calls[0].request
    body = json.loads(req.content)
    assert body["segment"] == "CASH" and body["trading_symbol"] == "RELIANCE"
    assert req.headers["authorization"] == "Bearer T123"
    assert req.headers["x-api-version"] == "1.0"


@respx.mock
async def test_groww_failures_raise(http):
    base = "https://growwapi.groww.in/v1"
    respx.post(f"{base}/token/api/access").mock(
        return_value=httpx.Response(
            200, json={"status": "FAILURE", "error": {"code": "GA001", "message": "bad key"}}
        )
    )
    with pytest.raises(BrokerError, match="GA001"):
        await GrowwAdapter(http).authenticate(BrokerCredentials("K", "S"))
    with pytest.raises(BrokerError, match="unsupported_exchange"):
        await GrowwAdapter(http).place_order(
            OrderRequest("X", "MCX", "BUY", Decimal(1), "MARKET", "NRML")
        )


@respx.mock
async def test_groww_depth_and_search_build_valid_base_types(http):
    base = "https://growwapi.groww.in/v1"
    respx.get(f"{base}/marketdata/depth").mock(
        return_value=httpx.Response(
            200,
            json={"status": "SUCCESS", "payload": {"bids": [{"price": 1, "quantity": 2}], "asks": []}},
        )
    )
    respx.get(f"{base}/marketdata/search").mock(
        return_value=httpx.Response(
            200,
            json={"status": "SUCCESS", "payload": [{"tradingSymbol": "TCS", "exchange": "NSE"}]},
        )
    )
    a = GrowwAdapter(http)
    depth = await a.get_depth("TCS", "NSE")
    assert depth.bids[0].quantity == Decimal(2)
    assert (await a.search_symbols("TC"))[0].trading_symbol == "TCS"
