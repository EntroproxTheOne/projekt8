from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.models import AudioResult, WordTimestamp
from video_pipeline.providers.base import ProviderError, TranscriptionProvider
from video_pipeline.timestamps import estimate_word_timestamps


class DeepgramAudioProvider:
    provider_name = "deepgram-audio"

    def __init__(self, settings: Settings, transcription_fallback: TranscriptionProvider | None = None):
        self.settings = settings
        self.transcription_fallback = transcription_fallback

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.settings.deepgram_api_key:
            raise ProviderError("DEEPGRAM_API_KEY is required for Deepgram Aura 2 TTS.")
        response = requests.post(
            f"https://api.deepgram.com/v1/speak?model={self.settings.deepgram_tts_model}",
            headers={"Authorization": f"Token {self.settings.deepgram_api_key}", "Content-Type": "text/plain"},
            data=text.encode("utf-8"),
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Deepgram TTS failed: {response.text[:500]}")
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        if output_audio_path.suffix.lower() != ".mp3":
            output_audio_path = output_audio_path.with_suffix(".mp3")
        output_audio_path.write_bytes(response.content)
        if self.transcription_fallback:
            timestamps = self.transcription_fallback.transcribe_word_timestamps(output_audio_path, text)
            source = self.transcription_fallback.provider_name
        else:
            timestamps = estimate_word_timestamps(text)
            source = "estimated"
        return AudioResult(audio_path=output_audio_path, timestamps=timestamps, timestamp_source=source, provider=self.provider_name)

    def transcribe_word_timestamps(self, audio_path: Path, expected_text: str | None = None) -> list[WordTimestamp]:
        if not self.settings.deepgram_api_key:
            raise ProviderError("DEEPGRAM_API_KEY is required for caption transcription.")
        mime = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        response = requests.post(
            "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true",
            headers={"Authorization": f"Token {self.settings.deepgram_api_key}", "Content-Type": mime},
            data=audio_path.read_bytes(), timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Deepgram transcription failed: {response.text[:500]}")
        words = response.json().get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("words", [])
        if not words:
            raise ProviderError("Deepgram transcription returned no word timestamps.")
        return [WordTimestamp(word=item.get("punctuated_word") or item["word"], start=float(item["start"]), end=float(item["end"])) for item in words]
