"""
app/pipeline/gen_scripts/prompts.py
------------------------------------
Prompt templates for the gen_scripts step.

Design principles:
  1. SYSTEM prompt defines the role, constraints, and output contract.
  2. USER prompt injects the learner query + the live effects catalog.
  3. A few-shot example is embedded in the system prompt to anchor format.
  4. The JSON schema is inlined so the model knows exactly what to produce.

Using Groq (llama-3.1-70b-versatile or mixtral-8x7b):
  - Temperature: 0.3  → deterministic enough, still creative
  - max_tokens: 3000  → enough for a full 12-scene script
  - response_format: json_object  → Groq native JSON mode
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
        "voice_name": "string — Google Cloud TTS voice (default en-US-Journey-F)",
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
  "total_duration_s": 95,
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
      "narration": "Have you ever wondered what it means when something is acidic or basic? It all comes down to the pH scale.",
      "voice_config": {
        "speaking_rate": 0.95,
        "pitch": 0.0,
        "volume_gain_db": 0.0,
        "voice_name": "en-US-Journey-F",
        "language_code": "en-US"
      },
      "audio_effect": { "type": "chime", "volume_db": -20 }
    },
    {
      "scene_id": 2,
      "duration_s": 14,
      "effect": "EQUATION_STEP",
      "effect_params": {
        "steps": [
          "\\\\text{pH} = -\\\\log_{10}[H^+]",
          "[H^+] = 10^{-7} \\\\text{ mol/L (pure water)}",
          "\\\\text{pH} = -\\\\log_{10}(10^{-7}) = 7"
        ]
      },
      "transition": "fade",
      "narration": "pH is defined as the negative logarithm of the hydrogen ion concentration. Pure water has a concentration of 10 to the power of negative 7, giving a neutral pH of 7.",
      "voice_config": { "speaking_rate": 0.85, "pitch": -1.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "none", "volume_db": -18 }
    },
    {
      "scene_id": 3,
      "duration_s": 18,
      "effect": "PH_SCALE",
      "effect_params": {
        "highlight_ph": 7,
        "show_examples": true
      },
      "transition": "wipe_left",
      "narration": "The scale runs from 0 to 14. Values below 7 are acidic — like lemon juice at pH 2. Values above 7 are basic — like baking soda at pH 9. Pure water sits right in the middle at pH 7.",
      "voice_config": { "speaking_rate": 1.0, "pitch": 0.0, "volume_gain_db": 0.0, "voice_name": "en-US-Journey-F", "language_code": "en-US" },
      "audio_effect": { "type": "soft_music", "volume_db": -22 }
    },
    {
      "scene_id": 7,
      "duration_s": 12,
      "effect": "CONCLUSION_CARD",
      "effect_params": {
        "title": "Key Takeaways",
        "bullets": [
          "pH measures hydrogen ion concentration",
          "Scale runs from 0 (most acidic) to 14 (most basic)",
          "pH 7 is neutral (pure water)",
          "Each unit represents a 10× change in acidity"
        ]
      },
      "transition": "fade",
      "narration": "To summarise: pH measures hydrogen ion concentration on a scale from 0 to 14. Each step is a tenfold change in acidity.",
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
- Choose effects from the catalog that best illustrate the chemistry concepts.
- For formulas, use standard LaTeX notation inside effect_params.
- Narration must sync with the scene duration — do not write more text than can be spoken in duration_s seconds (average speaking rate: ~2.5 words/second at rate 1.0).
- Make the explanation accessible to a high-school student.
- Output ONLY the JSON object. No other text.
"""
