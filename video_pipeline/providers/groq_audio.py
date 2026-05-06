import json
from pathlib import Path

import requests

from video_pipeline.audio_utils import wav_duration_seconds
from video_pipeline.providers.base import AudioResult, ProviderError
from video_pipeline.providers.transcription import GroqWordTranscriber
from video_pipeline.timestamps import estimate_word_timestamps


class GroqAudioProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str = "playai-tts",
        voice: str = "Fritz-PlayAI",
        transcription_model: str = "whisper-large-v3",
        allow_estimated_timestamps: bool = True,
        timeout_seconds: int = 300,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.allow_estimated_timestamps = allow_estimated_timestamps
        self.timeout_seconds = timeout_seconds
        self.transcriber = GroqWordTranscriber(api_key, transcription_model, timeout_seconds)

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is required for Groq audio generation")
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "voice": self.voice, "input": text, "response_format": "wav"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        output_audio_path.write_bytes(response.content)
        try:
            words = self.transcriber.transcribe(output_audio_path, prompt=text[:200])
            source = "groq-transcription"
        except Exception:
            if not self.allow_estimated_timestamps:
                raise
            words = estimate_word_timestamps(text, wav_duration_seconds(output_audio_path))
            source = "estimated"
        output_timestamps_path.parent.mkdir(parents=True, exist_ok=True)
        output_timestamps_path.write_text(json.dumps([item.model_dump() for item in words], indent=2), encoding="utf-8")
        return AudioResult(output_audio_path, words, source)
