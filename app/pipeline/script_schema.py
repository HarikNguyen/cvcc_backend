"""
app/pipeline/script_schema.py
------------------------------
Pydantic schema for the structured script JSON produced by gen_scripts.

This schema is the contract between:
  - The LLM (Groq) that generates the script
  - The TTS service (Google Cloud TTS) that reads narration
  - The Manim framework that renders visuals

Having a strict schema means LLM output is validated before any
downstream processing begins — bad output fails fast and cleanly.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ── Voice / TTS config ─────────────────────────────────────────────────────────

class VoiceConfig(BaseModel):
    """
    Google Cloud TTS voice parameters per scene.
    Ref: https://cloud.google.com/text-to-speech/docs/reference/rest/v1/AudioConfig
    """
    speaking_rate: float = Field(
        default=1.0,
        ge=0.25, le=4.0,
        description="Speech speed. 1.0 = normal. 0.8 = slower for complex content.",
    )
    pitch: float = Field(
        default=0.0,
        ge=-20.0, le=20.0,
        description="Pitch shift in semitones. 0 = default. Negative = deeper.",
    )
    volume_gain_db: float = Field(
        default=0.0,
        ge=-96.0, le=16.0,
        description="Volume gain in dB. 0 = default.",
    )
    voice_name: str = Field(
        default="en-US-Journey-F",
        description=(
            "Google Cloud TTS voice name. "
            "Preferred: en-US-Journey-F (female, warm) or en-US-Journey-D (male)."
        ),
    )
    language_code: str = Field(default="en-US")


class AudioEffect(BaseModel):
    """Optional background sound layered under the narration."""
    type: Literal["none", "soft_music", "whoosh", "chime", "pop"] = "none"
    volume_db: float = Field(default=-18.0, ge=-40.0, le=0.0)


# ── Scene ──────────────────────────────────────────────────────────────────────

class Scene(BaseModel):
    """One visual + audio unit in the video."""

    scene_id: int = Field(..., ge=1, description="Sequential scene number, starting at 1.")
    duration_s: float = Field(
        ...,
        gt=0, le=30,
        description="Estimated scene duration in seconds.",
    )

    # ── Visual ──────────────────────────────────────────────────────────────
    effect: str = Field(
        ...,
        description="Keyword from the Manim effects catalog.",
    )
    effect_params: dict = Field(
        default_factory=dict,
        description="Parameters for the chosen effect. Must match the effect's required_params.",
    )
    transition: Literal["fade", "wipe_left", "none"] = Field(
        default="fade",
        description="Transition INTO this scene from the previous one.",
    )

    # ── Audio ────────────────────────────────────────────────────────────────
    narration: str = Field(
        ...,
        min_length=1,
        description="Voiceover text for this scene. Spoken by TTS.",
    )
    voice_config: VoiceConfig = Field(default_factory=VoiceConfig)
    audio_effect: AudioEffect = Field(default_factory=AudioEffect)


# ── Top-level Script ───────────────────────────────────────────────────────────

class VideoScript(BaseModel):
    """
    Full structured script for one chemistry concept video.
    Max total duration: 180 seconds.
    """

    title: str = Field(..., description="Short descriptive title for the video.")
    topic: str = Field(..., description="The original learner prompt.")
    total_duration_s: float = Field(
        ...,
        gt=0, le=180,
        description="Sum of all scene durations. Must be ≤ 180.",
    )
    scenes: list[Scene] = Field(..., min_length=3, max_length=12)

    @model_validator(mode="after")
    def validate_total_duration(self) -> "VideoScript":
        computed = sum(s.duration_s for s in self.scenes)
        if abs(computed - self.total_duration_s) > 2.0:
            raise ValueError(
                f"total_duration_s ({self.total_duration_s}s) does not match "
                f"sum of scene durations ({computed:.1f}s). "
                "Update total_duration_s to match."
            )
        if computed > 180:
            raise ValueError(
                f"Total duration {computed:.1f}s exceeds the 180s maximum."
            )
        return self

    @model_validator(mode="after")
    def validate_scene_ids(self) -> "VideoScript":
        ids = [s.scene_id for s in self.scenes]
        expected = list(range(1, len(self.scenes) + 1))
        if ids != expected:
            raise ValueError(
                f"scene_id must be sequential starting at 1. Got: {ids}"
            )
        return self

    @model_validator(mode="after")
    def validate_first_and_last_scene(self) -> "VideoScript":
        if self.scenes[0].effect != "TITLE_CARD":
            raise ValueError("First scene must use TITLE_CARD effect.")
        if self.scenes[-1].effect != "CONCLUSION_CARD":
            raise ValueError("Last scene must use CONCLUSION_CARD effect.")
        return self
