from pathlib import Path

from video_pipeline.models import AudioResult, ScenePlan, TitleAndDescription, VideoPlan
from video_pipeline.pipeline import PipelineServices, generate_assets, generate_plan
from video_pipeline.providers.base import ProviderError
from video_pipeline.providers.mock import MockAudioProvider, MockImageProvider, MockPlannerProvider
from video_pipeline.timestamps import estimate_word_timestamps


def test_generate_plan_creates_two_scene_plan(tmp_path: Path):
    services = PipelineServices(MockPlannerProvider(), MockAudioProvider(), MockImageProvider())

    manifest = generate_plan("test idea", 1, "mock", tmp_path, None, services)

    assert manifest.plan_path == "plan.json"
    assert len(manifest.scenes) == 2
    assert (tmp_path / manifest.run_id / "metadata.txt").exists()


def test_generate_assets_retries_images_then_fallback(tmp_path: Path, monkeypatch):
    services = PipelineServices(MockPlannerProvider(), MockAudioProvider(), MockImageProvider())
    manifest = generate_plan("retry idea", 1, "mock", tmp_path, "run-a", services)
    calls = {"count": 0}

    class FailingImage:
        provider_name = "fail-image"

        def generate_scene_image(self, prompt, narration_context, output_path):
            calls["count"] += 1
            raise ProviderError("fail")

        def generate_thumbnail(self, prompt, output_path):
            raise ProviderError("fail")

    monkeypatch.setattr("video_pipeline.pipeline.sleep", lambda seconds: None)
    services = PipelineServices(
        MockPlannerProvider(),
        MockAudioProvider(),
        FailingImage(),
        image_fallback=MockImageProvider(),
    )

    generate_assets(tmp_path, manifest.run_id, services)

    assert calls["count"] == 6
    assert (tmp_path / "run-a" / "images" / "image_001.png").exists()


def test_generate_assets_falls_back_to_audio_provider(tmp_path: Path):
    services = PipelineServices(MockPlannerProvider(), MockAudioProvider(), MockImageProvider())
    manifest = generate_plan("audio fallback idea", 1, "mock", tmp_path, "run-a", services)

    class BadAudio:
        provider_name = "bad-audio"

        def synthesize_with_timestamps(self, text, output_audio_path, output_timestamps_path):
            raise ProviderError("bad audio")

    services = PipelineServices(
        MockPlannerProvider(),
        BadAudio(),
        MockImageProvider(),
        audio_fallback=MockAudioProvider(),
    )

    result = generate_assets(tmp_path, manifest.run_id, services)

    assert result.scenes[0].audio_path
    assert result.scenes[0].timestamp_source == "mock-estimated"


def test_audio_result_accepts_estimated_timestamps(tmp_path: Path):
    words = estimate_word_timestamps("hello world", 2.0)
    result = AudioResult(audio_path=tmp_path / "a.wav", timestamps=words, timestamp_source="test")

    assert result.timestamps[0].start == 0


def test_selected_output_skips_unneeded_providers(tmp_path):
    class UnexpectedProvider:
        def __getattr__(self, name):
            raise AssertionError(f'Unselected provider called: {name}')

    for mode in ('image', 'audio'):
        services = PipelineServices(MockPlannerProvider(), MockAudioProvider(), MockImageProvider())
        manifest = generate_plan('A test story', 1, 'mock', tmp_path, mode, services)
        selective = PipelineServices(services.planner,
            services.audio if mode == 'audio' else UnexpectedProvider(),
            services.images if mode == 'image' else UnexpectedProvider())
        result = generate_assets(tmp_path, manifest.run_id, selective, output_mode=mode)
        assert all(bool(scene.image_path) == (mode == 'image') for scene in result.scenes)
        assert all(bool(scene.audio_path) == (mode == 'audio') for scene in result.scenes)
