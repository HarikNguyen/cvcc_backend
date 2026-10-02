"""
app/pipeline/gen_speech/__init__.py
------------------------------------
--------------------------------------
gen_speech: Generate voiceovers for each scene using edge-tts.

Reliability mechanisms:
  1. Minimum file size guard (< 1KB means TTS failed silently)
  2. Minimum duration guard (< 0.5s means TTS failed silently)
  3. Per-scene retry (max RETRY_PER_SCENE attempts)
  4. If a single scene consistently fails, the job fails fast with a
     clear error naming which scene and why.

Output layout (per job):
  tmp_manim_scenes/{job_id}/audio/
    scene_01.mp3
    ...
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3

from app.pipeline.script_schema import Scene, VideoScript

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
RETRY_PER_SCENE = 3
MIN_FILE_SIZE_BYTES = 1_024       # < 1 KB → treat as empty
MIN_DURATION_S = 0.5              # < 0.5s → treat as silent


# ── Result objects ─────────────────────────────────────────────────────────────

@dataclass
class SceneAudio:
    """Audio artifact for one scene."""
    scene_id: int
    audio_path: str          # absolute path to .mp3
    actual_duration_s: float # measured from the file


@dataclass
class SpeechResult:
    """Aggregate result for all scenes in a script."""
    scenes: list[SceneAudio]

    def get(self, scene_id: int) -> SceneAudio | None:
        return next((s for s in self.scenes if s.scene_id == scene_id), None)

    @property
    def total_audio_duration_s(self) -> float:
        return sum(s.actual_duration_s for s in self.scenes)


# ── Errors ─────────────────────────────────────────────────────────────────────

class SpeechGenerationError(Exception):
    """Raised when a scene's audio cannot be generated after all retries."""
    pass


# ── Core helpers ───────────────────────────────────────────────────────────────

def _measure_duration(mp3_path: str) -> float:
    """Return the duration of an mp3 file in seconds using mutagen."""
    audio = MP3(mp3_path)
    return audio.info.length


def _synthesize_scene(
    scene: Scene,
    out_path: str,
) -> float:
    """
    Call edge-tts for one scene, write mp3 to out_path.
    Returns measured duration in seconds.
    Raises ValueError if output is empty or too short.
    """
    # Use a default voice if the requested one isn't an edge-tts voice
    voice = scene.voice_config.voice_name
    if not voice.endswith("Neural"):
        voice = "en-US-AriaNeural"

    # Rate format for edge-tts (e.g., +10%, -20%)
    rate_str = f"{int((scene.voice_config.speaking_rate - 1.0) * 100):+d}%"
    
    # GCP pitch is in semitones (0.0 is default)
    # We map 1 semitone to ~5Hz roughly, just to have some effect
    pitch_str = f"{int(scene.voice_config.pitch * 5):+d}Hz"
    
    cmd = [
        "edge-tts",
        "--voice", voice,
        f"--rate={rate_str}",
        f"--pitch={pitch_str}",
        "--text", scene.narration,
        "--write-media", out_path,
    ]
    
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"edge-tts failed: {result.stderr}")

    if not os.path.exists(out_path):
        raise ValueError(f"Scene {scene.scene_id}: edge-tts output file not created.")

    # ── Size guard ─────────────────────────────────────────────────────────
    file_size = os.path.getsize(out_path)
    if file_size < MIN_FILE_SIZE_BYTES:
        raise ValueError(
            f"Scene {scene.scene_id}: TTS returned {file_size} bytes "
            f"(minimum {MIN_FILE_SIZE_BYTES}). Likely empty response."
        )

    # ── Duration guard ────────────────────────────────────────────────     
    duration = _measure_duration(out_path)
    if duration < MIN_DURATION_S:
        os.unlink(out_path)
        raise ValueError(
            f"Scene {scene.scene_id}: audio duration {duration:.2f}s is below "
            f"minimum {MIN_DURATION_S}s. Treating as silent."
        )

    return duration


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_speech(
    script: VideoScript,
    job_id: str,
    tmp_dir: str | None = None,
    progress_cb=None,
) -> SpeechResult:
    """
    Generate MP3 audio for every scene in the script.

    Parameters
    ----------
    script:      The validated VideoScript from gen_scripts.
    job_id:      Used to namespace the output directory.
    tmp_dir:     Base temp directory (defaults to TMP_DIR env var or 'tmp_manim_scenes').
    progress_cb: Optional callable(str) for status updates.

    Returns
    -------
    SpeechResult with one SceneAudio per scene.

    Raises
    ------
    SpeechGenerationError: if any scene fails after all retries.
    """
    base = tmp_dir or os.getenv("TMP_DIR", "tmp_manim_scenes")
    audio_dir = os.path.join(base, job_id, "audio")
    Path(audio_dir).mkdir(parents=True, exist_ok=True)

    results: list[SceneAudio] = []

    for scene in script.scenes:
        mp3_path = os.path.join(audio_dir, f"scene_{scene.scene_id:02d}.mp3")
        last_error: str | None = None

        for attempt in range(1, RETRY_PER_SCENE + 1):
            if progress_cb:
                progress_cb(
                    f"Generating audio: scene {scene.scene_id}/{len(script.scenes)} "
                    f"(attempt {attempt})..."
                )

            logger.info(
                "gen_speech scene %d attempt %d/%d",
                scene.scene_id, attempt, RETRY_PER_SCENE,
            )

            try:
                duration = _synthesize_scene(scene, mp3_path)
                logger.info(
                    "gen_speech scene %d OK: %.2fs (script target %.2fs)",
                    scene.scene_id, duration, scene.duration_s,
                )
                results.append(SceneAudio(
                    scene_id=scene.scene_id,
                    audio_path=mp3_path,
                    actual_duration_s=duration,
                ))
                break  # success — move to next scene

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "gen_speech scene %d attempt %d failed: %s",
                    scene.scene_id, attempt, e,
                )
                # Clean up any partial file before retry
                if os.path.exists(mp3_path):
                    os.unlink(mp3_path)

        else:
            # All retries exhausted for this scene
            raise SpeechGenerationError(
                f"Audio generation failed for scene {scene.scene_id} "
                f"after {RETRY_PER_SCENE} attempts. Last error: {last_error}"
            )

    logger.info(
        "gen_speech complete: %d scenes, total audio %.2fs",
        len(results),
        sum(r.actual_duration_s for r in results),
    )

    return SpeechResult(scenes=results)
