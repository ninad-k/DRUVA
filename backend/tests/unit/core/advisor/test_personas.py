"""Smoke tests for the investor-persona registry."""

from __future__ import annotations

from app.core.advisor.personas import (
    ASWATH_DAMODARAN,
    CHARLIE_MUNGER,
    MICHAEL_BURRY,
    PETER_LYNCH,
    RAKESH_JHUNJHUNWALA,
    STANLEY_DRUCKENMILLER,
    WARREN_BUFFETT,
    list_personas,
    resolve_persona,
)


EXPECTED_SLUGS = {
    "buffett",
    "munger",
    "lynch",
    "damodaran",
    "jhunjhunwala",
    "burry",
    "druckenmiller",
}


def test_all_personas_registered() -> None:
    found = {p.slug for p in list_personas()}
    assert EXPECTED_SLUGS.issubset(found)


def test_resolve_is_case_insensitive() -> None:
    assert resolve_persona("Buffett") is WARREN_BUFFETT
    assert resolve_persona("MUNGER") is CHARLIE_MUNGER
    assert resolve_persona("unknown") is None


def test_each_persona_has_non_empty_prompt_and_style() -> None:
    for persona in (
        WARREN_BUFFETT,
        CHARLIE_MUNGER,
        PETER_LYNCH,
        ASWATH_DAMODARAN,
        RAKESH_JHUNJHUNWALA,
        MICHAEL_BURRY,
        STANLEY_DRUCKENMILLER,
    ):
        assert persona.slug
        assert persona.display_name
        assert persona.style
        assert len(persona.system_prompt) > 200
        assert len(persona.checklist) >= 3
