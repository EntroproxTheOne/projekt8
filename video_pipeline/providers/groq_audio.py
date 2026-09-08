import json
from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.models import AudioResult, WordTimestamp
from video_pipeline.providers.base import ProviderError
from video_pipeline.timestamps import estimate_word_timestamps


class GroqAudioProvider:
    provider_name = "groq-audio"

    def __init__(self, settings: Settings):
        self.settings = settings

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY is required for Groq audio.")
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.settings.groq_api_key}", "Content-Type": "application/json"},
            json={"model": "playai-tts", "voice": "Fritz-PlayAI", "input": text, "response_format": "wav"},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Groq TTS failed: {response.text[:500]}")
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        output_audio_path.write_bytes(response.content)
        timestamps = self.transcribe_word_timestamps(output_audio_path, text)
        return AudioResult(
            audio_path=output_audio_path,
            timestamps=timestamps,
            timestamp_source=self.settings.groq_transcription_model,
            provider=self.provider_name,
        )

    def transcribe_word_timestamps(self, audio_path: Path, expected_text: str | None = None) -> list[WordTimestamp]:
        if not self.settings.groq_api_key:
            if expected_text:
                return estimate_word_timestamps(expected_text)
            raise ProviderError("GROQ_API_KEY is required for Groq transcription.")
        with audio_path.open("rb") as file:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
                files={"file": (audio_path.name, file)},
                data={
                    "model": self.settings.groq_transcription_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                },
                timeout=self.settings.network_timeout_seconds,
            )
        if response.status_code >= 400:
            if expected_text:
                return estimate_word_timestamps(expected_text)
            raise ProviderError(f"Groq transcription failed: {response.text[:500]}")
        payload = response.json()
        if payload.get("words"):
            return [
                WordTimestamp(word=item["word"], start=float(item["start"]), end=float(item["end"]))
                for item in payload["words"]
            ]
        if expected_text:
            return estimate_word_timestamps(expected_text)
        raise ProviderError("Groq transcription did not return word timestamps.")
