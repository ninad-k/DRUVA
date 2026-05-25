"""IndicatorRegistry — Phase K.

Central registry mapping indicator names to their implementations.
Supports both the native numpy implementations and an optional pandas-ta
bridge for the extended indicator catalogue.

Usage::

    from app.core.indicators.registry import registry

    result = registry.compute("rsi", close=closes, length=14)
    result = registry.compute("macd", close=closes, fast=12, slow=26, signal=9)

    # List available indicators
    meta_list = registry.list_indicators()
    meta_list = registry.list_indicators(category="volatility")
"""

from __future__ import annotations

import importlib
from typing import Any, Sequence

import numpy as np

from app.core.indicators.base import IndicatorMeta, IndicatorResult
from app.core.indicators import numpy_impl as _ni


class IndicatorRegistry:
    """Registry of all available indicators."""

    def __init__(self) -> None:
        self._native: dict[str, tuple[Any, IndicatorMeta]] = {}
        self._register_all()

    def _register_all(self) -> None:
        """Register all native numpy indicators with explicit metadata."""
        C, O = "overlap", "other"
        entries: list[tuple[str, Any, IndicatorMeta]] = [
            # Overlap
            ("sma",         _ni.sma,         IndicatorMeta("sma",         "Simple Moving Average",      "overlap", {"length": 20})),
            ("ema",         _ni.ema,         IndicatorMeta("ema",         "Exponential Moving Average", "overlap", {"length": 20})),
            ("wma",         _ni.wma,         IndicatorMeta("wma",         "Weighted Moving Average",    "overlap", {"length": 20})),
            ("dema",        _ni.dema,        IndicatorMeta("dema",        "Double EMA",                 "overlap", {"length": 20})),
            ("tema",        _ni.tema,        IndicatorMeta("tema",        "Triple EMA",                 "overlap", {"length": 20})),
            ("hma",         _ni.hma,         IndicatorMeta("hma",         "Hull Moving Average",        "overlap", {"length": 20})),
            ("vwap",        _ni.vwap,        IndicatorMeta("vwap",        "VWAP",                       "overlap")),
            # Trend
            ("macd",        _ni.macd,        IndicatorMeta("macd",        "MACD",                       "trend",      {"fast": 12, "slow": 26, "signal": 9},  ("macd", "signal", "histogram"))),
            ("adx",         _ni.adx,         IndicatorMeta("adx",         "Average Directional Index",  "trend",      {"length": 14},  ("adx", "di_plus", "di_minus"))),
            ("ichimoku",    _ni.ichimoku,    IndicatorMeta("ichimoku",    "Ichimoku Cloud",             "trend",      {"tenkan": 9, "kijun": 26},  ("tenkan", "kijun", "senkou_a", "senkou_b", "chikou"))),
            ("supertrend",  _ni.supertrend,  IndicatorMeta("supertrend",  "Supertrend",                 "trend",      {"atr_length": 7, "multiplier": 3.0},  ("supertrend", "direction"))),
            # Momentum
            ("rsi",         _ni.rsi,         IndicatorMeta("rsi",         "Relative Strength Index",    "momentum",   {"length": 14})),
            ("stochastic",  _ni.stochastic,  IndicatorMeta("stochastic",  "Stochastic Oscillator",      "momentum",   {"k_length": 14, "d_length": 3},  ("k", "d"))),
            ("cci",         _ni.cci,         IndicatorMeta("cci",         "Commodity Channel Index",    "momentum",   {"length": 20})),
            ("roc",         _ni.roc,         IndicatorMeta("roc",         "Rate of Change",             "momentum",   {"length": 10})),
            ("williams_r",  _ni.williams_r,  IndicatorMeta("williams_r",  "Williams %R",                "momentum",   {"length": 14})),
            ("mfi",         _ni.mfi,         IndicatorMeta("mfi",         "Money Flow Index",           "momentum",   {"length": 14})),
            ("tsi",         _ni.tsi,         IndicatorMeta("tsi",         "True Strength Index",        "momentum",   {"fast": 13, "slow": 25})),
            ("dpo",         _ni.dpo,         IndicatorMeta("dpo",         "Detrended Price Oscillator", "momentum",   {"length": 20})),
            ("ppo",         _ni.ppo,         IndicatorMeta("ppo",         "Percentage Price Oscillator","momentum",   {"fast": 12, "slow": 26, "signal": 9},  ("ppo", "signal", "histogram"))),
            # Volatility
            ("atr",         _ni.atr,         IndicatorMeta("atr",         "Average True Range",         "volatility", {"length": 14})),
            ("bbands",      _ni.bollinger_bands,    IndicatorMeta("bbands",      "Bollinger Bands",       "volatility", {"length": 20, "std_dev": 2.0},  ("upper", "mid", "lower"))),
            ("keltner",     _ni.keltner_channels,   IndicatorMeta("keltner",     "Keltner Channels",      "volatility", {"ema_length": 20, "atr_length": 10},  ("upper", "mid", "lower"))),
            ("donchian",    _ni.donchian_channels,  IndicatorMeta("donchian",    "Donchian Channels",     "volatility", {"length": 20},  ("upper", "mid", "lower"))),
            ("hv",          _ni.historical_volatility, IndicatorMeta("hv",       "Historical Volatility", "volatility", {"length": 20})),
            ("chaikin_vol", _ni.chaikin_volatility, IndicatorMeta("chaikin_vol", "Chaikin Volatility",    "volatility", {"ema_length": 10, "roc_length": 10})),
            # Volume
            ("obv",         _ni.obv,         IndicatorMeta("obv",         "On-Balance Volume",          "volume")),
            ("vwma",        _ni.vwma,        IndicatorMeta("vwma",        "Volume-Weighted MA",         "volume",     {"length": 20})),
            ("cmf",         _ni.chaikin_mf,  IndicatorMeta("cmf",         "Chaikin Money Flow",         "volume",     {"length": 20})),
            ("emv",         _ni.ease_of_movement,  IndicatorMeta("emv",   "Ease of Movement",           "volume",     {"length": 14})),
            ("force_index", _ni.force_index, IndicatorMeta("force_index", "Force Index",                "volume",     {"length": 13})),
            # Cycle / other
            ("aroon",       _ni.aroon,       IndicatorMeta("aroon",       "Aroon",                      "cycle",      {"length": 25},  ("up", "down", "oscillator"))),
            ("pivot",       _ni.pivot_points,IndicatorMeta("pivot",       "Pivot Points",               "other",      {},  ("pp", "r1", "r2", "s1", "s2"))),
        ]
        for name, fn, meta in entries:
            self._native[name] = (fn, meta)

    def compute(
        self,
        name: str,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Compute an indicator by name.

        Parameters are passed as keyword arguments.  OHLCV arrays use the
        conventional parameter names: ``close``, ``high``, ``low``, ``volume``.

        If the indicator is not found in the native registry, falls through to
        the pandas-ta bridge (if installed).

        Raises ``KeyError`` if the indicator is not available.
        """
        name_lower = name.lower()
        if name_lower in self._native:
            fn, _ = self._native[name_lower]
            return fn(**kwargs)

        # Pandas-ta bridge
        return self._pandas_ta_compute(name_lower, **kwargs)

    def _pandas_ta_compute(self, name: str, **kwargs: Any) -> IndicatorResult:
        """Delegate to pandas-ta when the native impl is absent."""
        try:
            import pandas as pd
            import pandas_ta as ta
        except ImportError as exc:
            raise KeyError(
                f"Indicator '{name}' not found in native registry and pandas-ta is not installed"
            ) from exc

        close = kwargs.pop("close", None)
        high = kwargs.pop("high", None)
        low = kwargs.pop("low", None)
        volume = kwargs.pop("volume", None)
        open_ = kwargs.pop("open", None)

        df = pd.DataFrame({
            "close": close if close is not None else [],
            **({"high": high} if high is not None else {}),
            **({"low": low} if low is not None else {}),
            **({"volume": volume} if volume is not None else {}),
            **({"open": open_} if open_ is not None else {}),
        })
        df.ta.strategy(ta.Strategy(
            name="custom",
            ta=[{"kind": name, **kwargs}],
        ))

        # Extract the result columns — pandas-ta prefixes with indicator name
        result_cols = [c for c in df.columns if c.lower().startswith(name.lower())]
        if not result_cols:
            raise KeyError(f"pandas-ta computed nothing for indicator '{name}'")

        meta = IndicatorMeta(name=name, display_name=name.upper(), category="other",
                             outputs=tuple(result_cols))
        arrays = {col: df[col].to_numpy(dtype=float) for col in result_cols}
        return IndicatorResult(meta=meta, arrays=arrays)

    def list_indicators(self, category: str | None = None) -> list[IndicatorMeta]:
        """List all registered native indicators, optionally filtered by category."""
        metas = [meta for _, meta in self._native.values()]
        if category:
            metas = [m for m in metas if m.category == category]
        return sorted(metas, key=lambda m: (m.category, m.name))

    def categories(self) -> list[str]:
        return sorted({meta.category for _, meta in self._native.values()})

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._native


registry = IndicatorRegistry()
