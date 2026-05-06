import base64
import json
from pathlib import Path

import requests

from video_pipeline.audio_utils import wav_duration_seconds, write_pcm_as_wav
from video_pipeline.providers.base import AudioResult, ProviderError
from video_pipeline.providers.transcription import GroqWordTranscriber
from video_pipeline.timestamps import estimate_word_timestamps


class GeminiAudioProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-3.1-flash-tts-preview",
        voice: str = "Kore",
        groq_api_key: str | None = None,
        transcription_model: str = "whisper-large-v3",
        allow_estimated_timestamps: bool = True,
        timeout_seconds: int = 300,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.allow_estimated_timestamps = allow_estimated_timestamps
        self.timeout_seconds = timeout_seconds
        self.transcriber = GroqWordTranscriber(groq_api_key, transcription_model, timeout_seconds)

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini audio generation")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": f"Read this narration exactly:\n{text}"}]}],
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": self.voice,
                                }
                            }
                        },
                    },
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(f"Gemini audio request timed out after {self.timeout_seconds} seconds") from exc
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Gemini audio request failed.{detail}") from exc
        inline_data = self._extract_inline_audio(response.json())
        audio_bytes = base64.b64decode(inline_data["data"])
        mime_type = inline_data.get("mimeType", "")
        if "wav" in mime_type.lower():
            output_audio_path.parent.mkdir(parents=True, exist_ok=True)
            output_audio_path.write_bytes(audio_bytes)
        else:
            write_pcm_as_wav(output_audio_path, audio_bytes)
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

    def _extract_inline_audio(self, payload: dict) -> dict:
        try:
            parts = payload["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise ProviderError("Gemini TTS response did not contain audio parts") from exc
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                return inline_data
        raise ProviderError("Gemini TTS response did not contain inline audio data")
