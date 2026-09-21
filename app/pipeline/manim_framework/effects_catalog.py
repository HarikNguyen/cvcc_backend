"""
app/pipeline/manim_framework/effects_catalog.py
------------------------------------------------
Single source of truth for all available Manim effects.

Design rationale:
  The LLM does NOT generate arbitrary Manim code.
  Instead, it selects keywords from this catalog and provides parameters.
  The framework then renders the effect deterministically.

  This is the core reliability mechanism:
    - No hallucinated Manim API calls.
    - Every effect is pre-tested and guaranteed to render.
    - Adding a new effect = add one entry here + implement its renderer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EffectSpec:
    """Metadata for one registered effect."""
    keyword: str
    description: str
    required_params: list[str]
    optional_params: dict[str, Any] = field(default_factory=dict)
    max_duration_s: float = 30.0


# ── Effect Registry ────────────────────────────────────────────────────────────
# keyword → EffectSpec
EFFECTS: dict[str, EffectSpec] = {

    # ── Meta / structural ──────────────────────────────────────────────────
    "TITLE_CARD": EffectSpec(
        keyword="TITLE_CARD",
        description="Animated title + subtitle intro card. Use as the first scene.",
        required_params=["title"],
        optional_params={"subtitle": "", "color": "#58C4DD"},
        max_duration_s=8,
    ),
    "CONCLUSION_CARD": EffectSpec(
        keyword="CONCLUSION_CARD",
        description="Summary card with 2-4 bullet key-takeaways. Use as the last scene.",
        required_params=["bullets"],   # list[str]
        optional_params={"title": "Key Takeaways"},
        max_duration_s=15,
    ),
    "SECTION_TITLE": EffectSpec(
        keyword="SECTION_TITLE",
        description="Brief section divider title between scenes.",
        required_params=["text"],
        optional_params={"color": "#FFFFFF"},
        max_duration_s=4,
    ),

    # ── Text / explanation ─────────────────────────────────────────────────
    "TEXT_REVEAL": EffectSpec(
        keyword="TEXT_REVEAL",
        description="Animated text lines appearing one by one from top to bottom.",
        required_params=["lines"],     # list[str], max 4 lines
        optional_params={"font_size": 36},
        max_duration_s=20,
    ),
    "HIGHLIGHT_BOX": EffectSpec(
        keyword="HIGHLIGHT_BOX",
        description="Key concept text inside a highlighted box with an optional icon label.",
        required_params=["text"],
        optional_params={"label": "", "color": "#FFD700"},
        max_duration_s=10,
    ),

    # ── Formula / chemistry ────────────────────────────────────────────────
    "FORMULA_DISPLAY": EffectSpec(
        keyword="FORMULA_DISPLAY",
        description=(
            "Render one or more LaTeX chemical/math formulas, "
            "written in from left to right. "
            "Use standard LaTeX chemistry notation."
        ),
        required_params=["formulas"],  # list[str] LaTeX strings
        optional_params={"color": "#58C4DD", "scale": 1.0},
        max_duration_s=15,
    ),
    "FORMULA_TRANSFORM": EffectSpec(
        keyword="FORMULA_TRANSFORM",
        description=(
            "Animate a formula morphing into another formula. "
            "Good for showing reactions or equilibrium changes."
        ),
        required_params=["from_formula", "to_formula"],
        optional_params={"label": ""},
        max_duration_s=12,
    ),
    "EQUATION_STEP": EffectSpec(
        keyword="EQUATION_STEP",
        description=(
            "Show a derivation step by step. Each step appears below the previous. "
            "Use for pH = -log[H+] style derivations."
        ),
        required_params=["steps"],     # list[str] LaTeX strings
        optional_params={"color": "#FFFFFF"},
        max_duration_s=20,
    ),

    # ── Molecular diagrams ────────────────────────────────────────────────
    "ATOM_DIAGRAM": EffectSpec(
        keyword="ATOM_DIAGRAM",
        description=(
            "Draw one or two atoms as circles with element symbols. "
            "Optionally show electron dots around them."
        ),
        required_params=["atoms"],     # list[{"symbol": str, "color": str}]
        optional_params={"show_electrons": True},
        max_duration_s=12,
    ),
    "BOND_FORMATION": EffectSpec(
        keyword="BOND_FORMATION",
        description=(
            "Animate two atoms moving together to form a covalent or ionic bond. "
            "bond_type: 'single' | 'double' | 'ionic'"
        ),
        required_params=["atom_a", "atom_b", "bond_type"],
        optional_params={"label": ""},
        max_duration_s=15,
    ),
    "MOLECULE_LABEL": EffectSpec(
        keyword="MOLECULE_LABEL",
        description=(
            "Show a molecule name + its structural formula side by side. "
            "Use for H2O, HCl, NaCl, etc."
        ),
        required_params=["name", "formula"],
        optional_params={"color": "#58C4DD"},
        max_duration_s=10,
    ),
    "ELECTRON_TRANSFER": EffectSpec(
        keyword="ELECTRON_TRANSFER",
        description=(
            "Animate an electron (dot) moving from one atom to another. "
            "Use for ionic bond formation."
        ),
        required_params=["from_atom", "to_atom"],
        optional_params={"electron_color": "#FFFF00"},
        max_duration_s=12,
    ),

    # ── Scale / comparison ─────────────────────────────────────────────────
    "PH_SCALE": EffectSpec(
        keyword="PH_SCALE",
        description=(
            "Render an animated horizontal pH scale bar (0–14) with color gradient "
            "from red (acid) to green (neutral) to blue (base). "
            "Optionally highlight a specific pH value with a marker."
        ),
        required_params=[],
        optional_params={"highlight_ph": None, "show_examples": True},
        max_duration_s=20,
    ),
    "COMPARISON_TABLE": EffectSpec(
        keyword="COMPARISON_TABLE",
        description=(
            "Side-by-side two-column comparison table. "
            "Use for ionic vs covalent bonding differences."
        ),
        required_params=["left_header", "right_header", "rows"],  # rows: list[list[str, str]]
        optional_params={"title": ""},
        max_duration_s=20,
    ),
    "NUMBER_LINE": EffectSpec(
        keyword="NUMBER_LINE",
        description="Animated number line with labeled points. Good for pH ranges.",
        required_params=["min_val", "max_val", "labels"],  # labels: list[{"value": float, "text": str}]
        optional_params={"color": "#58C4DD"},
        max_duration_s=15,
    ),

    # ── Process / flow ─────────────────────────────────────────────────────
    "ARROW_DIAGRAM": EffectSpec(
        keyword="ARROW_DIAGRAM",
        description=(
            "Show a left-to-right flow of 2–4 labeled boxes connected by arrows. "
            "Good for reaction steps or processes."
        ),
        required_params=["steps"],     # list[str]
        optional_params={"color": "#58C4DD", "arrow_color": "#FFFFFF"},
        max_duration_s=15,
    ),
    "PROS_CONS": EffectSpec(
        keyword="PROS_CONS",
        description=(
            "Two-column list: left = one concept's properties, "
            "right = another concept's properties. "
            "Items appear one by one."
        ),
        required_params=["left_title", "left_items", "right_title", "right_items"],
        optional_params={},
        max_duration_s=20,
    ),
}


def get_effect(keyword: str) -> EffectSpec | None:
    """Return the EffectSpec for the given keyword, or None if not registered."""
    return EFFECTS.get(keyword)


def list_keywords() -> list[str]:
    """Return all registered effect keywords (for prompt injection)."""
    return list(EFFECTS.keys())


def catalog_for_prompt() -> str:
    """
    Render the catalog as a compact string suitable for injection into an LLM prompt.
    Format: KEYWORD | description | required params
    """
    lines = []
    for kw, spec in EFFECTS.items():
        req = ", ".join(spec.required_params) if spec.required_params else "—"
        lines.append(
            f"- {kw} (max {int(spec.max_duration_s)}s)\n"
            f"  {spec.description}\n"
            f"  Required params: {req}"
        )
    return "\n".join(lines)
