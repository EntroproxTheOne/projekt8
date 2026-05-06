import json
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from uuid import uuid4

from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest
from video_pipeline.models import VideoPlan
from video_pipeline.providers.base import AudioProvider, ImageProvider, PlannerProvider, ProviderError
from video_pipeline.timestamps import validate_word_timestamps


@dataclass(frozen=True)
class PipelineServices:
    planner: PlannerProvider
    audio: AudioProvider
    images: ImageProvider
    audio_fallback: AudioProvider | None = None
    image_fallback: ImageProvider | None = None


def new_run_id() -> str:
    return uuid4().hex[:12]


def generate_plan(
    idea: str,
    duration: int,
    audio_provider: str,
    base_output_dir: Path,
    run_id: str | None,
    services: PipelineServices,
) -> object:
    resolved_run_id = run_id or new_run_id()
    paths = RunPaths(base_output_dir, resolved_run_id)
    manifest = create_or_load_manifest(paths, idea, duration, audio_provider)
    if paths.plan_path.exists():
        return manifest
    plan = services.planner.generate_video_plan(idea, duration * 150, duration * 12)
    plan = VideoPlan(
        scenes=plan.scenes[:2],
        thumbnail_prompt=plan.thumbnail_prompt,
        title_and_description=plan.title_and_description,
    )
    paths.plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    manifest.plan_path = str(paths.plan_path.relative_to(paths.run_dir))
    manifest.metadata_path = str(paths.metadata_path.relative_to(paths.run_dir))
    manifest.scenes = []
    for scene in plan.scenes:
        manifest.scene_status(scene.paragraph_index)
    title = plan.title_and_description.title
    description = plan.title_and_description.description
    paths.metadata_path.write_text(f"{title}\n\n{description}\n", encoding="utf-8")
    save_manifest(paths, manifest)
    return manifest


def load_plan(paths: RunPaths) -> VideoPlan:
    return VideoPlan.model_validate_json(paths.plan_path.read_text(encoding="utf-8"))


def generate_assets(base_output_dir: Path, run_id: str, services: PipelineServices) -> object:
    paths = RunPaths(base_output_dir, run_id)
    manifest = create_or_load_manifest(paths, idea="resume", duration=1, audio_provider="groq")
    plan = load_plan(paths)
    scenes = plan.scenes[:2]
    for scene in scenes:
        status = manifest.scene_status(scene.paragraph_index)
        image_path = paths.image_path(scene.paragraph_index)
        try:
            if not image_path.exists():
                generate_image_with_retry(
                    services.images,
                    services.image_fallback,
                    scene.image_prompt,
                    scene.narration,
                    image_path,
                )
            status.image_path = str(image_path.relative_to(paths.run_dir))
            status.error = None
        except Exception as exc:
            status.error = str(exc)
            save_manifest(paths, manifest)
            raise
        save_manifest(paths, manifest)
    for scene in scenes:
        status = manifest.scene_status(scene.paragraph_index)
        audio_path = paths.audio_path(scene.paragraph_index)
        timestamps_path = paths.timestamps_path(scene.paragraph_index)
        result = None
        try:
            if not audio_path.exists() or not timestamps_path.exists():
                result = synthesize_audio_with_fallback(
                    services.audio,
                    services.audio_fallback,
                    scene.narration,
                    audio_path,
                    timestamps_path,
                )
                validate_word_timestamps(result.timestamps)
                timestamps_path.write_text(
                    json.dumps([item.model_dump() for item in result.timestamps], indent=2),
                    encoding="utf-8",
                )
                status.timestamp_source = result.timestamp_source
            status.audio_path = (
                result.audio_path.relative_to(paths.run_dir).as_posix()
                if result is not None
                else audio_path.relative_to(paths.run_dir).as_posix()
            )
            status.timestamps_path = timestamps_path.relative_to(paths.run_dir).as_posix()
            status.error = None
        except Exception as exc:
            status.error = str(exc)
            save_manifest(paths, manifest)
            raise
        save_manifest(paths, manifest)
    thumbnail_path = paths.images_dir / "thumbnail.png"
    if not thumbnail_path.exists():
        try:
            services.images.generate_thumbnail(plan.thumbnail_prompt, thumbnail_path)
        except ProviderError:
            if services.image_fallback is None:
                raise
            services.image_fallback.generate_thumbnail(plan.thumbnail_prompt, thumbnail_path)
    manifest.thumbnail_path = str(thumbnail_path.relative_to(paths.run_dir))
    save_manifest(paths, manifest)
    return manifest


def generate_image_with_retry(
    primary: ImageProvider,
    fallback: ImageProvider | None,
    prompt: str,
    narration_context: str,
    output_path: Path,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> Path:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return primary.generate_scene_image(prompt, narration_context, output_path)
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                sleep(backoff_seconds)
    if fallback is not None:
        return fallback.generate_scene_image(prompt, narration_context, output_path)
    if last_error is not None:
        raise last_error
    raise ProviderError("Image generation failed without an error")


def synthesize_audio_with_fallback(
    primary: AudioProvider,
    fallback: AudioProvider | None,
    text: str,
    output_audio_path: Path,
    output_timestamps_path: Path,
):
    try:
        return primary.synthesize_with_timestamps(text, output_audio_path, output_timestamps_path)
    except Exception:
        if fallback is None:
            raise
        return fallback.synthesize_with_timestamps(text, output_audio_path, output_timestamps_path)
