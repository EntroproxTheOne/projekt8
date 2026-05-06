import base64

import pytest
import requests

from video_pipeline.models import VideoPlan, WordTimestamp
from video_pipeline.providers.base import AudioResult, ProviderError, UnsupportedAudioProvider, UnsupportedImageProvider
from video_pipeline.providers.deepgram_audio import DeepgramAudioProvider
from video_pipeline.providers.gemini_llm import GeminiPlanner
from video_pipeline.providers.gemini_images import GeminiImageProvider
from video_pipeline.providers.grok_images import GrokImageProvider
from video_pipeline.providers.groq_llm import GroqPlanner


def test_audio_result_keeps_timestamp_source(tmp_path):
    path = tmp_path / "wav_001.wav"
    path.write_bytes(b"RIFF")

    result = AudioResult(
        audio_path=path,
        timestamps=[WordTimestamp(word="Hi", start=0, end=0.2)],
        timestamp_source="groq-transcription",
    )

    assert result.audio_path == path
    assert result.timestamp_source == "groq-transcription"


def test_groq_planner_extracts_json_from_response():
    planner = GroqPlanner(api_key="key", model="model")
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"scenes":[{"paragraph_index":1,"narration":"Hi","image_prompt":"A scene"}],"thumbnail_prompt":"Thumb","title_and_description":{"title":"T","description":"D"}}'
                }
            }
        ]
    }

    plan = planner.parse_response(payload)

    assert isinstance(plan, VideoPlan)
    assert plan.scenes[0].narration == "Hi"


def test_groq_planner_wraps_http_errors(monkeypatch):
    class Response:
        status_code = 401
        text = "bad key"

        def raise_for_status(self):
            raise requests.HTTPError("401 Client Error", response=self)

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("video_pipeline.providers.groq_llm.requests.post", fake_post)
    planner = GroqPlanner(api_key="key", model="model")

    with pytest.raises(ProviderError, match="Groq plan request failed"):
        planner.generate_video_plan("idea", 150, 12)


def test_gemini_planner_extracts_json_from_response():
    planner = GeminiPlanner(api_key="key", model="gemini-3.1-flash")
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '```json\n{"scenes":[{"paragraph_index":1,"narration":"Hi","image_prompt":"A scene"}],"thumbnail_prompt":"Thumb","title_and_description":{"title":"T","description":"D"}}\n```'
                        }
                    ]
                }
            }
        ]
    }

    plan = planner.parse_response(payload)

    assert isinstance(plan, VideoPlan)
    assert plan.scenes[0].image_prompt == "A scene"


def test_gemini_planner_wraps_http_errors(monkeypatch):
    class Response:
        status_code = 400
        text = "bad request"

        def raise_for_status(self):
            raise requests.HTTPError("400 Client Error", response=self)

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("video_pipeline.providers.gemini_llm.requests.post", fake_post)
    planner = GeminiPlanner(api_key="key", model="gemini-3.1-flash")

    with pytest.raises(ProviderError, match="Gemini plan request failed"):
        planner.generate_video_plan("idea", 150, 12)


def test_gemini_image_provider_parses_inline_data(monkeypatch, tmp_path):
    image_bytes = b"fakepng"

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image_bytes).decode("ascii")}}
                            ]
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("video_pipeline.providers.gemini_images.requests.post", fake_post)
    provider = GeminiImageProvider(api_key="key", model="gemini-2.5-flash-image")
    output = provider.generate_scene_image("prompt", "context", tmp_path / "image.png")

    assert output.read_bytes() == image_bytes


def test_gemini_image_provider_requires_key(tmp_path):
    provider = GeminiImageProvider(api_key=None, model="gemini-2.5-flash-image")

    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        provider.generate_thumbnail("prompt", tmp_path / "thumb.png")


def test_gemini_image_provider_wraps_timeout(monkeypatch, tmp_path):
    def fake_post(*args, **kwargs):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr("video_pipeline.providers.gemini_images.requests.post", fake_post)
    provider = GeminiImageProvider(api_key="key", model="gemini-3.1-flash-image-preview")

    with pytest.raises(ProviderError, match="Gemini image request timed out"):
        provider.generate_scene_image("prompt", "context", tmp_path / "image.png")


def test_deepgram_audio_provider_posts_text_and_writes_mp3(monkeypatch, tmp_path):
    class Response:
        headers = {"Content-Type": "audio/mpeg"}
        content = b"mp3 bytes"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        assert "model=aura-2-asteria-en" in url
        assert kwargs["data"] == "hello world"
        return Response()

    monkeypatch.setattr("video_pipeline.providers.deepgram_audio.requests.post", fake_post)
    provider = DeepgramAudioProvider(api_key="key", model="aura-2-asteria-en", groq_api_key=None)

    result = provider.synthesize_with_timestamps("hello world", tmp_path / "wav_001.wav", tmp_path / "timestamps_001.json")

    assert result.audio_path.name == "wav_001.mp3"
    assert result.audio_path.read_bytes() == b"mp3 bytes"
    assert result.timestamp_source == "estimated"


def test_grok_image_provider_downloads_url(monkeypatch, tmp_path):
    class GenerateResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"url": "https://example.test/image.png"}]}

    class ImageResponse:
        content = b"png bytes"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        assert url == "https://api.x.ai/v1/images/generations"
        assert kwargs["json"]["model"] == "grok-imagine-image"
        return GenerateResponse()

    def fake_get(url, **kwargs):
        assert url == "https://example.test/image.png"
        return ImageResponse()

    monkeypatch.setattr("video_pipeline.providers.grok_images.requests.post", fake_post)
    monkeypatch.setattr("video_pipeline.providers.grok_images.requests.get", fake_get)
    provider = GrokImageProvider(api_key="key", model="grok-imagine-image")

    output = provider.generate_scene_image("prompt", "context", tmp_path / "image.png")

    assert output.read_bytes() == b"png bytes"


def test_unsupported_image_provider_fails_with_model_name(tmp_path):
    provider = UnsupportedImageProvider(provider_name="seedrun", model="seedrun-4.0")

    with pytest.raises(ProviderError, match="seedrun-4.0"):
        provider.generate_scene_image("prompt", "context", tmp_path / "image.png")


def test_unsupported_audio_provider_fails_with_model_name(tmp_path):
    provider = UnsupportedAudioProvider(provider_name="realtimetts", model="realtimetts-1.5-mini")

    with pytest.raises(ProviderError, match="realtimetts-1.5-mini"):
        provider.synthesize_with_timestamps("hello", tmp_path / "audio.wav", tmp_path / "timestamps.json")
