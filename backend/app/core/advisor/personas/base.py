"""Persona base type + registry.

A ``Persona`` is the minimum needed to overlay an investor's voice on top of
the standard ``PortfolioAdvisor`` prompt: a slug, display name, short style
tag, and the system-prompt body. The body is appended *after* DRUVA's
existing portfolio/regime system prompt so the persona still operates inside
the same SEBI/regime guardrails.

``PersonaSignal`` is the canonical structured output every persona returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Persona:
    slug: str
    """Stable URL/key identifier, e.g. ``"buffett"``."""

    display_name: str
    """Human-readable name, e.g. ``"Warren Buffett"``."""

    style: str
    """One-line investing style tag (used in UI chips)."""

    system_prompt: str
    """Persona-specific instruction text, appended to the base system prompt."""

    checklist: tuple[str, ...] = ()
    """Optional scoring checklist surfaced in the reasoning block."""


class PersonaSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(..., ge=0, le=100)
    reasoning: str
    score: float | None = Field(default=None, description="Optional 0..1 quality score.")
    persona: str = Field(default="", description="Persona slug — filled by the council layer.")


_REGISTRY: dict[str, Persona] = {}


def register_persona(persona: Persona) -> None:
    """Add a persona to the global registry. Idempotent on slug collisions."""
    _REGISTRY[persona.slug] = persona


def resolve_persona(slug: str) -> Persona | None:
    """Look up a persona by slug, case-insensitive."""
    return _REGISTRY.get(slug.lower())


def list_personas() -> list[Persona]:
    """Return all registered personas, alphabetised by slug."""
    return sorted(_REGISTRY.values(), key=lambda p: p.slug)
