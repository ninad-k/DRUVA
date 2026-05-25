"""FilterPipeline — Phase F3.

Composes multiple ``PairFilter`` instances into a single pass/reject decision
per instrument.

Design notes:
- Filters run in insertion order; the first rejection short-circuits the rest.
- ``run()`` accepts a list of ``InstrumentSnapshot`` objects and returns a
  ``PipelineResult`` summarising which instruments passed and which were
  rejected (with per-filter reasons).
- ``build_pipeline_from_config`` mirrors the ``build_manager_from_config``
  pattern established in the protections framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.core.scanner.filters.age import AgeFilter
from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter
from app.core.scanner.filters.precision import PrecisionFilter
from app.core.scanner.filters.price import PriceFilter
from app.core.scanner.filters.range_stability import RangeStabilityFilter
from app.core.scanner.filters.volume import VolumeFilter


_FILTER_TYPES: dict[str, type[PairFilter]] = {
    "volume": VolumeFilter,
    "volume_filter": VolumeFilter,
    "price": PriceFilter,
    "price_filter": PriceFilter,
    "range_stability": RangeStabilityFilter,
    "range_stability_filter": RangeStabilityFilter,
    "age": AgeFilter,
    "age_filter": AgeFilter,
    "precision": PrecisionFilter,
    "precision_filter": PrecisionFilter,
}

_FLAT_KEYS: list[tuple[str, type[PairFilter]]] = [
    ("volume", VolumeFilter),
    ("price", PriceFilter),
    ("range_stability", RangeStabilityFilter),
    ("age", AgeFilter),
    ("precision", PrecisionFilter),
]


@dataclass
class SymbolFilterSummary:
    """Per-symbol result across all filters."""

    symbol: str
    passed: bool
    results: list[FilterResult] = field(default_factory=list)
    rejection_reason: str = ""

    @property
    def rejecting_filter(self) -> str | None:
        for r in self.results:
            if not r.passed:
                return r.filter_name
        return None


@dataclass
class PipelineResult:
    """Aggregate result of one pipeline run."""

    passed: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    details: dict[str, SymbolFilterSummary] = field(default_factory=dict)

    @property
    def n_passed(self) -> int:
        return len(self.passed)

    @property
    def n_rejected(self) -> int:
        return len(self.rejected)

    def rejection_breakdown(self) -> dict[str, int]:
        """Count rejections per filter name."""
        counts: dict[str, int] = {}
        for summary in self.details.values():
            if not summary.passed and summary.rejecting_filter:
                counts[summary.rejecting_filter] = counts.get(summary.rejecting_filter, 0) + 1
        return counts


class FilterPipeline:
    """Chains multiple ``PairFilter`` instances into a single pass.

    Usage::

        pipeline = FilterPipeline([VolumeFilter(), PriceFilter(min_price=50)])
        result = pipeline.run(snapshots)
        tradable = result.passed
    """

    def __init__(self, filters: Sequence[PairFilter]) -> None:
        self._filters: list[PairFilter] = list(filters)

    def add(self, f: PairFilter) -> None:
        self._filters.append(f)

    def run(self, snapshots: Sequence[InstrumentSnapshot]) -> PipelineResult:
        result = PipelineResult()
        for snap in snapshots:
            summary = self._evaluate(snap)
            result.details[snap.symbol] = summary
            if summary.passed:
                result.passed.append(snap.symbol)
            else:
                result.rejected.append(snap.symbol)
        return result

    def _evaluate(self, snap: InstrumentSnapshot) -> SymbolFilterSummary:
        summary = SymbolFilterSummary(symbol=snap.symbol, passed=True)
        for f in self._filters:
            fr = f.apply(snap)
            summary.results.append(fr)
            if not fr.passed:
                summary.passed = False
                summary.rejection_reason = fr.reason
                break  # short-circuit on first rejection
        return summary


def build_pipeline_from_config(
    config: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
) -> FilterPipeline:
    """Build a ``FilterPipeline`` from a config dict or list.

    **Flat dict** (preferred)::

        {
            "volume": {"min_turnover_inr": 10_00_00_000},
            "price":  {"min_price": 50, "max_price": 50_000},
            "range_stability": False,   # disabled
            "age":    {},               # defaults
            "precision": False,
        }

    **List of dicts** (legacy)::

        [
            {"name": "volume_filter", "min_turnover_inr": 10_00_00_000},
            {"name": "price_filter",  "min_price": 50},
        ]

    Passing ``None`` or ``{}`` enables all five filters at default settings.
    """
    if config is None:
        config = {}

    if isinstance(config, Mapping):
        if any(isinstance(v, Mapping) or v is False for v in config.values()):
            return _build_from_flat(config)
        if "filters" in config and isinstance(config["filters"], list):
            return _build_from_list(config["filters"])
        return _build_from_flat(config)

    return _build_from_list(config)


def _build_from_flat(cfg: Mapping[str, Any]) -> FilterPipeline:
    filters: list[PairFilter] = []
    for key, cls in _FLAT_KEYS:
        value = cfg.get(key)
        if value is False:
            continue
        kwargs: dict[str, Any] = value if isinstance(value, dict) else {}
        filters.append(cls(**kwargs))
    return FilterPipeline(filters)


def _build_from_list(entries: list[Mapping[str, Any]]) -> FilterPipeline:
    filters: list[PairFilter] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or entry.get("type") or "").strip().lower()
        cls = _FILTER_TYPES.get(name)
        if cls is None:
            raise ValueError(f"Unknown filter type: {name!r}")
        kwargs = {k: v for k, v in entry.items() if k not in {"name", "type"} and v is not None}
        filters.append(cls(**kwargs))
    return FilterPipeline(filters)
