"""
tests/test_gen_code.py
-----------------------
Unit tests for gen_code: CodeGenerator, ManimRenderer, AudioMixer.

Strategy:
  - CodeGenerator: fully unit-tested (no subprocess).
  - ManimRenderer: subprocess.run is mocked.
  - AudioMixer:    subprocess.run is mocked.
  - generate_video: integration test with all subprocesses mocked.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import subprocess

import pytest

from app.pipeline.gen_code import (
    AudioMixer,
    CodeGenerationError,
    CodeGenerator,
    ManimRenderer,
    generate_video,
)
from app.pipeline.gen_speech import SceneAudio, SpeechResult
from app.pipeline.script_schema import AudioEffect, Scene, VideoScript, VoiceConfig


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_script() -> VideoScript:
    scenes = [
        Scene(
            scene_id=1, duration_s=5.0, effect="TITLE_CARD",
            effect_params={"title": "Test Title", "subtitle": "A subtitle"},
            narration="Welcome.",
        ),
        Scene(
            scene_id=2, duration_s=8.0, effect="FORMULA_DISPLAY",
            effect_params={"formulas": ["H_2O"]},
            narration="This is water.",
        ),
        Scene(
            scene_id=3, duration_s=10.0, effect="CONCLUSION_CARD",
            effect_params={"bullets": ["Point A", "Point B"]},
            narration="In summary.",
        ),
    ]
    return VideoScript.model_construct(
        title="Test Video",
        topic="How does water work?",
        total_duration_s=23.0,
        scenes=scenes,
    )


def _make_speech(script: VideoScript) -> SpeechResult:
    return SpeechResult(scenes=[
        SceneAudio(scene_id=s.scene_id, audio_path=f"/fake/audio/scene_{s.scene_id:02d}.mp3",
                   actual_duration_s=s.duration_s - 0.5)
        for s in script.scenes
    ])


# ── CodeGenerator ──────────────────────────────────────────────────────────────

class TestCodeGenerator:
    def test_generates_python_file(self, tmp_path):
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")

        CodeGenerator.generate(script, speech, out)
        assert os.path.isfile(out)

    def test_generated_file_has_class_definition(self, tmp_path):
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        assert "class GeneratedVideo(ChemistryScene):" in content

    def test_generated_file_has_construct_method(self, tmp_path):
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        assert "def construct(self):" in content

    def test_generated_file_has_all_effect_calls(self, tmp_path):
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        assert "'TITLE_CARD'" in content
        assert "'FORMULA_DISPLAY'" in content
        assert "'CONCLUSION_CARD'" in content

    def test_generated_file_sets_vertical_config(self, tmp_path):
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        assert "pixel_width  = 1080" in content
        assert "pixel_height = 1920" in content

    def test_generated_file_is_valid_python_syntax(self, tmp_path):
        import ast
        script = _make_script()
        speech = _make_speech(script)
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        # Should not raise SyntaxError
        ast.parse(content)

    def test_generate_fallback_uses_only_safe_effects(self, tmp_path):
        script = _make_script()
        out = str(tmp_path / "scene_fallback.py")
        CodeGenerator.generate_fallback(script, out)
        content = Path(out).read_text()
        # Fallback should only use TEXT_REVEAL, TITLE_CARD, CONCLUSION_CARD
        for unsafe in ("FORMULA_DISPLAY", "BOND_FORMATION", "PH_SCALE"):
            assert unsafe not in content, f"Fallback should not use {unsafe}"

    def test_generate_fallback_is_valid_python(self, tmp_path):
        import ast
        script = _make_script()
        out = str(tmp_path / "scene_fallback.py")
        CodeGenerator.generate_fallback(script, out)
        content = Path(out).read_text()
        ast.parse(content)

    def test_duration_uses_actual_audio_duration_when_available(self, tmp_path):
        script = _make_script()
        speech = SpeechResult(scenes=[
            SceneAudio(scene_id=1, audio_path="/fake/s1.mp3", actual_duration_s=7.5),
            SceneAudio(scene_id=2, audio_path="/fake/s2.mp3", actual_duration_s=9.0),
            SceneAudio(scene_id=3, audio_path="/fake/s3.mp3", actual_duration_s=11.0),
        ])
        out = str(tmp_path / "scene.py")
        CodeGenerator.generate(script, speech, out)
        content = Path(out).read_text()
        # Scene 1: actual 7.5 + 0.5 = 8.0 >= script duration 5.0 → uses 8.0
        assert "duration=8.00" in content


# ── ManimRenderer ──────────────────────────────────────────────────────────────

class TestManimRenderer:

    def _make_mp4(self, directory: str) -> str:
        """Create a fake mp4 file in a subdirectory (simulating manim output)."""
        sub = os.path.join(directory, "videos", "GeneratedVideo")
        os.makedirs(sub, exist_ok=True)
        mp4 = os.path.join(sub, "raw_video.mp4")
        Path(mp4).write_bytes(b"fake-mp4")
        return mp4

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_returns_mp4_path_on_success(self, mock_run, tmp_path):
        render_dir = str(tmp_path / "render")
        self._make_mp4(render_dir)
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        result = ManimRenderer.render("/fake/scene.py", render_dir)
        assert result.endswith(".mp4")

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_raises_after_max_retries_on_failure(self, mock_run, tmp_path):
        render_dir = str(tmp_path / "render")
        mock_run.return_value = MagicMock(returncode=1, stderr="SyntaxError", stdout="")

        with pytest.raises(CodeGenerationError, match="failed after"):
            ManimRenderer.render("/fake/scene.py", render_dir)

        assert mock_run.call_count == 3  # MAX_RENDER_RETRIES

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_raises_on_timeout(self, mock_run, tmp_path):
        render_dir = str(tmp_path / "render")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=120)

        with pytest.raises(CodeGenerationError, match="timed out"):
            ManimRenderer.render("/fake/scene.py", render_dir)

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_retries_and_succeeds_on_second_attempt(self, mock_run, tmp_path):
        render_dir = str(tmp_path / "render")
        self._make_mp4(render_dir)

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=1, stderr="LaTeX error", stdout="")
            return MagicMock(returncode=0, stderr="", stdout="")

        mock_run.side_effect = side_effect
        result = ManimRenderer.render("/fake/scene.py", render_dir)
        assert result.endswith(".mp4")
        assert call_count == 2


# ── AudioMixer ─────────────────────────────────────────────────────────────────

class TestAudioMixer:

    def _make_fake_audio_files(self, tmp_path, n=3) -> SpeechResult:
        scenes = []
        for i in range(1, n + 1):
            p = str(tmp_path / f"scene_{i:02d}.mp3")
            Path(p).write_bytes(b"fake-audio")
            scenes.append(SceneAudio(scene_id=i, audio_path=p, actual_duration_s=3.0))
        return SpeechResult(scenes=scenes)

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_calls_ffmpeg_twice(self, mock_run, tmp_path):
        speech = self._make_fake_audio_files(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        output = str(tmp_path / "final.mp4")

        AudioMixer.mix("/fake/video.mp4", speech, output)
        assert mock_run.call_count == 2  # concat + mux

    @patch("app.pipeline.gen_code.subprocess.run")
    def test_raises_on_concat_failure(self, mock_run, tmp_path):
        speech = self._make_fake_audio_files(tmp_path)
        mock_run.return_value = MagicMock(returncode=1, stderr="ffmpeg error", stdout="")
        output = str(tmp_path / "final.mp4")

        with pytest.raises(CodeGenerationError, match="concat failed"):
            AudioMixer.mix("/fake/video.mp4", speech, output)

    @patch("app.pipeline.gen_code.shutil.copy")
    def test_no_audio_copies_video_directly(self, mock_copy, tmp_path):
        empty_speech = SpeechResult(scenes=[])
        output = str(tmp_path / "final.mp4")
        AudioMixer.mix("/fake/video.mp4", empty_speech, output)
        mock_copy.assert_called_once()

    def test_raises_on_missing_audio_files(self, tmp_path):
        speech = SpeechResult(scenes=[
            SceneAudio(scene_id=1, audio_path="/nonexistent/file.mp3", actual_duration_s=3.0)
        ])
        with pytest.raises(CodeGenerationError, match="missing"):
            AudioMixer.mix("/fake/video.mp4", speech, str(tmp_path / "out.mp4"))


# ── generate_video (integration) ──────────────────────────────────────────────

class TestGenerateVideo:

    @patch("app.pipeline.gen_code.AudioMixer.mix")
    @patch("app.pipeline.gen_code.ManimRenderer.render")
    def test_returns_final_mp4_path(self, mock_render, mock_mix, tmp_path):
        final_path = str(tmp_path / "artifacts" / "job-1" / "output.mp4")
        mock_render.return_value = "/fake/raw_video.mp4"
        mock_mix.return_value = final_path

        script = _make_script()
        speech = _make_speech(script)

        result = generate_video(
            script, speech, job_id="job-1",
            artifacts_dir=str(tmp_path / "artifacts"),
            tmp_dir=str(tmp_path / "tmp"),
        )
        assert result == final_path

    @patch("app.pipeline.gen_code.ManimRenderer.render")
    @patch("app.pipeline.gen_code.AudioMixer.mix")
    def test_fallback_render_called_when_main_fails(self, mock_mix, mock_render, tmp_path):
        # First call (main) raises, second (fallback) succeeds
        mock_render.side_effect = [
            CodeGenerationError("render failed"),
            "/fake/fallback_video.mp4",
        ]
        mock_mix.return_value = str(tmp_path / "final.mp4")

        script = _make_script()
        speech = _make_speech(script)

        result = generate_video(
            script, speech, job_id="job-fallback",
            artifacts_dir=str(tmp_path / "artifacts"),
            tmp_dir=str(tmp_path / "tmp"),
        )
        assert mock_render.call_count == 2

    @patch("app.pipeline.gen_code.ManimRenderer.render")
    def test_raises_when_both_main_and_fallback_fail(self, mock_render, tmp_path):
        mock_render.side_effect = CodeGenerationError("always fails")

        script = _make_script()
        speech = _make_speech(script)

        with pytest.raises(CodeGenerationError):
            generate_video(
                script, speech, job_id="job-double-fail",
                artifacts_dir=str(tmp_path / "artifacts"),
                tmp_dir=str(tmp_path / "tmp"),
            )

    @patch("app.pipeline.gen_code.AudioMixer.mix")
    @patch("app.pipeline.gen_code.ManimRenderer.render")
    def test_progress_cb_is_called(self, mock_render, mock_mix, tmp_path):
        mock_render.return_value = "/fake/raw.mp4"
        mock_mix.return_value = "/fake/final.mp4"

        script = _make_script()
        speech = _make_speech(script)
        calls = []

        generate_video(
            script, speech, job_id="job-cb",
            artifacts_dir=str(tmp_path / "artifacts"),
            tmp_dir=str(tmp_path / "tmp"),
            progress_cb=calls.append,
        )
        assert len(calls) >= 2
