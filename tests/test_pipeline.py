import json

from video_pipeline.models import ScenePlan, TitleDescription, VideoPlan, WordTimestamp
from video_pipeline.pipeline import PipelineServices, generate_assets, generate_plan
from video_pipeline.providers.base import AudioResult
from video_pipeline.providers.base import ProviderError


class FakePlanner:
    def generate_video_plan(self, idea, target_word_count, suggested_image_count):
        return VideoPlan(
            scenes=[
                ScenePlan(paragraph_index=1, narration="Hello world", image_prompt="A bright scene"),
                ScenePlan(paragraph_index=2, narration="Second scene", image_prompt="Another scene"),
                ScenePlan(paragraph_index=3, narration="Third scene", image_prompt="Third scene"),
            ],
            thumbnail_prompt="Thumb",
            title_and_description=TitleDescription(title="Title", description="Description"),
        )


class FakeAudio:
    def __init__(self, calls=None):
        self.calls = calls

    def synthesize_with_timestamps(self, text, output_audio_path, output_timestamps_path):
        if self.calls is not None:
            self.calls.append(f"audio:{output_audio_path.name}")
        output_audio_path.write_bytes(b"RIFF fake wav")
        words = [
            WordTimestamp(word="Hello", start=0, end=0.2),
            WordTimestamp(word="world", start=0.25, end=0.5),
        ]
        output_timestamps_path.write_text(json.dumps([item.model_dump() for item in words]), encoding="utf-8")
        return AudioResult(audio_path=output_audio_path, timestamps=words, timestamp_source="fake")


class FailingAudio:
    def synthesize_with_timestamps(self, text, output_audio_path, output_timestamps_path):
        raise ProviderError("primary audio failed")


class FakeImages:
    def __init__(self, calls=None):
        self.calls = calls

    def generate_scene_image(self, prompt, narration_context, output_path):
        if self.calls is not None:
            self.calls.append(f"image:{output_path.name}")
        output_path.write_bytes(b"fake image")
        return output_path

    def generate_thumbnail(self, prompt, output_path):
        if self.calls is not None:
            self.calls.append(f"thumbnail:{output_path.name}")
        output_path.write_bytes(b"fake thumbnail")
        return output_path


class FailingImages:
    def __init__(self, calls=None):
        self.calls = calls

    def generate_scene_image(self, prompt, narration_context, output_path):
        if self.calls is not None:
            self.calls.append(f"primary-image:{output_path.name}")
        raise ProviderError("primary image failed")

    def generate_thumbnail(self, prompt, output_path):
        if self.calls is not None:
            self.calls.append(f"primary-thumbnail:{output_path.name}")
        raise ProviderError("primary thumbnail failed")


def test_generate_plan_writes_plan_and_metadata(tmp_path):
    services = PipelineServices(planner=FakePlanner(), audio=FakeAudio(), images=FakeImages())

    manifest = generate_plan("Topic", 1, "groq", tmp_path, "run-a", services)

    assert (tmp_path / "run-a" / "plan.json").exists()
    assert (tmp_path / "run-a" / "metadata.txt").read_text(encoding="utf-8").startswith("Title")
    assert [scene.paragraph_index for scene in manifest.scenes] == [1, 2]


def test_generate_assets_skips_existing_audio(tmp_path):
    services = PipelineServices(planner=FakePlanner(), audio=FakeAudio(), images=FakeImages())
    generate_plan("Topic", 1, "groq", tmp_path, "run-a", services)
    generate_assets(tmp_path, "run-a", services)
    first_audio = tmp_path / "run-a" / "audio" / "wav_001.wav"
    first_audio.write_bytes(b"existing")

    generate_assets(tmp_path, "run-a", services)

    assert first_audio.read_bytes() == b"existing"


def test_generate_assets_limits_to_two_scenes_and_runs_images_before_audio(tmp_path):
    calls = []
    services = PipelineServices(planner=FakePlanner(), audio=FakeAudio(calls), images=FakeImages(calls))
    generate_plan("Topic", 1, "gemini", tmp_path, "run-a", services)

    generate_assets(tmp_path, "run-a", services)

    assert calls[:2] == ["image:image_001.png", "image:image_002.png"]
    assert calls[2:4] == ["audio:wav_001.wav", "audio:wav_002.wav"]
    assert "image:image_003.png" not in calls
    assert "audio:wav_003.wav" not in calls


def test_generate_assets_falls_back_to_audio_provider(tmp_path):
    calls = []
    services = PipelineServices(
        planner=FakePlanner(),
        audio=FailingAudio(),
        images=FakeImages(calls),
        audio_fallback=FakeAudio(calls),
    )
    generate_plan("Topic", 1, "deepgram", tmp_path, "run-a", services)

    manifest = generate_assets(tmp_path, "run-a", services)

    assert manifest.scene_status(1).audio_path == "audio/wav_001.wav"
    assert manifest.scene_status(1).timestamp_source == "fake"


def test_generate_assets_retries_images_then_uses_fallback(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("video_pipeline.pipeline.sleep", lambda seconds: None)
    services = PipelineServices(
        planner=FakePlanner(),
        audio=FakeAudio(calls),
        images=FailingImages(calls),
        image_fallback=FakeImages(calls),
    )
    generate_plan("Topic", 1, "deepgram", tmp_path, "run-a", services)

    generate_assets(tmp_path, "run-a", services)

    assert calls[:4] == [
        "primary-image:image_001.png",
        "primary-image:image_001.png",
        "primary-image:image_001.png",
        "image:image_001.png",
    ]
