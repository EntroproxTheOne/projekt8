import base64
from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.models import AudioResult
from video_pipeline.providers.base import ProviderError, TranscriptionProvider
from video_pipeline.timestamps import estimate_word_timestamps


class GeminiAudioProvider:
    provider_name = "gemini-audio"

    def __init__(self, settings: Settings, transcription_fallback: TranscriptionProvider | None = None):
        self.settings = settings
        self.transcription_fallback = transcription_fallback

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini TTS.")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_tts_model}:generateContent"
        )
        response = requests.post(
            url,
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"]},
            },
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Gemini TTS failed: {response.text[:500]}")
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        for candidate in response.json().get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    output_audio_path.write_bytes(base64.b64decode(inline["data"]))
                    timestamps = (
                        self.transcription_fallback.transcribe_word_timestamps(output_audio_path, text)
                        if self.transcription_fallback
                        else estimate_word_timestamps(text)
                    )
                    source = self.transcription_fallback.provider_name if self.transcription_fallback else "estimated"
                    return AudioResult(
                        audio_path=output_audio_path,
                        timestamps=timestamps,
                        timestamp_source=source,
                        provider=self.provider_name,
                    )
        raise ProviderError("Gemini TTS response did not include audio bytes.")
