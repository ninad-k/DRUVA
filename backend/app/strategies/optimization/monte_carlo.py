"""Strategy-level Monte Carlo robustness — Phase G.

Adapted from Jesse (MIT). Two complementary tests:

  • ``shuffle_trades``  — randomly reorder a strategy's realised trade
    P&L sequence. A *robust* strategy should land within a tight band of the
    original equity curve; a *fragile* one collapses because returns happened
    to come in a favourable sequence.

  • ``bootstrap_returns`` — sample daily returns with replacement to build
    synthetic equity curves. Wider distributions ⇒ less stable strategy.

Both return :class:`MonteCarloReport` with confidence-interval bands on
final equity, max drawdown, Sharpe and CAGR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from app.infrastructure.logging import get_logger
from app.strategies.optimization.losses import sharpe_loss

logger = get_logger(__name__)


@dataclass(frozen=True)
class MonteCarloReport:
    method: str                          # "shuffle" | "bootstrap"
    n_simulations: int

    median_final_equity: float
    p05_final_equity: float
    p95_final_equity: float

    median_max_drawdown: float
    p95_max_drawdown: float              # 95th percentile *loss* (worst)

    median_sharpe: float
    p05_sharpe: float
    p95_sharpe: float

    median_cagr: float
    p05_cagr: float
    p95_cagr: float

    passes_robustness: bool
    """``True`` iff p05_sharpe > 0 AND p95_max_drawdown < 0.35."""


def shuffle_trades(
    trade_pnls: Sequence[float],
    *,
    n_simulations: int = 1000,
    seed: int = 1,
) -> MonteCarloReport:
    """Trade-order shuffle Monte Carlo.

    Args:
        trade_pnls: realised P&L per trade, expressed as fractional returns
            of starting equity (``0.01 == +1% per trade``).
    """
    pnls = np.asarray(list(trade_pnls), dtype=float)
    if pnls.size == 0:
        return _empty_report("shuffle")
    rng = np.random.default_rng(seed)

    final_eq = np.empty(n_simulations)
    max_dd = np.empty(n_simulations)
    sharpe = np.empty(n_simulations)
    cagr = np.empty(n_simulations)

    for i in range(n_simulations):
        order = rng.permutation(pnls.size)
        equity = np.cumprod(1.0 + pnls[order])
        final_eq[i] = equity[-1]
        max_dd[i] = _max_drawdown(equity)
        # Treat shuffled trade returns as a daily series for Sharpe purposes.
        sharpe[i] = -sharpe_loss(pnls[order])
        cagr[i] = float(equity[-1] ** (252.0 / max(pnls.size, 1)) - 1.0)

    return _summarise("shuffle", n_simulations, final_eq, max_dd, sharpe, cagr)


def bootstrap_returns(
    daily_returns: Sequence[float],
    *,
    n_simulations: int = 1000,
    seed: int = 1,
    horizon_days: int | None = None,
) -> MonteCarloReport:
    """Bootstrap (sample-with-replacement) daily-return Monte Carlo.

    Args:
        daily_returns: realised daily returns as fractions.
        horizon_days: synthetic curve length; defaults to ``len(daily_returns)``.
    """
    returns = np.asarray(list(daily_returns), dtype=float)
    if returns.size == 0:
        return _empty_report("bootstrap")
    horizon = int(horizon_days or returns.size)
    rng = np.random.default_rng(seed)

    final_eq = np.empty(n_simulations)
    max_dd = np.empty(n_simulations)
    sharpe = np.empty(n_simulations)
    cagr = np.empty(n_simulations)

    for i in range(n_simulations):
        sample = returns[rng.integers(0, returns.size, size=horizon)]
        equity = np.cumprod(1.0 + sample)
        final_eq[i] = equity[-1]
        max_dd[i] = _max_drawdown(equity)
        sharpe[i] = -sharpe_loss(sample)
        cagr[i] = float(equity[-1] ** (252.0 / max(horizon, 1)) - 1.0)

    return _summarise("bootstrap", n_simulations, final_eq, max_dd, sharpe, cagr)


def monte_carlo_robustness(
    *,
    trade_pnls: Sequence[float] | None = None,
    daily_returns: Sequence[float] | None = None,
    n_simulations: int = 1000,
    seed: int = 1,
) -> dict[str, MonteCarloReport]:
    """Run both modes back-to-back; either input may be omitted."""
    out: dict[str, MonteCarloReport] = {}
    if trade_pnls is not None:
        out["shuffle"] = shuffle_trades(
            trade_pnls, n_simulations=n_simulations, seed=seed
        )
    if daily_returns is not None:
        out["bootstrap"] = bootstrap_returns(
            daily_returns, n_simulations=n_simulations, seed=seed
        )
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak
    return float(np.max(dd))


def _summarise(
    method: str,
    n_sims: int,
    final_eq: np.ndarray,
    max_dd: np.ndarray,
    sharpe: np.ndarray,
    cagr: np.ndarray,
) -> MonteCarloReport:
    p05_sharpe = float(np.quantile(sharpe, 0.05))
    p95_dd = float(np.quantile(max_dd, 0.95))
    return MonteCarloReport(
        method=method,
        n_simulations=n_sims,
        median_final_equity=float(np.median(final_eq)),
        p05_final_equity=float(np.quantile(final_eq, 0.05)),
        p95_final_equity=float(np.quantile(final_eq, 0.95)),
        median_max_drawdown=float(np.median(max_dd)),
        p95_max_drawdown=p95_dd,
        median_sharpe=float(np.median(sharpe)),
        p05_sharpe=p05_sharpe,
        p95_sharpe=float(np.quantile(sharpe, 0.95)),
        median_cagr=float(np.median(cagr)),
        p05_cagr=float(np.quantile(cagr, 0.05)),
        p95_cagr=float(np.quantile(cagr, 0.95)),
        passes_robustness=(p05_sharpe > 0.0) and (p95_dd < 0.35),
    )


def _empty_report(method: str) -> MonteCarloReport:
    return MonteCarloReport(
        method=method,
        n_simulations=0,
        median_final_equity=1.0,
        p05_final_equity=1.0,
        p95_final_equity=1.0,
        median_max_drawdown=0.0,
        p95_max_drawdown=0.0,
        median_sharpe=0.0,
        p05_sharpe=0.0,
        p95_sharpe=0.0,
        median_cagr=0.0,
        p05_cagr=0.0,
        p95_cagr=0.0,
        passes_robustness=False,
    )
