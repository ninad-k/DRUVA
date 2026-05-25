"""ProtectionManager — Phase F2.

Composes multiple Protection instances and exposes a single
``should_block(symbol)`` entry-point consumed by the execution layer.

``build_manager_from_config`` accepts two formats:

**Flat dict** (preferred for settings files)::

    {
        "cooldown":      {"stop_minutes": 60},    # or False to disable
        "stoploss_guard":{"trade_limit": 3},
        "max_drawdown":  {"max_drawdown_pct": 15},
        "low_profit_pairs": False,                # disabled
    }

**List of dicts** (legacy / Freqtrade-style)::

    [
        {"name": "cooldown_period", "stop_minutes": 60},
        {"name": "stoploss_guard",  "trade_limit": 3},
    ]

Passing ``None`` or ``{}`` enables all four protections at default settings.
"""

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
    "low_profit_pairs": LowProfitPairs,
    MaxDrawdownProtection.name: MaxDrawdownProtection,
    "max_drawdown": MaxDrawdownProtection,
    StoplossGuard.name: StoplossGuard,
    "stoploss": StoplossGuard,
    "stoploss_guard": StoplossGuard,
}

# Default insertion order for the flat-dict format.
_FLAT_KEYS: list[tuple[str, type[Protection]]] = [
    ("cooldown", CooldownPeriod),
    ("stoploss_guard", StoplossGuard),
    ("max_drawdown", MaxDrawdownProtection),
    ("low_profit_pairs", LowProfitPairs),
]


@dataclass
class ProtectionManager:
    """Evaluate several protections as one policy."""

    protections: list[Protection] = field(default_factory=list)
    # Internal cache of active blocks keyed by scope-key for active_blocks().
    _active: dict[str, ProtectionDecision] = field(default_factory=dict, repr=False, compare=False)

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
            p.evaluate(
                symbol=symbol,
                now=evaluated_at,
                recent_trades=trades,
                portfolio_state=portfolio_state,
            )
            for p in self.protections
        ]
        blocks = [d for d in decisions if d.blocked]
        if not blocks:
            return ProtectionDecision.allow()

        global_blocks = [d for d in blocks if d.scope == "global"]
        winner = max(global_blocks or blocks, key=lambda d: d.until or evaluated_at)
        # Cache for active_blocks()
        cache_key = "__global__" if winner.scope == "global" else (winner.symbol or "__global__")
        existing = self._active.get(cache_key)
        if existing is None or (winner.until and existing.until and winner.until > existing.until):
            self._active[cache_key] = winner
        return winner

    def should_block(
        self,
        *,
        symbol: str,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
        now: datetime | None = None,
    ) -> ProtectionDecision:
        """Alias for the execution-layer guard check."""
        return self.evaluate(
            symbol=symbol,
            recent_trades=recent_trades,
            portfolio_state=portfolio_state,
            now=now,
        )

    def active_blocks(self, now: datetime | None = None) -> list[ProtectionDecision]:
        """Return all cached blocks that have not yet expired."""
        _now = now or now_utc()
        expired = [k for k, d in self._active.items() if d.until and d.until <= _now]
        for k in expired:
            del self._active[k]
        return list(self._active.values())

    # Expose _protections as alias so both attribute names work.
    @property
    def _protections(self) -> list[Protection]:
        return self.protections


def build_manager_from_config(
    config: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> ProtectionManager:
    """Build a ``ProtectionManager`` from a config dict or list.

    See module docstring for accepted formats.  Passing ``None`` or ``{}``
    enables all four built-in protections at their default settings.
    """
    if config is None:
        config = {}

    # ── Flat-dict format ─────────────────────────────────────────────────
    if isinstance(config, Mapping):
        # Legacy nested format: {"protections": [...]}
        if "protections" in config and isinstance(config["protections"], Iterable):
            return _build_from_list(config["protections"])

        # Flat format: {"cooldown": {...}, "stoploss_guard": False, ...}
        return _build_from_flat_dict(config)

    # ── List format ───────────────────────────────────────────────────────
    return _build_from_list(config)


def _build_from_flat_dict(cfg: Mapping[str, Any]) -> ProtectionManager:
    protections: list[Protection] = []
    for key, cls in _FLAT_KEYS:
        value = cfg.get(key)
        if value is False:
            continue  # explicitly disabled
        kwargs: dict[str, Any] = value if isinstance(value, dict) else {}
        protections.append(cls(**kwargs))
    return ProtectionManager(protections=protections)


def _build_from_list(entries: Iterable[Mapping[str, Any]]) -> ProtectionManager:
    protections: list[Protection] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or entry.get("type") or "").strip().lower()
        cls = _PROTECTION_TYPES.get(name)
        if cls is None:
            raise ValueError(f"Unknown protection type: {name!r}")
        kwargs = {
            k: v
            for k, v in entry.items()
            if k not in {"name", "type", "enabled"} and v is not None
        }
        if entry.get("enabled", True):
            protections.append(cls(**kwargs))
    return ProtectionManager(protections=protections)
