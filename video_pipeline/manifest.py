import json
from dataclasses import dataclass
from pathlib import Path

from video_pipeline.models import RunManifest


@dataclass(frozen=True)
class RunPaths:
    base_dir: Path
    run_id: str

    @property
    def run_dir(self) -> Path:
        return self.base_dir / self.run_id

    @property
    def audio_dir(self) -> Path:
        return self.run_dir / "audio"

    @property
    def timestamps_dir(self) -> Path:
        return self.run_dir / "timestamps"

    @property
    def images_dir(self) -> Path:
        return self.run_dir / "images"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def plan_path(self) -> Path:
        return self.run_dir / "plan.json"

    @property
    def metadata_path(self) -> Path:
        return self.run_dir / "metadata.txt"

    @property
    def final_video_path(self) -> Path:
        return self.run_dir / "final_output_video.mp4"

    def audio_path(self, paragraph_index: int) -> Path:
        return self.audio_dir / f"wav_{paragraph_index:03d}.wav"

    def timestamps_path(self, paragraph_index: int) -> Path:
        return self.timestamps_dir / f"timestamps_{paragraph_index:03d}.json"

    def image_path(self, paragraph_index: int) -> Path:
        return self.images_dir / f"image_{paragraph_index:03d}.png"


def ensure_run_dirs(paths: RunPaths) -> None:
    paths.audio_dir.mkdir(parents=True, exist_ok=True)
    paths.timestamps_dir.mkdir(parents=True, exist_ok=True)
    paths.images_dir.mkdir(parents=True, exist_ok=True)


def create_or_load_manifest(paths: RunPaths, idea: str, duration: int, audio_provider: str) -> RunManifest:
    ensure_run_dirs(paths)
    if paths.manifest_path.exists():
        return RunManifest.model_validate_json(paths.manifest_path.read_text(encoding="utf-8"))
    manifest = RunManifest(
        run_id=paths.run_id,
        idea=idea,
        target_duration_minutes=duration,
        audio_provider=audio_provider,
    )
    save_manifest(paths, manifest)
    return manifest


def save_manifest(paths: RunPaths, manifest: RunManifest) -> None:
    ensure_run_dirs(paths)
    paths.manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
