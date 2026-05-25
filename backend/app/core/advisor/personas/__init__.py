"""Investor-persona system prompts for the Council mode.

Each persona is a small declarative record (system prompt + investment style
tags). Personas are *prompt overlays* on top of DRUVA's existing
``PortfolioAdvisor`` — no LLM SDK or LangChain duplication.

Adapted from virattt/ai-hedge-fund (MIT). The Indian-market variant
(Rakesh Jhunjhunwala) is original to DRUVA.
"""

from app.core.advisor.personas.base import (
    Persona,
    PersonaSignal,
    list_personas,
    register_persona,
    resolve_persona,
)
from app.core.advisor.personas.buffett import WARREN_BUFFETT
from app.core.advisor.personas.burry import MICHAEL_BURRY
from app.core.advisor.personas.damodaran import ASWATH_DAMODARAN
from app.core.advisor.personas.druckenmiller import STANLEY_DRUCKENMILLER
from app.core.advisor.personas.graham import BENJAMIN_GRAHAM
from app.core.advisor.personas.jhunjhunwala import RAKESH_JHUNJHUNWALA
from app.core.advisor.personas.klarman import SETH_KLARMAN
from app.core.advisor.personas.lynch import PETER_LYNCH
from app.core.advisor.personas.marks import HOWARD_MARKS
from app.core.advisor.personas.munger import CHARLIE_MUNGER
from app.core.advisor.personas.rajan import RAGHURAM_RAJAN

# Ensure module-level personas are registered.
for _p in (
    WARREN_BUFFETT,
    CHARLIE_MUNGER,
    PETER_LYNCH,
    ASWATH_DAMODARAN,
    RAKESH_JHUNJHUNWALA,
    MICHAEL_BURRY,
    STANLEY_DRUCKENMILLER,
    BENJAMIN_GRAHAM,
    SETH_KLARMAN,
    HOWARD_MARKS,
    RAGHURAM_RAJAN,
):
    register_persona(_p)


__all__ = [
    "Persona",
    "PersonaSignal",
    "list_personas",
    "register_persona",
    "resolve_persona",
    "WARREN_BUFFETT",
    "CHARLIE_MUNGER",
    "PETER_LYNCH",
    "ASWATH_DAMODARAN",
    "RAKESH_JHUNJHUNWALA",
    "MICHAEL_BURRY",
    "STANLEY_DRUCKENMILLER",
    "BENJAMIN_GRAHAM",
    "SETH_KLARMAN",
    "HOWARD_MARKS",
    "RAGHURAM_RAJAN",
]
