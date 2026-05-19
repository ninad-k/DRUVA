"""Monte Carlo portfolio path simulator for goal projection.

Simulates `n_simulations` monthly portfolio paths using log-normal returns,
a step-up SIP schedule, and optional regime-aware return adjustment.

Returns P10 / P50 / P90 outcome bands and probability of reaching the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MonteCarloInput:
    current_value: float          # current portfolio value (₹)
    monthly_sip: float            # monthly SIP contribution (₹)
    target_corpus: float          # goal target (₹)
    horizon_years: float          # investment horizon in years
    annual_return_pct: float = 12.0   # expected annualised return (%)
    annual_volatility_pct: float = 18.0  # annualised volatility (%)
    sip_step_up_pct: float = 10.0    # annual SIP step-up (%)
    n_simulations: int = 1000
    seed: int = 42
    # Optional regime-based return adjustment (applied to mean return)
    regime_return_adj_pct: float = 0.0  # e.g. -3.0 in Bear, +2.0 in Bull


@dataclass
class MonteCarloResult:
    # Summary statistics at horizon
    p10: float = 0.0   # 10th percentile final value
    p25: float = 0.0
    p50: float = 0.0   # median
    p75: float = 0.0
    p90: float = 0.0   # 90th percentile final value
    probability_of_success: float = 0.0  # fraction of paths ≥ target_corpus
    expected_final_value: float = 0.0
    worst_case: float = 0.0   # 5th percentile
    best_case: float = 0.0    # 95th percentile
    # Monthly fan data: list of (month, p10, p25, p50, p75, p90) tuples
    fan_data: list[dict[str, float]] = field(default_factory=list)
    # Input echo
    horizon_months: int = 0
    target_corpus: float = 0.0
    total_invested: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "p10": round(self.p10, 2),
            "p25": round(self.p25, 2),
            "p50": round(self.p50, 2),
            "p75": round(self.p75, 2),
            "p90": round(self.p90, 2),
            "probability_of_success": round(self.probability_of_success, 4),
            "expected_final_value": round(self.expected_final_value, 2),
            "worst_case": round(self.worst_case, 2),
            "best_case": round(self.best_case, 2),
            "horizon_months": self.horizon_months,
            "target_corpus": round(self.target_corpus, 2),
            "total_invested": round(self.total_invested, 2),
            "fan_data": [
                {k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()}
                for row in self.fan_data
            ],
        }


def run_simulation(inp: MonteCarloInput) -> MonteCarloResult:
    """Run Monte Carlo simulation and return percentile bands.

    Each path is simulated month-by-month:
      portfolio(t+1) = portfolio(t) * exp(μ_m + σ_m * Z) + sip(t)

    where:
      μ_m = monthly mean log return (adjusted for regime)
      σ_m = monthly volatility
      Z   ~ N(0, 1) independent per simulation per month
      sip(t) steps up by sip_step_up_pct each January

    Args:
        inp: MonteCarloInput parameters.

    Returns:
        MonteCarloResult with fan data and probability of reaching target.
    """
    rng = np.random.default_rng(inp.seed)

    horizon_months = max(1, round(inp.horizon_years * 12))

    # Annualised → monthly parameters (log-normal)
    adj_annual_return = inp.annual_return_pct + inp.regime_return_adj_pct
    annual_mu = np.log(1 + adj_annual_return / 100)
    annual_sigma = inp.annual_volatility_pct / 100
    monthly_mu = annual_mu / 12
    monthly_sigma = annual_sigma / np.sqrt(12)

    n = inp.n_simulations

    # Paths matrix: shape (n_simulations, horizon_months + 1)
    paths = np.empty((n, horizon_months + 1), dtype=np.float64)
    paths[:, 0] = inp.current_value

    # Track SIP per simulation per month (all sims get the same SIP schedule)
    sip_schedule = _build_sip_schedule(inp.monthly_sip, inp.sip_step_up_pct, horizon_months)

    # Simulate
    Z = rng.standard_normal((n, horizon_months))
    for t in range(horizon_months):
        log_ret = monthly_mu + monthly_sigma * Z[:, t]
        paths[:, t + 1] = paths[:, t] * np.exp(log_ret) + sip_schedule[t]

    final_values = paths[:, -1]

    # Percentiles at horizon
    p5, p10, p25, p50, p75, p90, p95 = np.percentile(
        final_values, [5, 10, 25, 50, 75, 90, 95]
    )

    # Probability of success
    success_mask = final_values >= inp.target_corpus
    prob_success = float(success_mask.mean())

    # Fan data: monthly percentiles (sample every month, but return every month)
    fan_data: list[dict[str, float]] = []
    for t in range(horizon_months + 1):
        col = paths[:, t]
        tp10, tp25, tp50, tp75, tp90 = np.percentile(col, [10, 25, 50, 75, 90])
        fan_data.append({
            "month": float(t),
            "p10": float(tp10),
            "p25": float(tp25),
            "p50": float(tp50),
            "p75": float(tp75),
            "p90": float(tp90),
        })

    total_invested = inp.current_value + float(sum(sip_schedule))

    return MonteCarloResult(
        p10=float(p10),
        p25=float(p25),
        p50=float(p50),
        p75=float(p75),
        p90=float(p90),
        probability_of_success=prob_success,
        expected_final_value=float(final_values.mean()),
        worst_case=float(p5),
        best_case=float(p95),
        fan_data=fan_data,
        horizon_months=horizon_months,
        target_corpus=inp.target_corpus,
        total_invested=total_invested,
    )


def _build_sip_schedule(
    monthly_sip: float,
    step_up_pct: float,
    horizon_months: int,
) -> list[float]:
    """Return per-month SIP amounts with annual step-up."""
    schedule: list[float] = []
    sip = monthly_sip
    for month in range(1, horizon_months + 1):
        schedule.append(sip)
        if month % 12 == 0:
            sip *= 1 + step_up_pct / 100
    return schedule
