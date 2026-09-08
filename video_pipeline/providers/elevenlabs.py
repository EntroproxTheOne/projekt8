from pathlib import Path
from typing import Any

import requests

from video_pipeline.config import Settings
from video_pipeline.models import AudioResult, WordTimestamp
from video_pipeline.providers.base import ProviderError, TranscriptionProvider
from video_pipeline.timestamps import estimate_word_timestamps


class ElevenLabsProvider:
    provider_name = "elevenlabs"

    def __init__(self, settings: Settings, alignment_fallback: TranscriptionProvider | None = None):
        self.settings = settings
        self.alignment_fallback = alignment_fallback

    @property
    def headers(self) -> dict[str, str]:
        if not self.settings.elevenlabs_api_key:
            raise ProviderError("ELEVENLABS_API_KEY is required for ElevenLabs.")
        return {"xi-api-key": self.settings.elevenlabs_api_key}

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if output_audio_path.suffix.lower() != ".mp3":
            output_audio_path = output_audio_path.with_suffix(".mp3")
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.settings.elevenlabs_voice_id}",
            headers={**self.headers, "Content-Type": "application/json"},
            params={"output_format": "mp3_44100_128"},
            json={"text": text, "model_id": self.settings.elevenlabs_tts_model},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"ElevenLabs TTS failed: {response.text[:500]}")
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        output_audio_path.write_bytes(response.content)
        timestamps = self.force_align(output_audio_path, text)
        return AudioResult(
            audio_path=output_audio_path,
            timestamps=timestamps,
            timestamp_source="elevenlabs-forced-alignment",
            provider=self.provider_name,
            cost=_float_header(response.headers.get("character-cost")),
        )

    def force_align(self, audio_path: Path, text: str) -> list[WordTimestamp]:
        with audio_path.open("rb") as file:
            response = requests.post(
                "https://api.elevenlabs.io/v1/forced-alignment",
                headers=self.headers,
                files={"file": (audio_path.name, file)},
                data={"text": text},
                timeout=self.settings.network_timeout_seconds,
            )
        if response.status_code >= 400:
            if self.alignment_fallback:
                return self.alignment_fallback.transcribe_word_timestamps(audio_path, text)
            return estimate_word_timestamps(text)
        words = response.json().get("words") or []
        if not words:
            return estimate_word_timestamps(text)
        return [
            WordTimestamp(word=item.get("text") or item.get("word", ""), start=float(item["start"]), end=float(item["end"]))
            for item in words
            if item.get("start") is not None and item.get("end") is not None
        ]

    def voice_change(self, audio_path: Path, output_path: Path, voice_id: str | None = None) -> Path:
        with audio_path.open("rb") as file:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id or self.settings.elevenlabs_voice_id}",
                headers=self.headers,
                params={"output_format": "mp3_44100_128"},
                files={"audio": (audio_path.name, file)},
                data={"model_id": "eleven_multilingual_sts_v2"},
                timeout=self.settings.network_timeout_seconds,
            )
        if response.status_code >= 400:
            raise ProviderError(f"ElevenLabs voice changer failed: {response.text[:500]}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path

    def sound_effect(self, prompt: str, output_path: Path, duration_seconds: float | None = None) -> Path:
        payload: dict[str, Any] = {"text": prompt, "model_id": "eleven_text_to_sound_v2"}
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds
        response = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"ElevenLabs sound effect failed: {response.text[:500]}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path

    def dialogue(self, inputs: list[dict[str, str]], output_path: Path) -> Path:
        response = requests.post(
            "https://api.elevenlabs.io/v1/text-to-dialogue",
            headers={**self.headers, "Content-Type": "application/json"},
            json={"inputs": inputs, "model_id": "eleven_v3"},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"ElevenLabs dialogue failed: {response.text[:500]}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path


def _float_header(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
