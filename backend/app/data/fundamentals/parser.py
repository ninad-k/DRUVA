"""HTML parser for Screener.in company pages.

Screener renders key ratios inside ``#top-ratios`` and company profile in
``.company-profile``. The layout is stable enough that regex/BeautifulSoup
extraction works well. On parse failure we return partial dicts so the
scanner can still use whatever fields were recognised.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_STRIP_RE = re.compile(r"[^\d.\-]")


def _to_decimal(text: str | None) -> Decimal | None:
    if not text:
        return None
    clean = _STRIP_RE.sub("", text)
    if not clean or clean in {".", "-"}:
        return None
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


RATIO_KEYS = {
    "market cap": "market_cap",
    "current price": "current_price",
    "stock p/e": "pe_ratio",
    "roce": "roce",
    "roe": "roe",
    "eps": "eps",
    "debt to equity": "debt_to_equity",
    "promoter holding": "promoter_holding",
    "sales growth": "sales_growth_3y",
    "profit growth": "profit_growth_3y",
}


def parse_ratios(html: str) -> dict[str, Any]:
    """Parse Screener key-ratios section from full page HTML.

    Uses BeautifulSoup when available; falls back to regex extraction so
    tests can run without an extra dependency pinned to screener_client.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError:
        return _regex_parse(html)

    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}
    # Key ratios are in #top-ratios > li
    top = soup.select_one("#top-ratios")
    if top is not None:
        for li in top.select("li"):
            label = li.select_one(".name")
            value = li.select_one(".number")
            if not label or not value:
                continue
            key = label.get_text(" ", strip=True).lower()
            for needle, field_name in RATIO_KEYS.items():
                if needle in key:
                    dec = _to_decimal(value.get_text(" ", strip=True))
                    if dec is not None:
                        out[field_name] = dec
                    break

    # Sector / industry are often in breadcrumb-ish spans; try a few selectors.
    sector = soup.select_one('a[href*="/sectors/"]')
    if sector is not None:
        out["sector"] = sector.get_text(" ", strip=True)
    industry = soup.select_one('a[href*="/industries/"]')
    if industry is not None:
        out["industry"] = industry.get_text(" ", strip=True)
    return out


def _regex_parse(html: str) -> dict[str, Any]:
    """Minimal regex fallback used when bs4 is not installed (tests/CI)."""
    out: dict[str, Any] = {}
    for needle, field_name in RATIO_KEYS.items():
        pat = re.compile(rf">\s*{re.escape(needle)}\s*<.*?([-\d.]+)", re.IGNORECASE | re.DOTALL)
        m = pat.search(html)
        if m:
            dec = _to_decimal(m.group(1))
            if dec is not None:
                out[field_name] = dec
    return out
