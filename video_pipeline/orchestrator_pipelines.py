from pathlib import Path

from video_pipeline.models import ArtifactKind, ArtifactRecord
from video_pipeline.orchestrator import OrchestratorContext, OrchestratorStep
from video_pipeline.providers.local_vision import LocalVisionProvider


def text_to_video_steps() -> list[OrchestratorStep]:
    return [
        OrchestratorStep("script", "Generate script/story plan", _placeholder_script, provider_key="planner"),
        OrchestratorStep("images", "Generate scene images", _placeholder_images, ["script"], provider_key="image", allow_parallel=False),
        OrchestratorStep("audio", "Generate TTS and timestamps", _placeholder_audio, ["script"], provider_key="audio", allow_parallel=False),
        OrchestratorStep("captions", "Build captions", _placeholder_captions, ["audio"]),
        OrchestratorStep("video", "Assemble final video", _placeholder_video, ["images", "captions"]),
    ]


def image_to_video_steps() -> list[OrchestratorStep]:
    return [
        OrchestratorStep("privacy", "Optional face hiding", _privacy_passthrough, provider_key="local-vision"),
        OrchestratorStep("motion", "Create image-to-video motion clip", _placeholder_video, ["privacy"]),
        OrchestratorStep("captions", "Attach captions if available", _placeholder_captions, ["motion"]),
    ]


def audio_to_captions_steps() -> list[OrchestratorStep]:
    return [
        OrchestratorStep("transcript", "Transcribe audio to text", _placeholder_transcript, provider_key="audio"),
        OrchestratorStep("captions", "Create timed captions", _placeholder_captions, ["transcript"]),
    ]


def _write_text_artifact(context: OrchestratorContext, artifact_id: str, kind: ArtifactKind, filename: str, text: str) -> ArtifactRecord:
    path = context.artifact_path(filename)
    path.write_text(text, encoding="utf-8")
    return ArtifactRecord(id=artifact_id, kind=kind, path=str(path.relative_to(context.job_dir)), provider="placeholder")


def _placeholder_script(context: OrchestratorContext) -> list[ArtifactRecord]:
    idea = context.manifest.input_data.get("idea", "Untitled idea")
    return [_write_text_artifact(context, "script", ArtifactKind.script, "script.txt", f"Draft script for: {idea}\n")]


def _placeholder_images(context: OrchestratorContext) -> list[ArtifactRecord]:
    return [_write_text_artifact(context, "image-prompts", ArtifactKind.prompt, "image_prompts.txt", "Scene image prompts pending real provider execution.\n")]


def _placeholder_audio(context: OrchestratorContext) -> list[ArtifactRecord]:
    return [_write_text_artifact(context, "audio-plan", ArtifactKind.audio, "audio_plan.txt", "TTS chunks pending real provider execution.\n")]


def _placeholder_transcript(context: OrchestratorContext) -> list[ArtifactRecord]:
    return [_write_text_artifact(context, "transcript", ArtifactKind.transcript, "transcript.txt", "Transcript pending provider execution.\n")]


def _placeholder_captions(context: OrchestratorContext) -> list[ArtifactRecord]:
    return [_write_text_artifact(context, "captions", ArtifactKind.caption, "captions.srt", "1\n00:00:00,000 --> 00:00:01,000\nCaption placeholder\n")]


def _placeholder_video(context: OrchestratorContext) -> list[ArtifactRecord]:
    return [_write_text_artifact(context, "video-plan", ArtifactKind.video, "video_plan.txt", "Video assembly placeholder.\n")]


def _privacy_passthrough(context: OrchestratorContext) -> list[ArtifactRecord]:
    input_path = context.manifest.input_data.get("image_path")
    if input_path and Path(input_path).exists():
        output = context.artifact_path("privacy_hidden.png")
        metadata = LocalVisionProvider().hide_faces(Path(input_path), output)
        return [ArtifactRecord(id="privacy-mask", kind=ArtifactKind.privacy_mask, path=str(output.relative_to(context.job_dir)), data=metadata)]
    return [_write_text_artifact(context, "privacy-mask", ArtifactKind.privacy_mask, "privacy.txt", "No image provided.\n")]
