"""
tests/test_gen_speech.py
-------------------------
Unit tests for gen_speech.
Google Cloud TTS client is fully mocked — no real API calls.
MP3 test fixtures are generated with ffmpeg (silent audio).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.gen_speech import (
    MIN_DURATION_S,
    MIN_FILE_SIZE_BYTES,
    SceneAudio,
    SpeechGenerationError,
    SpeechResult,
    _measure_duration,
    generate_speech,
)
from app.pipeline.script_schema import AudioEffect, Scene, VideoScript, VoiceConfig


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_scene(scene_id: int, narration: str = "Test narration.") -> Scene:
    return Scene(
        scene_id=scene_id,
        duration_s=5.0,
        effect="TITLE_CARD" if scene_id == 1 else "TEXT_REVEAL",
        effect_params={"title": "T"} if scene_id == 1 else {"lines": ["L"]},
        narration=narration,
        voice_config=VoiceConfig(),
        audio_effect=AudioEffect(),
    )


def _make_script(num_scenes: int = 3) -> VideoScript:
    """Create a minimal valid script bypassing model validators for testing."""
    scenes = []
    for i in range(1, num_scenes + 1):
        if i == 1:
            scenes.append(Scene(
                scene_id=i, duration_s=5.0, effect="TITLE_CARD",
                effect_params={"title": "Test"}, narration="Hello.",
            ))
        elif i == num_scenes:
            scenes.append(Scene(
                scene_id=i, duration_s=10.0, effect="CONCLUSION_CARD",
                effect_params={"bullets": ["Point A", "Point B"]},
                narration="In conclusion.",
            ))
        else:
            scenes.append(Scene(
                scene_id=i, duration_s=5.0, effect="TEXT_REVEAL",
                effect_params={"lines": ["line"]}, narration=f"Scene {i}.",
            ))
    total = sum(s.duration_s for s in scenes)
    return VideoScript.model_construct(
        title="Test Video",
        topic="test",
        total_duration_s=total,
        scenes=scenes,
    )


def _make_real_mp3(duration_s: float = 2.0) -> bytes:
    """Generate a real silent MP3 binary using ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono",
            "-t", str(duration_s),
            "-q:a", "9",
            tmp_path,
        ],
        capture_output=True,
        check=True,
    )
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.unlink(tmp_path)
    return data


# ── Tests: _measure_duration ───────────────────────────────────────────────────

class TestMeasureDuration:
    def test_returns_correct_duration(self, tmp_path):
        mp3_data = _make_real_mp3(duration_s=3.0)
        mp3_file = tmp_path / "test.mp3"
        mp3_file.write_bytes(mp3_data)
        duration = _measure_duration(str(mp3_file))
        assert abs(duration - 3.0) < 0.2  # tolerance for MP3 encoding

    def test_short_audio_is_measurable(self, tmp_path):
        mp3_data = _make_real_mp3(duration_s=0.5)
        mp3_file = tmp_path / "short.mp3"
        mp3_file.write_bytes(mp3_data)
        duration = _measure_duration(str(mp3_file))
        assert duration > 0


# ── Tests: generate_speech ─────────────────────────────────────────────────────

class TestGenerateSpeech:
    """All tests mock the Google Cloud TTS client."""

    def _mock_tts_response(self, mp3_bytes: bytes) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.audio_content = mp3_bytes
        return mock_resp

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_returns_speech_result_with_all_scenes(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="test-job", tmp_dir=str(tmp_path))

        assert isinstance(result, SpeechResult)
        assert len(result.scenes) == 3

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_scene_audio_files_exist_on_disk(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="test-job", tmp_dir=str(tmp_path))

        for scene_audio in result.scenes:
            assert os.path.isfile(scene_audio.audio_path)

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_actual_duration_is_populated(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=3.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="test-job", tmp_dir=str(tmp_path))

        for scene_audio in result.scenes:
            assert scene_audio.actual_duration_s > 0

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_files_are_named_by_scene_id(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="abc-123", tmp_dir=str(tmp_path))

        for scene_audio in result.scenes:
            filename = os.path.basename(scene_audio.audio_path)
            assert filename == f"scene_{scene_audio.scene_id:02d}.mp3"

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_progress_callback_is_called(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        calls = []
        script = _make_script(num_scenes=3)
        generate_speech(script, job_id="job", tmp_dir=str(tmp_path), progress_cb=calls.append)

        assert len(calls) >= 3  # at least one call per scene

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_raises_on_empty_audio_response(self, MockClient, tmp_path):
        """TTS returns too few bytes → SpeechGenerationError after retries."""
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(b"\x00" * 10)

        script = _make_script(num_scenes=3)
        with pytest.raises(SpeechGenerationError, match="scene 1"):
            generate_speech(script, job_id="bad-job", tmp_dir=str(tmp_path))

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_retries_on_api_error_then_succeeds(self, MockClient, tmp_path):
        """First call raises exception, second call succeeds."""
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_resp = self._mock_tts_response(mp3_bytes)

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient API error")
            return mock_resp

        mock_client.synthesize_speech.side_effect = side_effect

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="retry-job", tmp_dir=str(tmp_path))
        assert len(result.scenes) == 3
        assert call_count > 1  # confirms retry happened

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_speech_result_get_by_scene_id(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="get-job", tmp_dir=str(tmp_path))

        assert result.get(1) is not None
        assert result.get(999) is None

    @patch("app.pipeline.gen_speech.texttospeech.TextToSpeechClient")
    def test_total_audio_duration_is_sum_of_scenes(self, MockClient, tmp_path):
        mp3_bytes = _make_real_mp3(duration_s=2.0)
        mock_client = MockClient.return_value
        mock_client.synthesize_speech.return_value = self._mock_tts_response(mp3_bytes)

        script = _make_script(num_scenes=3)
        result = generate_speech(script, job_id="dur-job", tmp_dir=str(tmp_path))

        expected = sum(s.actual_duration_s for s in result.scenes)
        assert abs(result.total_audio_duration_s - expected) < 0.01
