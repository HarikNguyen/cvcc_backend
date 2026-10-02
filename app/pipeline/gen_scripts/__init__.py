"""
app/pipeline/gen_scripts/__init__.py
--------------------------------------
gen_scripts: call Gemini LLM → parse → validate → return VideoScript.

Reliability mechanisms:
  1. Gemini JSON mode (response_mime_type="application/json").
  2. Pydantic schema validation → catches wrong field types, missing params.
  3. Effect keyword validation → rejects hallucinated effect names.
  4. Retry loop (max MAX_RETRIES): on parse/validation failure, the error
     message is fed back to the model so it can self-correct.
  5. Low temperature (0.3) → deterministic enough across runs.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.pipeline.manim_framework.effects_catalog import EFFECTS
from app.pipeline.script_schema import VideoScript
from app.pipeline.gen_scripts.prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
_TEMPERATURE = 0.3
_MAX_RETRIES = 3

# Built once at module load — the catalog is static.
_SYSTEM_PROMPT = build_system_prompt()


class ScriptGenerationError(Exception):
    """Raised when gen_scripts fails after all retries."""
    pass


def _validate_effect_keywords(script: VideoScript) -> list[str]:
    """
    Check that every scene uses a registered effect keyword.
    Returns a list of error strings (empty = all valid).
    """
    errors = []
    for scene in script.scenes:
        if scene.effect not in EFFECTS:
            errors.append(
                f"Scene {scene.scene_id}: unknown effect '{scene.effect}'. "
                f"Valid keywords: {list(EFFECTS.keys())}"
            )
    return errors


def _validate_required_params(script: VideoScript) -> list[str]:
    """
    Check that each scene's effect_params contains all required params
    defined in the effects catalog.
    Returns a list of error strings.
    """
    errors = []
    for scene in script.scenes:
        spec = EFFECTS.get(scene.effect)
        if spec is None:
            continue  # already caught by keyword validation
        for req in spec.required_params:
            if req not in scene.effect_params:
                errors.append(
                    f"Scene {scene.scene_id} ({scene.effect}): "
                    f"missing required param '{req}'."
                )
    return errors


def generate_script(prompt: str, progress_cb=None) -> VideoScript:
    """
    Generate a structured VideoScript for the given learner prompt.

    Parameters
    ----------
    prompt:      The learner's chemistry question.
    progress_cb: Optional callable(str) called with status updates.

    Returns
    -------
    A validated VideoScript object.

    Raises
    ------
    ScriptGenerationError: if all retries are exhausted.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    user_prompt = build_user_prompt(prompt)

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    ]

    last_error: Optional[str] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        if progress_cb:
            progress_cb(f"Generating script (attempt {attempt}/{_MAX_RETRIES})...")

        logger.info("gen_scripts attempt %d/%d for prompt: %r", attempt, _MAX_RETRIES, prompt[:60])

        # ── If a previous attempt failed, append error feedback ─────────────
        if last_error and attempt > 1:
            contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text="[previous attempt — invalid output]")])
            )
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(
                    text=f"Your previous output was invalid. Fix ALL of these errors and "
                    f"output ONLY the corrected JSON:\n\n{last_error}"
                )])
            )

        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=_TEMPERATURE,
                    response_mime_type="application/json",
                )
            )
            raw = response.text

            # ── Parse JSON ───────────────────────────────────────────────────
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}\nRaw output:\n{raw[:500]}"
                logger.warning("gen_scripts attempt %d: JSON parse error: %s", attempt, e)
                continue

            # ── Validate against Pydantic schema ─────────────────────────────
            try:
                script = VideoScript(**data)
            except ValidationError as e:
                last_error = f"Schema validation errors:\n{e}"
                logger.warning("gen_scripts attempt %d: schema error: %s", attempt, e)
                continue

            # ── Validate effect keywords ──────────────────────────────────────
            kw_errors = _validate_effect_keywords(script)
            param_errors = _validate_required_params(script)
            all_errors = kw_errors + param_errors

            if all_errors:
                last_error = "Effect/param validation errors:\n" + "\n".join(all_errors)
                logger.warning("gen_scripts attempt %d: catalog errors: %s", attempt, all_errors)
                continue

            logger.info(
                "gen_scripts succeeded on attempt %d: %d scenes, %.1fs total",
                attempt, len(script.scenes), script.total_duration_s,
            )
            return script

        except Exception as e:
            last_error = f"API error: {type(e).__name__}: {e}"
            logger.error("gen_scripts attempt %d: API error: %s", attempt, e)

            # Invalid requests, credentials, permissions, and unavailable
            # models cannot succeed by retrying the identical request.
            if isinstance(e, errors.ClientError) and e.code in {400, 401, 403, 404}:
                raise ScriptGenerationError(
                    f"Script generation failed without retrying: {last_error}"
                ) from e
            continue

    raise ScriptGenerationError(
        f"Script generation failed after {_MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
