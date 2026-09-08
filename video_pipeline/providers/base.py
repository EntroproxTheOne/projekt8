from pathlib import Path
import re
from typing import Any, Protocol

from video_pipeline.models import AudioResult, VideoPlan, WordTimestamp


class ProviderError(RuntimeError):
    pass


def sanitize_provider_error(error: object, secrets: tuple[str, ...] = ()) -> str:
    message = str(error)
    message = re.sub(r"([?&](?:key|api_key|token)=)[^&\s'\"]+", r"\1[REDACTED]", message, flags=re.IGNORECASE)
    message = re.sub(r"(Authorization['\"]?\s*[:=]\s*['\"]?(?:Bearer|Token)\s+)[^\s'\"]+", r"\1[REDACTED]", message, flags=re.IGNORECASE)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


class PlannerProvider(Protocol):
    provider_name: str

    def generate_video_plan(self, idea: str, target_word_count: int, target_image_count: int) -> VideoPlan:
        ...


class ImageProvider(Protocol):
    provider_name: str

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        ...

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        ...


class AudioProvider(Protocol):
    provider_name: str

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        ...


class TranscriptionProvider(Protocol):
    provider_name: str

    def transcribe_word_timestamps(self, audio_path: Path, expected_text: str | None = None) -> list[WordTimestamp]:
        ...


class MediaUtilityProvider(Protocol):
    provider_name: str

    def run(self, operation: str, input_path: Path, output_path: Path, **kwargs: Any) -> dict[str, Any]:
        ...
