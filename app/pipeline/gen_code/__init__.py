"""
app/pipeline/gen_code/__init__.py
----------------------------------
gen_code: Translate VideoScript + SpeechResult → Manim Python file → MP4.

Pipeline:
  1. CodeGenerator.generate()   → writes scene.py from VideoScript data
  2. ManimRenderer.render()     → runs `manim` subprocess → raw_video.mp4
     - If crash: retry up to MAX_RETRIES with a simplified fallback scene
  3. AudioMixer.mix()           → ffmpeg concatenates audio + mixes with video
  4. Returns path to final .mp4

Design decisions:
  - Code generation is PROGRAMMATIC (no LLM) for 100% determinism.
    The LLM already did the hard work in gen_scripts.
  - The generated scene.py only calls self.play_effect(...) with the
    exact params from the VideoScript. No raw Manim primitives.
  - Retry strategy: on render crash the fallback produces a minimal
    text-only version so the job never silently returns an empty file.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

from app.pipeline.gen_speech import SpeechResult
from app.pipeline.script_schema import VideoScript

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_RENDER_RETRIES = int(os.getenv("GEN_CODE_MAX_RETRIES", "3"))
RENDER_TIMEOUT_S   = int(os.getenv("MANIM_RENDER_TIMEOUT_S", "300"))
VIDEO_QUALITY      = os.getenv("MANIM_QUALITY", "l")   # l=low(fast), m=medium, h=high

# Absolute path to project root (needed for subprocess sys.path injection)
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])


class CodeGenerationError(Exception):
    """Raised when render fails after all retries."""


# ── Stage 1: Programmatic code generator ─────────────────────────────────────

class CodeGenerator:
    """
    Translates a VideoScript into a runnable Manim Python file.
    Produces deterministic output — same script always produces same code.
    """

    @staticmethod
    def generate(
        script: VideoScript,
        speech: SpeechResult,
        out_path: str,
    ) -> str:
        """
        Write the generated scene.py to `out_path`.
        Returns the path.
        """
        lines: list[str] = []

        # ── Header ─────────────────────────────────────────────────────────
        lines += [
            "# AUTO-GENERATED — do not edit manually.",
            f"# Topic: {script.topic}",
            "",
            "import sys",
            f"sys.path.insert(0, {_PROJECT_ROOT!r})",
            "",
            "from manim import config as manim_config",
            "manim_config.pixel_width  = 1080",
            "manim_config.pixel_height = 1920",
            "manim_config.frame_width  = 9",
            "manim_config.frame_height = 16",
            "",
            "from app.pipeline.manim_framework.base_scene import ChemistryScene",
            "",
            "",
            "class GeneratedVideo(ChemistryScene):",
            "    def construct(self):",
        ]

        # ── Scene calls ────────────────────────────────────────────────────
        for scene in script.scenes:
            # Serialise params as a Python dict literal
            params_repr = json.dumps(scene.effect_params, ensure_ascii=False)

            # Pad duration to actual audio duration if we have it
            audio_info = speech.get(scene.scene_id)
            duration = (
                max(audio_info.actual_duration_s + 0.5, scene.duration_s)
                if audio_info
                else scene.duration_s
            )

            comment = f"# Scene {scene.scene_id}: {scene.effect}"
            call = (
                f"        self.play_effect("
                f"{scene.effect!r}, "
                f"{params_repr}, "
                f"duration={duration:.2f})"
            )
            lines += [f"        {comment}", call, ""]

        code = "\n".join(lines)

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)

        logger.info("gen_code: wrote scene file → %s (%d bytes)", out_path, len(code))
        return out_path

    @staticmethod
    def generate_fallback(script: VideoScript, out_path: str) -> str:
        """
        Generate a minimal text-only fallback scene.
        Used when the main scene crashes after all retries.
        Only uses TEXT_REVEAL (very safe, no LaTeX / complex animations).
        """
        lines = [
            "import sys",
            f"sys.path.insert(0, {_PROJECT_ROOT!r})",
            "from manim import config as manim_config",
            "manim_config.pixel_width  = 1080",
            "manim_config.pixel_height = 1920",
            "manim_config.frame_width  = 9",
            "manim_config.frame_height = 16",
            "from app.pipeline.manim_framework.base_scene import ChemistryScene",
            "",
            "class GeneratedVideo(ChemistryScene):",
            "    def construct(self):",
        ]

        for scene in script.scenes:
            # Strip down to text-only safe params
            if scene.effect == "TITLE_CARD":
                params = {"title": scene.effect_params.get("title", script.title)}
            elif scene.effect == "CONCLUSION_CARD":
                params = {"bullets": scene.effect_params.get("bullets", [script.topic])}
            else:
                # Represent narration as wrapped text lines
                words = scene.narration.split()
                chunks = [" ".join(words[i:i+7]) for i in range(0, len(words), 7)]
                params = {"lines": chunks[:4]}
                scene = scene.model_copy(update={"effect": "TEXT_REVEAL"})

            params_repr = json.dumps(params, ensure_ascii=False)
            effect = "TITLE_CARD" if scene.effect == "TITLE_CARD" else (
                "CONCLUSION_CARD" if scene.effect == "CONCLUSION_CARD" else "TEXT_REVEAL"
            )
            lines += [
                f"        # Scene {scene.scene_id} (fallback)",
                f"        self.play_effect({effect!r}, {params_repr}, duration={scene.duration_s:.1f})",
                "",
            ]

        code = "\n".join(lines)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        logger.warning("gen_code: wrote FALLBACK scene file → %s", out_path)
        return out_path


# ── Stage 2: Manim subprocess renderer ────────────────────────────────────────

class ManimRenderer:
    """Runs the generated scene.py via manim subprocess with timeout + retry."""

    @staticmethod
    def render(
        scene_py_path: str,
        output_dir: str,
        progress_cb=None,
    ) -> str:
        """
        Render GeneratedVideo in scene_py_path → mp4 in output_dir.
        Returns absolute path to the rendered mp4.
        Raises CodeGenerationError after MAX_RENDER_RETRIES failures.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        last_error: str | None = None

        for attempt in range(1, MAX_RENDER_RETRIES + 1):
            if progress_cb:
                progress_cb(f"Rendering video (attempt {attempt}/{MAX_RENDER_RETRIES})...")

            logger.info("manim render attempt %d/%d", attempt, MAX_RENDER_RETRIES)

            cmd = [
                "manim",
                f"-q{VIDEO_QUALITY}",          # quality: l/m/h
                "--media_dir", output_dir,
                "--output_file", "raw_video",
                scene_py_path,
                "GeneratedVideo",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=RENDER_TIMEOUT_S,
                    cwd=_PROJECT_ROOT,
                )

                if result.returncode == 0:
                    mp4 = ManimRenderer._find_output(output_dir)
                    if mp4:
                        logger.info("manim render OK on attempt %d → %s", attempt, mp4)
                        return mp4
                    last_error = "Render returned 0 but no .mp4 found in output dir."
                else:
                    last_error = (
                        f"manim exit code {result.returncode}\n"
                        f"STDERR:\n{result.stderr[-1500:]}"
                    )
                    logger.warning("manim attempt %d failed:\n%s", attempt, last_error[-400:])

            except subprocess.TimeoutExpired:
                last_error = f"Manim render timed out after {RENDER_TIMEOUT_S}s."
                logger.error("manim attempt %d timed out", attempt)

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.error("manim attempt %d unexpected error: %s", attempt, e)

        raise CodeGenerationError(
            f"Manim render failed after {MAX_RENDER_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _find_output(output_dir: str) -> str | None:
        """Walk output_dir recursively and return the first .mp4 found."""
        for root, _, files in os.walk(output_dir):
            for f in files:
                if f.endswith(".mp4"):
                    return os.path.join(root, f)
        return None


# ── Stage 3: Audio mixer ───────────────────────────────────────────────────────

class AudioMixer:
    """Concatenates per-scene audio tracks and mixes with the silent Manim video."""

    @staticmethod
    def mix(
        video_path: str,
        speech: SpeechResult,
        output_path: str,
    ) -> str:
        """
        Concatenate scene audio files → combined.mp3, then mux with video.
        Returns path to the final .mp4 with audio.
        """
        if not speech.scenes:
            logger.warning("No audio scenes — returning video without audio.")
            shutil.copy(video_path, output_path)
            return output_path

        tmp_dir = os.path.dirname(output_path)
        combined_audio = os.path.join(tmp_dir, "combined_audio.mp3")

        # ── Step A: Concatenate audio files ─────────────────────────────
        audio_paths = [s.audio_path for s in sorted(speech.scenes, key=lambda x: x.scene_id)]
        missing = [p for p in audio_paths if not os.path.isfile(p)]
        if missing:
            raise CodeGenerationError(
                f"Audio files missing before mix: {missing}"
            )

        # Build ffmpeg concat input
        inputs = []
        for p in audio_paths:
            inputs += ["-i", p]

        concat_filter = (
            f"{''.join(f'[{i}:0]' for i in range(len(audio_paths)))}"
            f"concat=n={len(audio_paths)}:v=0:a=1[outa]"
        )

        concat_cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", concat_filter,
            "-map", "[outa]",
            combined_audio,
        ]

        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise CodeGenerationError(
                f"FFmpeg audio concat failed:\n{result.stderr[-800:]}"
            )

        # ── Step B: Mux audio into video ────────────────────────────────
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", combined_audio,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",          # trim to shorter of video/audio
            output_path,
        ]

        result = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise CodeGenerationError(
                f"FFmpeg mux failed:\n{result.stderr[-800:]}"
            )

        logger.info("AudioMixer: final video with audio → %s", output_path)
        return output_path


# ── Public entrypoint ──────────────────────────────────────────────────────────

def generate_video(
    script: VideoScript,
    speech: SpeechResult,
    job_id: str,
    artifacts_dir: str | None = None,
    tmp_dir: str | None = None,
    progress_cb=None,
) -> str:
    """
    Full gen_code pipeline: script + speech → final .mp4 with audio.

    Parameters
    ----------
    script:        Validated VideoScript from gen_scripts.
    speech:        SpeechResult from gen_speech.
    job_id:        Used to namespace temp and artifact directories.
    artifacts_dir: Base dir for final .mp4 (default from ARTIFACTS_DIR env).
    tmp_dir:       Base dir for intermediate files (default from TMP_DIR env).
    progress_cb:   Optional callable(str) for status updates.

    Returns
    -------
    Absolute path to the final .mp4 file.

    Raises
    ------
    CodeGenerationError: if rendering fails after all retries.
    """
    base_tmp  = tmp_dir or os.getenv("TMP_DIR", "tmp_manim_scenes")
    base_art  = artifacts_dir or os.getenv("ARTIFACTS_DIR", "artifacts")
    job_tmp   = os.path.join(base_tmp, job_id)
    job_art   = os.path.join(base_art, job_id)

    Path(job_tmp).mkdir(parents=True, exist_ok=True)
    Path(job_art).mkdir(parents=True, exist_ok=True)

    scene_py  = os.path.join(job_tmp, "scene.py")
    render_dir = os.path.join(job_tmp, "render")
    final_mp4 = os.path.join(job_art, "output.mp4")

    # ── Stage 1: Generate code ─────────────────────────────────────────────
    if progress_cb:
        progress_cb("Generating Manim scene code...")
    CodeGenerator.generate(script, speech, scene_py)

    # ── Stage 2: Render with fallback ──────────────────────────────────────
    try:
        if progress_cb:
            progress_cb("Rendering animation...")
        raw_video = ManimRenderer.render(scene_py, render_dir, progress_cb)
    except CodeGenerationError as e:
        logger.warning("Main render failed, trying fallback: %s", e)
        if progress_cb:
            progress_cb("Main render failed — attempting fallback render...")

        fallback_py = os.path.join(job_tmp, "scene_fallback.py")
        CodeGenerator.generate_fallback(script, fallback_py)
        raw_video = ManimRenderer.render(fallback_py, render_dir + "_fallback", progress_cb)

    # ── Stage 3: Mix audio ─────────────────────────────────────────────────
    if progress_cb:
        progress_cb("Mixing audio tracks...")
    final = AudioMixer.mix(raw_video, speech, final_mp4)

    return final
