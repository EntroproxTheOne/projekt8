from pathlib import Path

import pytest
from PIL import Image

from video_pipeline.config import load_settings
from video_pipeline.providers.base import ProviderError
from video_pipeline.providers.elevenlabs import ElevenLabsProvider
from video_pipeline.providers.local_vision import LocalVisionProvider
from video_pipeline.providers.openrouter import OpenRouterProvider


def test_openrouter_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = OpenRouterProvider(load_settings("x", 1))

    with pytest.raises(ProviderError):
        provider.list_models()


def test_elevenlabs_requires_key(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    provider = ElevenLabsProvider(load_settings("x", 1))

    with pytest.raises(ProviderError):
        provider.synthesize_with_timestamps("hello", tmp_path / "a.wav", tmp_path / "t.json")


def test_local_vision_hide_faces_copies_when_no_detector_faces(tmp_path: Path):
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.new("RGB", (100, 100), (255, 255, 255)).save(input_path)

    result = LocalVisionProvider().hide_faces(input_path, output_path)

    assert output_path.exists()
    assert "faces_detected" in result
