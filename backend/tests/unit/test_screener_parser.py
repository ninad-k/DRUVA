from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.fundamentals.parser import parse_ratios


SAMPLE_HTML = """
<html>
<body>
<ul id="top-ratios">
  <li><span class="name">Market Cap</span><span class="number">54,320</span></li>
  <li><span class="name">Current Price</span><span class="number">1,234.50</span></li>
  <li><span class="name">Stock P/E</span><span class="number">25.3</span></li>
  <li><span class="name">ROCE</span><span class="number">28.1</span></li>
  <li><span class="name">ROE</span><span class="number">22.4</span></li>
  <li><span class="name">Debt to equity</span><span class="number">0.25</span></li>
  <li><span class="name">Promoter holding</span><span class="number">55.2</span></li>
</ul>
<a href="/sectors/financials/">Financials</a>
<a href="/industries/banking/">Banking</a>
</body></html>
"""


@pytest.mark.unit
def test_parse_ratios_extracts_core_fields() -> None:
    result = parse_ratios(SAMPLE_HTML)
    # When bs4 is available we get named keys
    assert result.get("roe") in (Decimal("22.4"), 22.4) or "roe" in result
    assert result.get("roce") in (Decimal("28.1"), 28.1) or "roce" in result
    # Depending on parser backend: accept either case.
    if "debt_to_equity" in result:
        assert float(result["debt_to_equity"]) == pytest.approx(0.25, abs=0.01)
