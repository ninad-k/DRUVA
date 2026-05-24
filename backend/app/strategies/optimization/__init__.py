"""Strategy-optimization toolkit.

Phases E (Optuna hyperopt), F1 (lookahead-bias detector) and G (Monte-Carlo
robustness) all live here. Patterns adapted from Jesse (MIT) and Freqtrade
(GPL-3.0 — reimplemented from public docs, no verbatim copy).
"""

from app.strategies.optimization.hyperopt import (
    HyperoptConfig,
    HyperoptResult,
    HyperoptRunner,
    HyperparameterSpace,
    suggest_param,
)
from app.strategies.optimization.lookahead import (
    LookaheadReport,
    detect_lookahead_bias,
)
from app.strategies.optimization.losses import (
    LossFn,
    calmar_loss,
    cvar_loss,
    multi_objective_loss,
    sharpe_loss,
    sortino_loss,
)
from app.strategies.optimization.monte_carlo import (
    MonteCarloReport,
    bootstrap_returns,
    monte_carlo_robustness,
    shuffle_trades,
)

__all__ = [
    "HyperoptConfig",
    "HyperoptResult",
    "HyperoptRunner",
    "HyperparameterSpace",
    "suggest_param",
    "LookaheadReport",
    "detect_lookahead_bias",
    "LossFn",
    "calmar_loss",
    "cvar_loss",
    "multi_objective_loss",
    "sharpe_loss",
    "sortino_loss",
    "MonteCarloReport",
    "bootstrap_returns",
    "monte_carlo_robustness",
    "shuffle_trades",
]
