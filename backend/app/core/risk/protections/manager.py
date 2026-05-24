"""Composition layer for risk protections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

from app.core.risk.protections.base import (
    PortfolioMetrics,
    Protection,
    ProtectionDecision,
    TradeRecord,
    now_utc,
)
from app.core.risk.protections.cooldown import CooldownPeriod
from app.core.risk.protections.low_profit_pairs import LowProfitPairs
from app.core.risk.protections.max_drawdown import MaxDrawdownProtection
from app.core.risk.protections.stoploss_guard import StoplossGuard


_PROTECTION_TYPES: dict[str, type[Protection]] = {
    CooldownPeriod.name: CooldownPeriod,
    "cooldown": CooldownPeriod,
    LowProfitPairs.name: LowProfitPairs,
    "low_profit": LowProfitPairs,
    MaxDrawdownProtection.name: MaxDrawdownProtection,
    "max_drawdown": MaxDrawdownProtection,
    StoplossGuard.name: StoplossGuard,
    "stoploss": StoplossGuard,
}


@dataclass
class ProtectionManager:
    """Evaluate several protections as one policy."""

    protections: list[Protection] = field(default_factory=list)

    def evaluate(
        self,
        *,
        symbol: str,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
        now: datetime | None = None,
    ) -> ProtectionDecision:
        """Return the highest-priority block, or allow when no policy blocks."""
        evaluated_at = now or now_utc()
        trades = list(recent_trades)
        decisions = [
            protection.evaluate(
                symbol=symbol,
                now=evaluated_at,
                recent_trades=trades,
                portfolio_state=portfolio_state,
            )
            for protection in self.protections
        ]
        blocks = [decision for decision in decisions if decision.blocked]
        if not blocks:
            return ProtectionDecision.allow()

        global_blocks = [decision for decision in blocks if decision.scope == "global"]
        candidates = global_blocks or blocks
        return max(candidates, key=lambda decision: decision.until or evaluated_at)

    def should_block(
        self,
        *,
        symbol: str,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
        now: datetime | None = None,
    ) -> ProtectionDecision:
        """Compatibility alias for execution-layer guard checks."""
        return self.evaluate(
            symbol=symbol,
            recent_trades=recent_trades,
            portfolio_state=portfolio_state,
            now=now,
        )


def build_manager_from_config(config: Iterable[Mapping[str, Any]] | Mapping[str, Any]) -> ProtectionManager:
    """Build a manager from dictionaries with ``name``/``type`` plus kwargs."""
    entries: Iterable[Mapping[str, Any]]
    if isinstance(config, Mapping):
        raw_entries = config.get("protections", [])
        entries = raw_entries if isinstance(raw_entries, Iterable) else []
    else:
        entries = config

    protections: list[Protection] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or entry.get("type") or "").strip().lower()
        cls = _PROTECTION_TYPES.get(name)
        if cls is None:
            raise ValueError(f"Unknown protection type: {name}")
        kwargs = {
            key: value
            for key, value in entry.items()
            if key not in {"name", "type", "enabled"} and value is not None
        }
        if entry.get("enabled", True):
            protections.append(cls(**kwargs))

    return ProtectionManager(protections=protections)
