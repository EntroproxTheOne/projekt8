import json
from pathlib import Path

import requests

from video_pipeline.providers.base import AudioResult, ProviderError
from video_pipeline.providers.transcription import GroqWordTranscriber
from video_pipeline.timestamps import estimate_word_timestamps


class DeepgramAudioProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str = "aura-2-asteria-en",
        groq_api_key: str | None = None,
        transcription_model: str = "whisper-large-v3",
        timeout_seconds: int = 300,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transcriber = GroqWordTranscriber(groq_api_key, transcription_model, timeout_seconds)

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.api_key:
            raise ProviderError("DEEPGRAM_API_KEY is required for Deepgram Aura 2 audio generation")
        try:
            response = requests.post(
                f"https://api.deepgram.com/v1/speak?model={self.model}",
                headers={"Authorization": f"Token {self.api_key}", "Content-Type": "text/plain"},
                data=text,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(f"Deepgram audio request timed out after {self.timeout_seconds} seconds") from exc
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Deepgram audio request failed.{detail}") from exc

        content_type = response.headers.get("Content-Type", "")
        audio_path = output_audio_path if "wav" in content_type.lower() else output_audio_path.with_suffix(".mp3")
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(response.content)

        try:
            words = self.transcriber.transcribe(audio_path, prompt=text[:200])
            source = "groq-transcription"
        except Exception:
            words = estimate_word_timestamps(text, max(2.0, len(text.split()) * 0.35))
            source = "estimated"
        output_timestamps_path.parent.mkdir(parents=True, exist_ok=True)
        output_timestamps_path.write_text(json.dumps([item.model_dump() for item in words], indent=2), encoding="utf-8")
        return AudioResult(audio_path=audio_path, timestamps=words, timestamp_source=source)
