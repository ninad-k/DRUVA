"""Optuna-driven hyperparameter optimisation for DRUVA strategies.

Adapted from Jesse (MIT). Differences from Jesse:

  • Optuna is *optional*. If not installed the runner falls back to random
    search so unit tests don't need the extra dependency.
  • Studies persist via SQLite by default (``sqlite:///hyperopt.db``) so they
    can be resumed and dashboards run against them.
  • Multi-objective is collapsed into a single weighted scalar (see
    ``multi_objective_loss``) — keeps Optuna's vanilla TPE sampler usable and
    makes pruning meaningful.

Strategies declare a ``hyperparameters()`` method returning a
``HyperparameterSpace``. The runner calls a user-supplied backtest function
which must return a daily-return ``ndarray``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from app.infrastructure.logging import get_logger
from app.strategies.optimization.losses import LossFn, multi_objective_loss

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Hyperparameter space
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperparameterSpec:
    """Declarative parameter definition."""

    name: str
    kind: str   # "int" | "float" | "categorical" | "log_float"
    low: float | int | None = None
    high: float | int | None = None
    step: float | int | None = None
    choices: Sequence[Any] | None = None


@dataclass
class HyperparameterSpace:
    """Container for a strategy's tunable parameters."""

    specs: list[HyperparameterSpec] = field(default_factory=list)

    def add_int(self, name: str, low: int, high: int, step: int = 1) -> None:
        self.specs.append(HyperparameterSpec(name=name, kind="int", low=low, high=high, step=step))

    def add_float(self, name: str, low: float, high: float, step: float | None = None) -> None:
        self.specs.append(
            HyperparameterSpec(name=name, kind="float", low=low, high=high, step=step)
        )

    def add_log_float(self, name: str, low: float, high: float) -> None:
        self.specs.append(HyperparameterSpec(name=name, kind="log_float", low=low, high=high))

    def add_categorical(self, name: str, choices: Sequence[Any]) -> None:
        self.specs.append(HyperparameterSpec(name=name, kind="categorical", choices=list(choices)))


def suggest_param(spec: HyperparameterSpec, trial: Any) -> Any:
    """Suggest a value for ``spec`` using an Optuna trial."""
    if spec.kind == "int":
        return trial.suggest_int(spec.name, int(spec.low), int(spec.high), step=int(spec.step or 1))
    if spec.kind == "float":
        return trial.suggest_float(spec.name, float(spec.low), float(spec.high), step=spec.step)
    if spec.kind == "log_float":
        return trial.suggest_float(spec.name, float(spec.low), float(spec.high), log=True)
    if spec.kind == "categorical":
        return trial.suggest_categorical(spec.name, list(spec.choices or ()))
    raise ValueError(f"Unknown hyperparameter kind: {spec.kind}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


BacktestFn = Callable[[dict[str, Any]], np.ndarray]
"""``{param_name: value}`` → daily-return ndarray."""


@dataclass
class HyperoptConfig:
    """Run-time configuration for a hyperopt study."""

    n_trials: int = 100
    timeout_s: int | None = None
    seed: int = 1
    storage_url: str | None = None
    """SQLite or Postgres URL; ``None`` means in-memory."""
    study_name: str = "druva-hyperopt"
    n_jobs: int = 1
    sampler: str = "tpe"   # "tpe" | "random"
    direction: str = "minimize"


@dataclass(frozen=True)
class HyperoptResult:
    best_params: dict[str, Any]
    best_value: float
    n_trials: int
    history: list[tuple[dict[str, Any], float]]
    """All ``(params, loss)`` tuples in run order."""


class HyperoptRunner:
    """Optimise a strategy's hyperparameters against a backtest function."""

    def __init__(
        self,
        *,
        space: HyperparameterSpace,
        backtest_fn: BacktestFn,
        loss_fn: LossFn = multi_objective_loss,
        config: HyperoptConfig | None = None,
    ) -> None:
        self._space = space
        self._backtest_fn = backtest_fn
        self._loss_fn = loss_fn
        self._config = config or HyperoptConfig()

    def run(self) -> HyperoptResult:
        try:
            import optuna  # noqa: F401
            return self._run_with_optuna()
        except ImportError:
            logger.warning("hyperopt.optuna_missing_fallback_to_random")
            return self._run_random()

    # ---- Optuna path -----------------------------------------------------

    def _run_with_optuna(self) -> HyperoptResult:
        import optuna

        cfg = self._config
        sampler = (
            optuna.samplers.TPESampler(seed=cfg.seed)
            if cfg.sampler == "tpe"
            else optuna.samplers.RandomSampler(seed=cfg.seed)
        )
        study = optuna.create_study(
            study_name=cfg.study_name,
            storage=cfg.storage_url,
            sampler=sampler,
            direction=cfg.direction,
            load_if_exists=True,
        )
        history: list[tuple[dict[str, Any], float]] = []

        def _objective(trial: optuna.Trial) -> float:
            params = {spec.name: suggest_param(spec, trial) for spec in self._space.specs}
            try:
                returns = self._backtest_fn(params)
            except Exception as exc:  # noqa: BLE001 — surface as a bad trial
                logger.warning("hyperopt.trial_error", error=str(exc), params=params)
                raise optuna.TrialPruned() from exc
            loss = float(self._loss_fn(returns))
            history.append((params, loss))
            return loss

        study.optimize(
            _objective,
            n_trials=cfg.n_trials,
            timeout=cfg.timeout_s,
            n_jobs=cfg.n_jobs,
            gc_after_trial=True,
            show_progress_bar=False,
        )

        return HyperoptResult(
            best_params=dict(study.best_params),
            best_value=float(study.best_value),
            n_trials=len(study.trials),
            history=history,
        )

    # ---- Random fallback -------------------------------------------------

    def _run_random(self) -> HyperoptResult:
        rng = random.Random(self._config.seed)
        history: list[tuple[dict[str, Any], float]] = []
        best_params: dict[str, Any] = {}
        best_value = float("inf")

        for _ in range(self._config.n_trials):
            params = {spec.name: _sample_random(spec, rng) for spec in self._space.specs}
            try:
                returns = self._backtest_fn(params)
            except Exception as exc:  # noqa: BLE001
                logger.warning("hyperopt.random_trial_error", error=str(exc), params=params)
                continue
            loss = float(self._loss_fn(returns))
            history.append((params, loss))
            if loss < best_value:
                best_value = loss
                best_params = params

        return HyperoptResult(
            best_params=best_params,
            best_value=best_value,
            n_trials=len(history),
            history=history,
        )


def _sample_random(spec: HyperparameterSpec, rng: random.Random) -> Any:
    if spec.kind == "int":
        step = int(spec.step or 1)
        low = int(spec.low)
        high = int(spec.high)
        n = (high - low) // step
        return low + step * rng.randint(0, max(n, 0))
    if spec.kind == "float":
        return rng.uniform(float(spec.low), float(spec.high))
    if spec.kind == "log_float":
        low = float(spec.low)
        high = float(spec.high)
        return float(np.exp(rng.uniform(np.log(low), np.log(high))))
    if spec.kind == "categorical":
        return rng.choice(list(spec.choices or ()))
    raise ValueError(f"Unknown hyperparameter kind: {spec.kind}")
