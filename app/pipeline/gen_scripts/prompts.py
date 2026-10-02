"""
app/pipeline/gen_scripts/prompts.py
------------------------------------
Prompt templates for the gen_scripts step.

Design principles:
  1. SYSTEM prompt defines the role, constraints, and output contract.
  2. USER prompt injects the learner query + the live effects catalog.
  3. A few-shot example is embedded in the system prompt to anchor format.
  4. The JSON schema is inlined so the model knows exactly what to produce.

Using Gemini (gemini-2.5-flash):
  - Temperature: 0.3  → deterministic enough, still creative
  - response_mime_type: application/json  → Gemini native JSON mode
"""

from __future__ import annotations
from app.pipeline.manim_framework.effects_catalog import catalog_for_prompt


# ── JSON schema injected into prompt ──────────────────────────────────────────
_SCHEMA = """
{
  "title": "string — short descriptive video title",
  "topic": "string — the original learner prompt verbatim",
  "total_duration_s": "number — sum of all scene durations, must be ≤ 180",
  "scenes": [
    {
      "scene_id": "integer — sequential, starting at 1",
      "duration_s": "number — this scene's duration in seconds (1–30)",
      "effect": "string — keyword from the Effects Catalog",
      "effect_params": "object — parameters required by that effect",
      "transition": "one of: fade | wipe_left | none",
      "narration": "string — voiceover text for this scene",
      "voice_config": {
        "speaking_rate": "number 0.25–4.0 (default 1.0)",
        "pitch": "number -20 to 20 semitones (default 0.0)",
        "volume_gain_db": "number (default 0.0)",
        "voice_name": "string — TTS voice (default en-US-Journey-F)",
        "language_code": "string (default en-US)"
      },
      "audio_effect": {
        "type": "one of: none | soft_music | whoosh | chime | pop",
        "volume_db": "number -40 to 0 (default -18)"
      }
    }
  ]
}
"""

# ── Few-shot example (partial) ─────────────────────────────────────────────────
_FEW_SHOT_EXAMPLE = """
EXAMPLE INPUT: "How does the pH scale work?"

EXAMPLE OUTPUT (abbreviated — real output must have all scenes):
{
  "title": "The pH Scale Explained",
  "topic": "How does the pH scale work?",
  "total_duration_s": 120,
  "scenes": [
    {
      "scene_id": 1,
      "duration_s": 5,
      "effect": "TITLE_CARD",
      "effect_params": {
        "title": "The pH Scale",
        "subtitle": "Acids, Bases & Everything Between",
        "color": "#58C4DD"
      },
      "transition": "none",
      "narration": "Have you ever wondered what makes something acidic or basic?",
      "voice_config": { "speaking_rate": 0.95, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "chime", "volume_db": -20 }
    },
    {
      "scene_id": 2,
      "duration_s": 12,
      "effect": "FORMULA_DISPLAY",
      "effect_params": {
        "formulas": [
          "\\\\text{pH} = -\\\\log_{10}[H^+]",
          "[H^+] = 10^{-7} \\\\text{ mol/L}"
        ],
        "color": "#58C4DD",
        "scale": 1.2
      },
      "transition": "fade",
      "narration": "pH equals the negative log of hydrogen ion concentration. Pure water has a concentration of ten to the negative seven.",
      "voice_config": { "speaking_rate": 0.85, "pitch": -1.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "none", "volume_db": -18 }
    },
    {
      "scene_id": 3,
      "duration_s": 10,
      "effect": "FORMULA_TRANSFORM",
      "effect_params": {
        "from_formula": "\\\\text{pH} = -\\\\log_{10}(10^{-7})",
        "to_formula": "\\\\text{pH} = 7",
        "label": "neutral water"
      },
      "transition": "fade",
      "narration": "Plugging in for pure water, we get pH equals 7, which is neutral.",
      "voice_config": { "speaking_rate": 0.9, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "whoosh", "volume_db": -20 }
    },
    {
      "scene_id": 4,
      "duration_s": 18,
      "effect": "PH_SCALE",
      "effect_params": {
        "highlight_ph": 7,
        "show_examples": true
      },
      "transition": "wipe_left",
      "narration": "The scale runs from zero to fourteen. Below seven is acidic, above seven is basic. Lemon juice sits at about two, while bleach is around thirteen.",
      "voice_config": { "speaking_rate": 1.0, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "soft_music", "volume_db": -22 }
    },
    {
      "scene_id": 5,
      "duration_s": 12,
      "effect": "MOLECULE_LABEL",
      "effect_params": {
        "name": "Hydrochloric Acid",
        "formula": "HCl",
        "color": "#FF6666"
      },
      "transition": "fade",
      "narration": "Hydrochloric acid, or HCl, fully dissociates in water, making it a strong acid with a very low pH.",
      "voice_config": { "speaking_rate": 0.95, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "pop", "volume_db": -18 }
    },
    {
      "scene_id": 6,
      "duration_s": 15,
      "effect": "EQUATION_STEP",
      "effect_params": {
        "steps": [
          "HCl \\\\rightarrow H^+ + Cl^-",
          "[H^+] = 1 \\\\text{ mol/L}",
          "\\\\text{pH} = -\\\\log_{10}(1) = 0"
        ]
      },
      "transition": "fade",
      "narration": "HCl splits into hydrogen and chloride ions. With a concentration of one molar, the pH is zero — extremely acidic.",
      "voice_config": { "speaking_rate": 0.85, "pitch": -1.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "none", "volume_db": -18 }
    },
    {
      "scene_id": 7,
      "duration_s": 10,
      "effect": "CONCLUSION_CARD",
      "effect_params": {
        "title": "Key Takeaways",
        "bullets": [
          "pH = −log₁₀[H⁺]",
          "Scale: 0 (acid) → 7 (neutral) → 14 (base)",
          "Each unit = 10× change in [H⁺]"
        ]
      },
      "transition": "fade",
      "narration": "Remember: pH measures hydrogen ion concentration. Each step is a tenfold change.",
      "voice_config": { "speaking_rate": 0.9, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "chime", "volume_db": -20 }
    }
  ]
}
"""


# ── Prompt builders ────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    """
    Static system prompt — built once, reused for all gen_scripts calls.
    Inlines the effects catalog and JSON schema.
    """
    catalog = catalog_for_prompt()
    return f"""You are an expert chemistry educator and video scriptwriter.
Your job is to write a structured script for a short educational chemistry video.

═══════════════════════════════════════
HARD CONSTRAINTS — NEVER VIOLATE THESE
═══════════════════════════════════════
1. Total video duration MUST be ≤ 180 seconds. Aim for 90–150 seconds.
2. Number of scenes: between 5 and 12.
3. Scene 1 MUST use effect "TITLE_CARD".
4. The LAST scene MUST use effect "CONCLUSION_CARD" with 2–4 bullet takeaways.
5. Every effect keyword MUST come from the Effects Catalog below. Do NOT invent new keywords.
6. Each scene's "effect_params" MUST include all required params listed for that effect.
7. scene_id values MUST be sequential integers starting at 1.
8. total_duration_s MUST equal the sum of all scene duration_s values (±1 second tolerance).
9. Narration text must be natural spoken English — no bullet points, no LaTeX in narration.
10. LaTeX formulas go in effect_params only (e.g., FORMULA_DISPLAY, EQUATION_STEP).
11. Output ONLY valid JSON. No markdown fences, no explanation text outside the JSON.

═══════════════════════════════════════
VISUAL-FIRST DESIGN — CRITICAL RULES
═══════════════════════════════════════
The audience watches on a phone (TikTok/YouTube Shorts). Text-heavy screens are BORING.
Follow these rules to maximize visual engagement:

A. MINIMIZE TEXT on screen. NEVER use TEXT_REVEAL unless absolutely necessary (e.g., a
   definition that cannot be shown any other way). Prefer FORMULA_DISPLAY, EQUATION_STEP,
   FORMULA_TRANSFORM, ATOM_DIAGRAM, BOND_FORMATION, or MOLECULE_LABEL instead.

B. MAXIMIZE CHEMICAL FORMULAS & ANIMATIONS. At least 60% of scenes (excluding TITLE_CARD
   and CONCLUSION_CARD) must use one of these visual effects:
   FORMULA_DISPLAY, FORMULA_TRANSFORM, EQUATION_STEP, ATOM_DIAGRAM, BOND_FORMATION,
   MOLECULE_LABEL, ELECTRON_TRANSFER, PH_SCALE, NUMBER_LINE.

C. SHOW, DON'T TELL. If the narration mentions a formula or molecule, there MUST be a
   corresponding visual effect showing it. Never just talk about "H₂O" without displaying it.

D. Use FORMULA_TRANSFORM for reactions and equilibria — it creates smooth morphing animations.

E. Use ATOM_DIAGRAM + BOND_FORMATION together to explain bonding concepts step-by-step.

F. Use MOLECULE_LABEL to introduce each important molecule/compound with its name and formula.

G. Use EQUATION_STEP for derivations and multi-line mathematical reasoning.

H. Use HIGHLIGHT_BOX sparingly — only for one key definition or rule per video (max 1 scene).

I. Keep narration concise (15–25 words per scene). Let the visuals do the explaining.

═══════════════════════════
VOICE & AUDIO GUIDELINES
═══════════════════════════
- Default voice: en-US-Journey-F (warm female narrator)
- speaking_rate: 0.85 for complex equations, 1.0 for general narration, 0.9 for conclusion
- pitch: use -1.0 to -2.0 for deeper/serious moments, 0.0 for default
- audio_effect: use "chime" for title/conclusion, "soft_music" for scale animations, "none" for equations
- Keep narration tight — the TTS must finish speaking within the scene's duration_s

═══════════════════
EFFECTS CATALOG
═══════════════════
{catalog}

═══════════════
OUTPUT SCHEMA
═══════════════
{_SCHEMA}

══════════════
FEW-SHOT EXAMPLE
══════════════
{_FEW_SHOT_EXAMPLE}
"""


def build_user_prompt(learner_prompt: str) -> str:
    """
    Dynamic user prompt — includes the learner's specific question.
    """
    return f"""Write a complete structured video script for the following learner query:

"{learner_prompt}"

Requirements:
- Cover the topic thoroughly but concisely (90–150 seconds total).
- Use TITLE_CARD as scene 1 and CONCLUSION_CARD as the last scene.
- VISUAL-FIRST: Maximize the use of FORMULA_DISPLAY, FORMULA_TRANSFORM, EQUATION_STEP,
  ATOM_DIAGRAM, BOND_FORMATION, MOLECULE_LABEL, and ELECTRON_TRANSFER.
- AVOID TEXT_REVEAL — only use it if no other effect can convey the information.
- Show every formula/molecule mentioned in narration as a visual effect on screen.
- Include at least one concrete chemical example (e.g., HCl, NaCl, H₂O) with its formula.
- For formulas, use standard LaTeX notation inside effect_params.
- Keep narration SHORT (15–25 words per scene). Let animations speak.
- Narration must sync with the scene duration — average speaking rate: ~2.5 words/second at rate 1.0.
- Make the explanation accessible to a high-school student.
- Output ONLY the JSON object. No other text.
"""
