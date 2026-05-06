from pathlib import Path

import requests

from video_pipeline.models import WordTimestamp
from video_pipeline.providers.base import ProviderError
from video_pipeline.timestamps import validate_word_timestamps


class GroqWordTranscriber:
    def __init__(self, api_key: str | None, model: str = "whisper-large-v3", timeout_seconds: int = 300) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio_path: Path, prompt: str | None = None) -> list[WordTimestamp]:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is required for Groq word-level transcription")
        with audio_path.open("rb") as audio_file:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={
                    "model": self.model,
                    "response_format": "verbose_json",
                    "language": "en",
                    "temperature": "0",
                    "prompt": prompt or "",
                },
                files={
                    "file": (audio_path.name, audio_file, "audio/wav"),
                    "timestamp_granularities[]": (None, "word"),
                },
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        raw_words = payload.get("words") or []
        words = [
            WordTimestamp(word=str(item["word"]).strip(), start=float(item["start"]), end=float(item["end"]))
            for item in raw_words
            if str(item.get("word", "")).strip()
        ]
        return validate_word_timestamps(words)
