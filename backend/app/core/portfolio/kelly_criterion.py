"""Kelly Criterion position sizing for DRUVA.

Kelly fraction: f* = (bp - q) / b
  b = odds (average_win / average_loss)
  p = win rate (decimal)
  q = 1 - p (loss rate)

Half-Kelly is used by default (f* / 2) for safety.

Example — a strategy with 55% win rate, avg win of 2%, avg loss of 1%:
  b = 2.0 / 1.0 = 2.0
  p = 0.55,  q = 0.45
  f* = (2.0 * 0.55 - 0.45) / 2.0 = 0.325  → 32.5% of capital
  half-Kelly = 16.25%, capped at 10% (DRUVA default max per position)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass
class TradeStats:
    """Aggregated statistics for a single trading strategy.

    Attributes:
        win_rate:     Fraction of trades that are profitable  (0.0–1.0).
        avg_win_pct:  Average P&L of winning trades as a percentage of position.
        avg_loss_pct: Average P&L of losing trades as a *positive* percentage
                      (magnitude of the loss, e.g. 1.5 for a 1.5% loss).
        n_trades:     Total number of closed trades used to compute the stats.
        sharpe:       Annualised Sharpe ratio of the strategy's daily returns.
    """

    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    n_trades: int
    sharpe: float


@dataclass
class KellyResult:
    """Outcome of a Kelly Criterion calculation.

    Attributes:
        full_kelly_pct:   Raw Kelly fraction as a percentage of capital.
        half_kelly_pct:   Full Kelly divided by 2 (the standard practical
                          recommendation for live trading).
        recommended_pct:  The value actually used before the position cap is
                          applied — either full or half Kelly depending on
                          ``use_half_kelly``.
        capped_pct:       Final allocation after applying ``max_position_pct``.
                          This is the value callers should use.
        rationale:        Human-readable one-sentence explanation of the sizing.
    """

    full_kelly_pct: float
    half_kelly_pct: float
    recommended_pct: float
    capped_pct: float
    rationale: str


def compute_kelly(
    stats: TradeStats,
    max_position_pct: float = 10.0,
    use_half_kelly: bool = True,
) -> KellyResult:
    """Compute the Kelly-optimal position size for one strategy.

    Args:
        stats:            Aggregated trade statistics from :class:`TradeStats`.
        max_position_pct: Hard ceiling on position size (default 10 %).
                          No matter how favourable the edge, the allocation
                          will never exceed this value.
        use_half_kelly:   Divide the raw Kelly fraction by 2 before capping.
                          Recommended for live trading to reduce drawdown
                          volatility.

    Returns:
        :class:`KellyResult` with all intermediate values and the final
        ``capped_pct`` ready to use.

    Example::

        stats = TradeStats(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            n_trades=200, sharpe=1.4
        )
        result = compute_kelly(stats)
        # result.full_kelly_pct  ≈ 32.5
        # result.half_kelly_pct  ≈ 16.25
        # result.capped_pct      = 10.0   (capped at default max)
    """
    p = float(stats.win_rate)
    q = 1.0 - p

    if stats.avg_loss_pct <= 0.0:
        logger.warning("kelly.zero_avg_loss", n_trades=stats.n_trades)
        return KellyResult(
            full_kelly_pct=0.0,
            half_kelly_pct=0.0,
            recommended_pct=0.0,
            capped_pct=0.0,
            rationale="Average loss is zero or negative; cannot compute Kelly fraction — no position taken.",
        )

    # b = ratio of average win to average loss (the "odds" term)
    b = stats.avg_win_pct / stats.avg_loss_pct

    # f* = (b*p - q) / b  — expressed as a fraction of capital
    raw_fraction = (b * p - q) / b
    full_kelly_pct = raw_fraction * 100.0

    half_kelly_pct = full_kelly_pct / 2.0
    recommended_pct = half_kelly_pct if use_half_kelly else full_kelly_pct

    # Negative Kelly → negative edge, take no position.
    if recommended_pct < 0.0:
        logger.info(
            "kelly.negative_edge",
            full_kelly_pct=round(full_kelly_pct, 4),
            n_trades=stats.n_trades,
        )
        return KellyResult(
            full_kelly_pct=round(full_kelly_pct, 4),
            half_kelly_pct=round(half_kelly_pct, 4),
            recommended_pct=round(recommended_pct, 4),
            capped_pct=0.0,
            rationale=(
                f"Negative edge (Kelly={full_kelly_pct:.2f}%): strategy has no statistical advantage "
                "— position size capped at 0%."
            ),
        )

    capped_pct = min(recommended_pct, max_position_pct)

    kelly_label = "half-Kelly" if use_half_kelly else "full Kelly"
    cap_applied = capped_pct < recommended_pct
    if cap_applied:
        rationale = (
            f"{kelly_label} of {recommended_pct:.2f}% exceeds the {max_position_pct:.1f}% "
            f"position cap — allocating {capped_pct:.1f}% of capital."
        )
    else:
        rationale = (
            f"{kelly_label} sizing with {stats.win_rate * 100:.1f}% win rate and "
            f"{b:.2f}x win/loss ratio recommends {capped_pct:.2f}% of capital."
        )

    logger.info(
        "kelly.computed",
        full_kelly_pct=round(full_kelly_pct, 4),
        half_kelly_pct=round(half_kelly_pct, 4),
        capped_pct=round(capped_pct, 4),
        n_trades=stats.n_trades,
    )

    return KellyResult(
        full_kelly_pct=round(full_kelly_pct, 4),
        half_kelly_pct=round(half_kelly_pct, 4),
        recommended_pct=round(recommended_pct, 4),
        capped_pct=round(capped_pct, 4),
        rationale=rationale,
    )


def kelly_portfolio_weights(
    strategies: list[TradeStats],
    names: list[str],
    total_capital: float,  # noqa: ARG001 — reserved for future dollar-level output
) -> dict[str, float]:
    """Compute normalised Kelly weights across a portfolio of strategies.

    Each strategy receives its own half-Kelly fraction.  The fractions are then
    normalised so the total does not exceed 100 % of capital.  Strategies with
    negative edge are excluded (allocated 0 %).

    Args:
        strategies:    List of :class:`TradeStats`, one per strategy.
        names:         Strategy names corresponding 1-to-1 with ``strategies``.
        total_capital: Total investable capital in INR (reserved for dollar-value
                       output in future; weights are currently percentage-based).

    Returns:
        Dict mapping ``strategy_name → allocation_pct`` (values sum to ≤ 100).

    Example::

        weights = kelly_portfolio_weights(
            strategies=[stats_a, stats_b],
            names=["MomentumAlpha", "MeanReversionBeta"],
            total_capital=1_000_000,
        )
        # {"MomentumAlpha": 18.4, "MeanReversionBeta": 12.6}
    """
    if len(strategies) != len(names):
        raise ValueError(
            f"strategies and names must have the same length "
            f"(got {len(strategies)} vs {len(names)})"
        )

    raw: dict[str, float] = {}
    for name, stats in zip(names, strategies, strict=True):
        result = compute_kelly(stats, max_position_pct=100.0, use_half_kelly=True)
        raw[name] = max(result.half_kelly_pct, 0.0)

    total_raw = sum(raw.values())
    if total_raw <= 0.0:
        logger.warning("kelly.all_strategies_negative_edge", count=len(strategies))
        return {name: 0.0 for name in names}

    # Normalise so weights sum to 100 % (or keep as-is if already ≤ 100 %).
    if total_raw > 100.0:
        factor = 100.0 / total_raw
        weights = {name: round(pct * factor, 4) for name, pct in raw.items()}
    else:
        weights = {name: round(pct, 4) for name, pct in raw.items()}

    logger.info(
        "kelly.portfolio_weights",
        n_strategies=len(strategies),
        total_allocated_pct=round(sum(weights.values()), 4),
        weights=weights,
    )
    return weights


async def compute_kelly_from_trades(trades: list[dict]) -> TradeStats:
    """Derive :class:`TradeStats` from a raw list of closed trade records.

    Each trade dict must contain at minimum:

    * ``"pnl_pct"`` (float) — realised P&L as a percentage of the position
      value (positive = profit, negative = loss).

    Optional keys (used for logging only):
    * ``"symbol"`` (str), ``"entry"`` (float), ``"exit"`` (float).

    The Sharpe ratio is computed from the per-trade ``pnl_pct`` values,
    annualised assuming roughly 252 trading days per year.

    Args:
        trades: List of trade dicts as described above.

    Returns:
        :class:`TradeStats` ready to pass to :func:`compute_kelly`.

    Example::

        stats = await compute_kelly_from_trades([
            {"pnl_pct": 1.8, "symbol": "RELIANCE"},
            {"pnl_pct": -0.9, "symbol": "RELIANCE"},
            {"pnl_pct": 2.3, "symbol": "RELIANCE"},
        ])
        # stats.win_rate ≈ 0.667, stats.avg_win_pct ≈ 2.05, stats.avg_loss_pct = 0.9
    """
    if not trades:
        logger.warning("kelly.no_trades_provided")
        return TradeStats(
            win_rate=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            n_trades=0,
            sharpe=0.0,
        )

    pnl_pcts: list[float] = []
    for t in trades:
        val = t.get("pnl_pct")
        if val is None:
            continue
        try:
            pnl_pcts.append(float(val))
        except (TypeError, ValueError):
            logger.warning("kelly.bad_pnl_pct", raw=repr(val))

    n = len(pnl_pcts)
    if n == 0:
        return TradeStats(
            win_rate=0.0, avg_win_pct=0.0, avg_loss_pct=0.0, n_trades=0, sharpe=0.0
        )

    wins = [p for p in pnl_pcts if p > 0.0]
    losses = [abs(p) for p in pnl_pcts if p < 0.0]

    win_rate = len(wins) / n
    avg_win_pct = statistics.mean(wins) if wins else 0.0
    avg_loss_pct = statistics.mean(losses) if losses else 0.0

    # Sharpe: mean / stdev of per-trade returns, annualised √252.
    if n > 1:
        mean_pnl = statistics.mean(pnl_pcts)
        stdev_pnl = statistics.stdev(pnl_pcts)
        sharpe = (mean_pnl / stdev_pnl * math.sqrt(252)) if stdev_pnl > 0 else 0.0
    else:
        sharpe = 0.0

    logger.info(
        "kelly.trades_aggregated",
        n_trades=n,
        win_rate=round(win_rate, 4),
        avg_win_pct=round(avg_win_pct, 4),
        avg_loss_pct=round(avg_loss_pct, 4),
        sharpe=round(sharpe, 4),
        computed_at=utcnow().isoformat(),
    )

    return TradeStats(
        win_rate=win_rate,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        n_trades=n,
        sharpe=sharpe,
    )
