from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from video_pipeline.models import VideoPlan, WordTimestamp


class ProviderError(RuntimeError):
    pass


class MissingTimestampsError(ProviderError):
    pass


@dataclass(frozen=True)
class AudioResult:
    audio_path: Path
    timestamps: list[WordTimestamp]
    timestamp_source: str


class PlannerProvider(Protocol):
    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        ...


class AudioProvider(Protocol):
    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        ...


class ImageProvider(Protocol):
    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        ...

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        ...


class UnsupportedAudioProvider:
    def __init__(self, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        raise ProviderError(
            f"Audio provider '{self.provider_name}' with model '{self.model}' is configured, "
            "but this MVP does not have that API adapter yet."
        )


class UnsupportedImageProvider:
    def __init__(self, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        raise ProviderError(
            f"Image provider '{self.provider_name}' with model '{self.model}' is configured, "
            "but this MVP does not have that API adapter yet."
        )

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        raise ProviderError(
            f"Image provider '{self.provider_name}' with model '{self.model}' is configured, "
            "but this MVP does not have that API adapter yet."
        )
