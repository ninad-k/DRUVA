"""Unit tests for the protections framework — Phase F2."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.risk.protections import (
    CooldownPeriod,
    LowProfitPairs,
    MaxDrawdownProtection,
    PortfolioMetrics,
    ProtectionDecision,
    ProtectionManager,
    StoplossGuard,
    TradeRecord,
    build_manager_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def metrics(total: float = 100_000, peak: float = 100_000) -> PortfolioMetrics:
    return PortfolioMetrics(total_value=total, peak_value=peak)


def trade(
    symbol: str = "RELIANCE",
    closed_at: str = "2024-01-01T10:00:00",
    pnl_pct: float = -0.02,
    hit_stoploss: bool = False,
) -> TradeRecord:
    return TradeRecord(
        symbol=symbol,
        closed_at=utc(closed_at),
        pnl_pct=pnl_pct,
        hit_stoploss=hit_stoploss,
    )


NOW = utc("2024-01-01T12:00:00")


# ---------------------------------------------------------------------------
# ProtectionDecision
# ---------------------------------------------------------------------------

class TestProtectionDecision:
    def test_allow_not_blocked(self):
        d = ProtectionDecision.allow()
        assert not d.blocked

    def test_block_symbol(self):
        d = ProtectionDecision.block_symbol(
            symbol="INFY", until=utc("2024-01-02T00:00:00"), reason="test"
        )
        assert d.blocked
        assert d.scope == "symbol"
        assert d.symbol == "INFY"

    def test_block_global(self):
        d = ProtectionDecision.block_global(until=utc("2024-01-02T00:00:00"), reason="test")
        assert d.blocked
        assert d.scope == "global"
        assert d.symbol is None


# ---------------------------------------------------------------------------
# CooldownPeriod
# ---------------------------------------------------------------------------

class TestCooldownPeriod:
    def test_blocks_within_window(self):
        p = CooldownPeriod(stop_minutes=120)
        # trade closed 30 minutes ago → still in cooldown
        t = trade(symbol="RELIANCE", closed_at="2024-01-01T11:30:00")
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[t], portfolio_state=metrics())
        assert d.blocked
        assert d.scope == "symbol"
        assert d.symbol == "RELIANCE"

    def test_allows_after_window(self):
        p = CooldownPeriod(stop_minutes=60)
        # trade closed 2 hours ago → window elapsed
        t = trade(symbol="RELIANCE", closed_at="2024-01-01T10:00:00")
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[t], portfolio_state=metrics())
        assert not d.blocked

    def test_ignores_other_symbols(self):
        p = CooldownPeriod(stop_minutes=120)
        t = trade(symbol="INFY", closed_at="2024-01-01T11:30:00")
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[t], portfolio_state=metrics())
        assert not d.blocked

    def test_no_trades_allows(self):
        p = CooldownPeriod()
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[], portfolio_state=metrics())
        assert not d.blocked


# ---------------------------------------------------------------------------
# StoplossGuard
# ---------------------------------------------------------------------------

class TestStoplossGuard:
    def _make_sl_trades(self, n: int, symbol: str = "RELIANCE") -> list[TradeRecord]:
        return [
            trade(symbol=symbol, closed_at="2024-01-01T11:00:00", hit_stoploss=True)
            for _ in range(n)
        ]

    def test_blocks_global_when_limit_exceeded(self):
        p = StoplossGuard(lookback_minutes=1440, trade_limit=3, stop_minutes=60)
        trades = self._make_sl_trades(4)
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert d.blocked
        assert d.scope == "global"

    def test_allows_below_limit(self):
        p = StoplossGuard(lookback_minutes=1440, trade_limit=4, stop_minutes=60)
        trades = self._make_sl_trades(3)
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked

    def test_per_symbol_flag(self):
        p = StoplossGuard(lookback_minutes=1440, trade_limit=2, stop_minutes=60, only_per_symbol=True)
        trades = [
            trade(symbol="RELIANCE", closed_at="2024-01-01T11:00:00", hit_stoploss=True),
            trade(symbol="RELIANCE", closed_at="2024-01-01T11:05:00", hit_stoploss=True),
        ]
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert d.blocked
        assert d.scope == "symbol"

    def test_per_symbol_ignores_other_symbols(self):
        p = StoplossGuard(lookback_minutes=1440, trade_limit=2, stop_minutes=60, only_per_symbol=True)
        # 4 SL trades on a different symbol — should not affect RELIANCE
        trades = self._make_sl_trades(4, symbol="INFY")
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked

    def test_ignores_trades_outside_window(self):
        p = StoplossGuard(lookback_minutes=60, trade_limit=2, stop_minutes=60)
        # Trade happened 2 hours ago — outside 60-min window
        old = trade(symbol="RELIANCE", closed_at="2024-01-01T10:00:00", hit_stoploss=True)
        recent = trade(symbol="RELIANCE", closed_at="2024-01-01T11:45:00", hit_stoploss=True)
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[old, recent], portfolio_state=metrics())
        assert not d.blocked  # only 1 recent SL, limit=2


# ---------------------------------------------------------------------------
# MaxDrawdownProtection
# ---------------------------------------------------------------------------

class TestMaxDrawdownProtection:
    def test_blocks_on_breach(self):
        p = MaxDrawdownProtection(max_drawdown_pct=10.0, stop_minutes=1440)
        m = metrics(total=85_000, peak=100_000)  # 15% drawdown
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[], portfolio_state=m)
        assert d.blocked
        assert d.scope == "global"

    def test_allows_below_threshold(self):
        p = MaxDrawdownProtection(max_drawdown_pct=20.0, stop_minutes=1440)
        m = metrics(total=85_000, peak=100_000)  # 15% drawdown
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[], portfolio_state=m)
        assert not d.blocked

    def test_uses_peak_when_current_above_recorded_peak(self):
        # Edge case: total > recorded peak (peak not yet updated) — use total as peak
        p = MaxDrawdownProtection(max_drawdown_pct=10.0, stop_minutes=1440)
        m = metrics(total=105_000, peak=100_000)
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[], portfolio_state=m)
        assert not d.blocked  # drawdown = 0%

    def test_exact_boundary(self):
        p = MaxDrawdownProtection(max_drawdown_pct=15.0, stop_minutes=60)
        m = metrics(total=85_000, peak=100_000)  # exactly 15%
        d = p.evaluate(symbol="RELIANCE", now=NOW, recent_trades=[], portfolio_state=m)
        assert d.blocked  # ≥ limit


# ---------------------------------------------------------------------------
# LowProfitPairs
# ---------------------------------------------------------------------------

class TestLowProfitPairs:
    def _make_trades(self, pnls: list[float], symbol: str = "INFY") -> list[TradeRecord]:
        return [
            TradeRecord(
                symbol=symbol,
                closed_at=utc("2024-01-01T10:00:00"),
                pnl_pct=p,
            )
            for p in pnls
        ]

    def test_blocks_low_profit_symbol(self):
        p = LowProfitPairs(lookback_minutes=10080, min_profit_pct=1.0, required_trades=3, stop_minutes=1440)
        trades = self._make_trades([-0.02, -0.01, -0.015])  # mean = -1.67%
        d = p.evaluate(symbol="INFY", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert d.blocked
        assert d.scope == "symbol"

    def test_allows_profitable_symbol(self):
        p = LowProfitPairs(lookback_minutes=10080, min_profit_pct=0.0, required_trades=3, stop_minutes=1440)
        trades = self._make_trades([0.01, 0.02, 0.015])  # mean = +1.67%
        d = p.evaluate(symbol="INFY", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked

    def test_skips_when_insufficient_trades(self):
        p = LowProfitPairs(lookback_minutes=10080, min_profit_pct=0.0, required_trades=5, stop_minutes=1440)
        trades = self._make_trades([-0.05, -0.05])  # only 2 trades
        d = p.evaluate(symbol="INFY", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked

    def test_ignores_other_symbols(self):
        p = LowProfitPairs(lookback_minutes=10080, min_profit_pct=0.0, required_trades=3, stop_minutes=1440)
        trades = self._make_trades([-0.05, -0.05, -0.05], symbol="RELIANCE")
        # RELIANCE losing, but we're checking INFY
        d = p.evaluate(symbol="INFY", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked

    def test_ignores_trades_outside_window(self):
        p = LowProfitPairs(lookback_minutes=60, min_profit_pct=0.0, required_trades=3, stop_minutes=1440)
        # Trades happened 2 hours ago — outside the 60-min window
        trades = [
            TradeRecord(symbol="INFY", closed_at=utc("2024-01-01T09:00:00"), pnl_pct=-0.05)
            for _ in range(5)
        ]
        d = p.evaluate(symbol="INFY", now=NOW, recent_trades=trades, portfolio_state=metrics())
        assert not d.blocked


# ---------------------------------------------------------------------------
# ProtectionManager
# ---------------------------------------------------------------------------

class TestProtectionManager:
    def test_allow_when_no_protections(self):
        mgr = ProtectionManager(protections=[])
        d = mgr.should_block(symbol="RELIANCE", recent_trades=[], portfolio_state=metrics())
        assert not d.blocked

    def test_returns_first_block(self):
        # MaxDrawdown fires first (global block)
        mgr = ProtectionManager(protections=[
            MaxDrawdownProtection(max_drawdown_pct=10.0, stop_minutes=60),
            CooldownPeriod(stop_minutes=120),
        ])
        m = metrics(total=85_000, peak=100_000)
        t = trade(closed_at="2024-01-01T11:30:00")
        d = mgr.should_block(symbol="RELIANCE", recent_trades=[t], portfolio_state=m, now=NOW)
        assert d.blocked
        assert d.scope == "global"

    def test_symbol_block_when_no_global_block(self):
        mgr = ProtectionManager(protections=[
            CooldownPeriod(stop_minutes=120),
        ])
        t = trade(symbol="RELIANCE", closed_at="2024-01-01T11:30:00")
        d = mgr.should_block(symbol="RELIANCE", recent_trades=[t], portfolio_state=metrics(), now=NOW)
        assert d.blocked
        assert d.scope == "symbol"

    def test_allows_when_all_pass(self):
        mgr = ProtectionManager(protections=[
            CooldownPeriod(stop_minutes=30),
            MaxDrawdownProtection(max_drawdown_pct=50.0),
        ])
        t = trade(closed_at="2024-01-01T10:00:00")  # 2 hours ago
        d = mgr.should_block(symbol="RELIANCE", recent_trades=[t], portfolio_state=metrics(), now=NOW)
        assert not d.blocked

    def test_active_blocks_returns_cached(self):
        mgr = ProtectionManager(protections=[CooldownPeriod(stop_minutes=120)])
        t = trade(symbol="RELIANCE", closed_at="2024-01-01T11:30:00")
        mgr.should_block(symbol="RELIANCE", recent_trades=[t], portfolio_state=metrics(), now=NOW)
        active = mgr.active_blocks(now=NOW)
        assert len(active) == 1
        assert active[0].symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# build_manager_from_config
# ---------------------------------------------------------------------------

class TestBuildManagerFromConfig:
    def test_default_config_has_four_protections(self):
        mgr = build_manager_from_config()
        assert len(mgr._protections) == 4

    def test_custom_cooldown(self):
        mgr = build_manager_from_config({"cooldown": {"stop_minutes": 180}})
        cp = next(p for p in mgr._protections if isinstance(p, CooldownPeriod))
        assert cp.stop_minutes == 180

    def test_disable_protection_with_false(self):
        mgr = build_manager_from_config({"cooldown": False})
        assert not any(isinstance(p, CooldownPeriod) for p in mgr._protections)

    def test_empty_config_defaults(self):
        mgr = build_manager_from_config({})
        assert len(mgr._protections) == 4

    def test_list_config_style(self):
        """Legacy: build_manager_from_config also accepts the list-of-dicts style."""
        cfg = [
            {"name": "cooldown_period", "stop_minutes": 45},
            {"name": "stoploss_guard", "trade_limit": 3},
        ]
        mgr = build_manager_from_config(cfg)
        assert len(mgr._protections) == 2
        cp = next(p for p in mgr._protections if isinstance(p, CooldownPeriod))
        assert cp.stop_minutes == 45
