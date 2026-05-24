"""Protections framework — Phase F2.

Adapted from Freqtrade's ``protections`` module (GPL-3.0 — re-implemented
from public docs, no verbatim copy).

A ``Protection`` is a small policy that inspects recent trade history (or
portfolio state) and may emit a *block* on either a single symbol or the
entire account for a configurable duration. ``ProtectionManager`` composes
multiple protections and exposes a single ``should_block(symbol)`` check
called by the execution layer before any new entry.
"""

from app.core.risk.protections.base import (
    Protection,
    ProtectionDecision,
    ProtectionScope,
    PortfolioMetrics,
    TradeRecord,
)
from app.core.risk.protections.cooldown import CooldownPeriod
from app.core.risk.protections.low_profit_pairs import LowProfitPairs
from app.core.risk.protections.manager import ProtectionManager, build_manager_from_config
from app.core.risk.protections.max_drawdown import MaxDrawdownProtection
from app.core.risk.protections.stoploss_guard import StoplossGuard

__all__ = [
    "Protection",
    "ProtectionDecision",
    "ProtectionScope",
    "PortfolioMetrics",
    "TradeRecord",
    "CooldownPeriod",
    "LowProfitPairs",
    "MaxDrawdownProtection",
    "StoplossGuard",
    "ProtectionManager",
    "build_manager_from_config",
]
