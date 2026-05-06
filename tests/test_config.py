import pytest

from video_pipeline.config import Settings, load_settings


def test_settings_calculates_duration_targets():
    settings = Settings(video_idea="AI history", target_duration_minutes=5)

    assert settings.target_word_count == 750
    assert settings.suggested_image_count == 60
    assert settings.audio_provider == "deepgram"
    assert settings.gemini_text_model == "gemini-3.1-flash-lite-preview"
    assert settings.deepgram_tts_model == "aura-2-asteria-en"
    assert settings.groq_transcription_model == "whisper-large-v3"


def test_settings_rejects_invalid_duration():
    with pytest.raises(ValueError, match="between 1 and 60"):
        Settings(video_idea="AI history", target_duration_minutes=0)


def test_load_settings_reads_provider_and_keys(monkeypatch):
    monkeypatch.setenv("AUDIO_PROVIDER", "deepgram")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROK_API_KEY", "grok-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-key")

    settings = load_settings(video_idea="Space mystery", target_duration_minutes=3)

    assert settings.audio_provider == "deepgram"
    assert settings.groq_api_key == "groq-key"
    assert settings.grok_api_key == "grok-key"
    assert settings.gemini_api_key == "gemini-key"
    assert settings.deepgram_api_key == "deepgram-key"


def test_settings_expose_image_and_audio_model_tiers():
    settings = Settings(video_idea="AI history", target_duration_minutes=1)

    assert settings.image_model_tier == "cheap"
    assert settings.image_model_options["cheap"] == ["grok-imagine-image"]
    assert settings.image_model_options["pro"] == ["gemini-3.1-flash-image-preview"]
    assert settings.audio_model_options["cheap"] == [
        "aura-2-asteria-en",
        "aura-2-zeus-en",
        "gemini-3.1-flash-tts-preview",
        "realtimetts-1.5-mini",
        "inworld-realtime-tts-1.5max",
    ]


def test_settings_accept_realtime_and_inworld_audio_providers():
    assert Settings(video_idea="AI history", target_duration_minutes=1, audio_provider="realtimetts").audio_provider == "realtimetts"
    assert Settings(video_idea="AI history", target_duration_minutes=1, audio_provider="inworld").audio_provider == "inworld"
