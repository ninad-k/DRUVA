"""Auto-discovery registry for strategies.

Strategies declare themselves with ``@register_strategy``. At app startup,
``import_strategies()`` imports every module under ``app.strategies.templates``
and ``app.strategies.ml`` so their decorators run and populate the registry.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TypeVar

from app.strategies.base import Strategy

T = TypeVar("T", bound=type[Strategy])

_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(name: str) -> callable:
    """Decorator to register a strategy class under ``name``.

    ``name`` must be globally unique across templates and ML strategies.
    """

    def decorator(cls: T) -> T:
        if name in _REGISTRY:
            raise ValueError(f"Strategy '{name}' is already registered.")
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy_class(name: str) -> type[Strategy]:
    """Look up a registered strategy class by name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"No strategy registered under '{name}'.") from exc


def all_strategies() -> dict[str, type[Strategy]]:
    """Return a copy of the registry."""
    return dict(_REGISTRY)


def import_strategies() -> None:
    """Import every submodule under ``templates`` and ``ml`` to trigger registration."""
    for pkg_name in ("app.strategies.templates", "app.strategies.ml"):
        try:
            pkg = importlib.import_module(pkg_name)
        except ImportError:
            continue
        if not hasattr(pkg, "__path__"):
            continue
        for _, module_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            importlib.import_module(module_name)
