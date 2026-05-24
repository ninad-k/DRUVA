"""Pluggable fundamentals data provider.

The valuation and persona-analysis layers depend on this abstraction so that
the underlying source (Screener.in, Trendlyne, Tickertape, a paid API, or a
static fixture) can be swapped via configuration without code changes.

Config keys (in ``Settings``):
  ``fundamentals_provider``    — ``repository`` | ``null`` | ``http`` | ``static``
  ``fundamentals_http_base_url`` — base URL when provider == ``http``
  ``fundamentals_http_api_key``  — bearer token / API key for the HTTP provider
  ``fundamentals_http_timeout_s``— per-request timeout

Implementations:
  • ``RepositoryFundamentalsProvider`` — reads the local ``FundamentalSnapshot``
    cache populated by the existing weekly refresh job.
  • ``NullFundamentalsProvider`` — always returns ``None`` (safe default when no
    source is configured; downstream agents fall back to ratio-only or pure-LLM
    reasoning).
  • ``StaticFundamentalsProvider`` — in-memory dict, useful for tests + the
    Phase-D demo before the user wires a real source.
  • ``HTTPFundamentalsProvider`` — generic JSON-API client; expects the remote
    payload to look like ``FundamentalsView``. Users wire their chosen source by
    setting two env vars; no code change needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

import httpx

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# View types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineItem:
    """One year (or quarter) of a single financial line item.

    All amounts are in the issuer's reporting currency — INR for NSE/BSE.
    ``period_end`` is the fiscal-period end date; for Indian companies this is
    typically 31-Mar of the fiscal year.
    """

    period_end: date
    value: float


@dataclass(frozen=True)
class FundamentalsView:
    """Read-only fundamentals view used by valuation + persona agents.

    Designed to be a *superset* of what ``FundamentalSnapshot`` stores: when the
    underlying source has only ratios (e.g. Screener basic), the historical
    line-item lists are empty and the DCF gracefully degrades. When the source
    provides 10-year filings (most Indian fundamentals providers do), the DCF
    runs at full fidelity.

    Field names mirror Indian filings (CMP, ROCE) where they differ from US
    conventions (last-trade price, ROIC) so the LLM prompts read naturally.
    """

    symbol: str
    exchange: str = "NSE"
    as_of: date | None = None

    # Spot data ------------------------------------------------------------
    market_cap: float | None = None
    current_price: float | None = None
    shares_outstanding: float | None = None
    sector: str | None = None
    industry: str | None = None

    # Ratios (latest snapshot) --------------------------------------------
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    roe: float | None = None              # %
    roce: float | None = None             # %
    debt_to_equity: float | None = None
    operating_margin: float | None = None # %
    current_ratio: float | None = None
    asset_turnover: float | None = None
    promoter_holding: float | None = None # %

    # Historical line items (oldest → newest). All optional. -----------------
    net_income: list[LineItem] = field(default_factory=list)
    revenue: list[LineItem] = field(default_factory=list)
    gross_profit: list[LineItem] = field(default_factory=list)
    operating_income: list[LineItem] = field(default_factory=list)
    free_cash_flow: list[LineItem] = field(default_factory=list)
    capital_expenditure: list[LineItem] = field(default_factory=list)
    depreciation: list[LineItem] = field(default_factory=list)
    total_assets: list[LineItem] = field(default_factory=list)
    total_liabilities: list[LineItem] = field(default_factory=list)
    shareholders_equity: list[LineItem] = field(default_factory=list)
    dividends: list[LineItem] = field(default_factory=list)
    share_repurchases: list[LineItem] = field(default_factory=list)
    shares_outstanding_history: list[LineItem] = field(default_factory=list)

    # Provenance ----------------------------------------------------------
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class FundamentalsProvider(Protocol):
    """Async fundamentals lookup. Implementations must be safe for concurrent use."""

    name: str

    async def get(self, symbol: str, exchange: str = "NSE") -> FundamentalsView | None:
        """Return the latest fundamentals view, or ``None`` if not available."""
        ...


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class NullFundamentalsProvider:
    """Always returns ``None``. Used when no fundamentals source is configured."""

    name = "null"

    async def get(self, symbol: str, exchange: str = "NSE") -> None:
        logger.debug("fundamentals.null_provider.get", symbol=symbol, exchange=exchange)
        return None


class StaticFundamentalsProvider:
    """Serves a fixed in-memory map. Primarily for tests and the Phase-D demo."""

    name = "static"

    def __init__(self, views: dict[tuple[str, str], FundamentalsView] | None = None) -> None:
        self._views: dict[tuple[str, str], FundamentalsView] = views or {}

    def add(self, view: FundamentalsView) -> None:
        self._views[(view.symbol.upper(), view.exchange.upper())] = view

    async def get(self, symbol: str, exchange: str = "NSE") -> FundamentalsView | None:
        return self._views.get((symbol.upper(), exchange.upper()))


class RepositoryFundamentalsProvider:
    """Reads from the existing ``FundamentalSnapshot`` cache.

    The DB row only stores latest ratios — historical line items will be empty.
    The DCF in that case will report ``DCFResult.degraded=True``.
    """

    name = "repository"

    def __init__(self, session_factory: Any) -> None:
        """``session_factory`` is an async callable yielding ``AsyncSession``."""
        self._session_factory = session_factory

    async def get(self, symbol: str, exchange: str = "NSE") -> FundamentalsView | None:
        # Imported lazily so test environments without SQLAlchemy still load this
        # module. ``session_factory`` is expected to be an async iterator that
        # yields an ``AsyncSession`` — matching DRUVA's ``get_session`` pattern.
        from app.data.fundamentals.repository import FundamentalRepository

        async for session in self._session_factory():
            repo = FundamentalRepository(session=session)
            row = await repo.latest(symbol=symbol.upper(), exchange=exchange.upper())
            if row is None:
                return None
            return FundamentalsView(
                symbol=row.symbol,
                exchange=row.exchange,
                as_of=row.as_of_date,
                market_cap=_decimal_to_float(row.market_cap),
                current_price=_decimal_to_float(row.current_price),
                pe_ratio=_decimal_to_float(row.pe_ratio),
                roe=_decimal_to_float(row.roe),
                roce=_decimal_to_float(row.roce),
                debt_to_equity=_decimal_to_float(row.debt_to_equity),
                promoter_holding=_decimal_to_float(row.promoter_holding),
                sector=row.sector,
                industry=row.industry,
                source=row.source,
                raw=dict(row.raw_jsonb or {}),
            )
        return None


class HTTPFundamentalsProvider:
    """Generic JSON-API client for a user-supplied fundamentals service.

    The remote endpoint must accept ``GET {base_url}/{exchange}/{symbol}`` and
    return JSON shaped roughly like ``FundamentalsView`` (snake_case keys,
    line-item lists as ``[{"period_end": "YYYY-MM-DD", "value": float}, ...]``).

    Users plug their own data source by setting ``DHRUVA_FUNDAMENTALS_PROVIDER=http``
    plus a base URL + API key. No code change required.
    """

    name = "http"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_s: float = 15.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("HTTPFundamentalsProvider requires a non-empty base_url")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or None
        self._timeout_s = float(timeout_s)
        self._http = http  # if None, a per-call client is created

    async def get(self, symbol: str, exchange: str = "NSE") -> FundamentalsView | None:
        url = f"{self._base_url}/{exchange.upper()}/{symbol.upper()}"
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            if self._http is not None:
                resp = await self._http.get(url, headers=headers, timeout=self._timeout_s)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning(
                "fundamentals.http_provider.error",
                symbol=symbol,
                exchange=exchange,
                error=str(exc),
            )
            return None

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            logger.warning(
                "fundamentals.http_provider.bad_status",
                symbol=symbol,
                exchange=exchange,
                status=resp.status_code,
            )
            return None

        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning("fundamentals.http_provider.invalid_json", error=str(exc))
            return None

        return _view_from_payload(payload, symbol=symbol, exchange=exchange)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_provider(
    *,
    kind: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout_s: float | None = None,
    session_factory: Any | None = None,
    static_views: dict[tuple[str, str], FundamentalsView] | None = None,
) -> FundamentalsProvider:
    """Construct a provider from explicit arguments + ``Settings``.

    Resolution order for each parameter:
      1. explicit kwarg passed here
      2. ``Settings`` field (env-loaded via pydantic-settings)
      3. raw env var fallback (for tests that monkeypatch ``os.environ``)

    Returns a ``NullFundamentalsProvider`` if the requested kind is unknown
    or required parameters are missing — never raises.
    """
    settings = _safe_settings()
    chosen = (
        kind
        or (settings.fundamentals_provider if settings else None)
        or os.environ.get("DHRUVA_FUNDAMENTALS_PROVIDER")
        or "repository"
    ).lower()

    if chosen == "repository":
        if session_factory is None:
            logger.warning("fundamentals.factory.repository_no_session")
            return NullFundamentalsProvider()
        return RepositoryFundamentalsProvider(session_factory=session_factory)
    if chosen == "static":
        return StaticFundamentalsProvider(views=static_views)
    if chosen == "http":
        resolved_base = (
            base_url
            or (settings.fundamentals_http_base_url if settings else "")
            or os.environ.get("DHRUVA_FUNDAMENTALS_HTTP_BASE_URL", "")
        )
        resolved_key = (
            api_key
            or (settings.fundamentals_http_api_key if settings else "")
            or os.environ.get("DHRUVA_FUNDAMENTALS_HTTP_API_KEY")
            or None
        )
        resolved_timeout = (
            timeout_s
            if timeout_s is not None
            else (settings.fundamentals_http_timeout_s if settings else 15.0)
        )
        if not resolved_base:
            logger.warning("fundamentals.factory.http_missing_base_url")
            return NullFundamentalsProvider()
        return HTTPFundamentalsProvider(
            base_url=resolved_base,
            api_key=resolved_key,
            timeout_s=resolved_timeout,
        )
    if chosen == "null" or chosen == "none":
        return NullFundamentalsProvider()
    logger.warning("fundamentals.factory.unknown_kind", kind=chosen)
    return NullFundamentalsProvider()


def _safe_settings() -> Any | None:
    """Load ``Settings`` lazily; tolerate environments without it on the path."""
    try:
        from app.config import get_settings

        return get_settings()
    except Exception as exc:  # noqa: BLE001 — tests/imports without env
        logger.debug("fundamentals.factory.settings_unavailable", error=str(exc))
        return None


def get_fundamentals_provider(session_factory: Any | None = None) -> FundamentalsProvider:
    """Convenience wrapper for FastAPI dependencies — reads all config from env."""
    return build_provider(session_factory=session_factory)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _view_from_payload(
    payload: dict[str, Any], *, symbol: str, exchange: str
) -> FundamentalsView | None:
    if not isinstance(payload, dict):
        return None
    try:
        return FundamentalsView(
            symbol=str(payload.get("symbol") or symbol).upper(),
            exchange=str(payload.get("exchange") or exchange).upper(),
            as_of=_parse_date(payload.get("as_of")),
            market_cap=_to_float(payload.get("market_cap")),
            current_price=_to_float(payload.get("current_price")),
            shares_outstanding=_to_float(payload.get("shares_outstanding")),
            sector=_to_str(payload.get("sector")),
            industry=_to_str(payload.get("industry")),
            pe_ratio=_to_float(payload.get("pe_ratio")),
            pb_ratio=_to_float(payload.get("pb_ratio")),
            roe=_to_float(payload.get("roe")),
            roce=_to_float(payload.get("roce")),
            debt_to_equity=_to_float(payload.get("debt_to_equity")),
            operating_margin=_to_float(payload.get("operating_margin")),
            current_ratio=_to_float(payload.get("current_ratio")),
            asset_turnover=_to_float(payload.get("asset_turnover")),
            promoter_holding=_to_float(payload.get("promoter_holding")),
            net_income=_parse_line_items(payload.get("net_income")),
            revenue=_parse_line_items(payload.get("revenue")),
            gross_profit=_parse_line_items(payload.get("gross_profit")),
            operating_income=_parse_line_items(payload.get("operating_income")),
            free_cash_flow=_parse_line_items(payload.get("free_cash_flow")),
            capital_expenditure=_parse_line_items(payload.get("capital_expenditure")),
            depreciation=_parse_line_items(payload.get("depreciation")),
            total_assets=_parse_line_items(payload.get("total_assets")),
            total_liabilities=_parse_line_items(payload.get("total_liabilities")),
            shareholders_equity=_parse_line_items(payload.get("shareholders_equity")),
            dividends=_parse_line_items(payload.get("dividends")),
            share_repurchases=_parse_line_items(payload.get("share_repurchases")),
            shares_outstanding_history=_parse_line_items(payload.get("shares_outstanding_history")),
            source=str(payload.get("source") or "http"),
            raw=dict(payload),
        )
    except Exception as exc:  # noqa: BLE001 — any malformed field → drop the row
        logger.warning("fundamentals.http_provider.parse_error", error=str(exc))
        return None


def _parse_line_items(value: Any) -> list[LineItem]:
    if not isinstance(value, list):
        return []
    items: list[LineItem] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        period_end = _parse_date(entry.get("period_end"))
        amount = _to_float(entry.get("value"))
        if period_end is None or amount is None:
            continue
        items.append(LineItem(period_end=period_end, value=amount))
    items.sort(key=lambda li: li.period_end)
    return items


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
