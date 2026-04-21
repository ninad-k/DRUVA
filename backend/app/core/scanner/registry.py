"""Auto-discovery registry for scanners.

Scanners declare themselves with ``@register_scanner("scanner.xxx.v1")``.
``import_scanners()`` walks ``app.strategies.scanners`` at startup so the
decorators fire.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TypeVar

from app.core.scanner.base import Scanner

T = TypeVar("T", bound=type[Scanner])

_REGISTRY: dict[str, type[Scanner]] = {}


def register_scanner(name: str):
    def decorator(cls: T) -> T:
        if name in _REGISTRY:
            raise ValueError(f"Scanner '{name}' already registered.")
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_scanner_class(name: str) -> type[Scanner]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"No scanner registered under '{name}'.") from exc


def all_scanners() -> dict[str, type[Scanner]]:
    return dict(_REGISTRY)


def import_scanners() -> None:
    """Walk ``app.strategies.scanners`` to trigger registration."""
    for pkg_name in ("app.strategies.scanners",):
        try:
            pkg = importlib.import_module(pkg_name)
        except ImportError:
            continue
        if not hasattr(pkg, "__path__"):
            continue
        for _, module_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            importlib.import_module(module_name)
