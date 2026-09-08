import wave
from pathlib import Path

from PIL import Image, ImageDraw

from video_pipeline.models import AudioResult, ScenePlan, TitleAndDescription, VideoPlan
from video_pipeline.timestamps import estimate_word_timestamps


class MockPlannerProvider:
    provider_name = "mock-planner"

    def generate_video_plan(self, idea: str, target_word_count: int, target_image_count: int) -> VideoPlan:
        return VideoPlan(
            scenes=[
                ScenePlan(
                    paragraph_index=1,
                    narration=f"{idea} begins with a simple question. Why do ordinary moments suddenly change direction?",
                    image_prompt=f"Cinematic documentary frame about {idea}, scene one, vertical 9:16",
                ),
                ScenePlan(
                    paragraph_index=2,
                    narration="The answer is rarely dramatic at first. It is usually a quiet pattern becoming visible.",
                    image_prompt=f"Cinematic documentary frame about {idea}, scene two, vertical 9:16",
                ),
            ],
            thumbnail_prompt=f"Bold YouTube thumbnail about {idea}",
            title_and_description=TitleAndDescription(
                title=f"The Hidden Pattern Behind {idea}",
                description=f"A short faceless documentary about {idea}.",
            ),
        )


class MockImageProvider:
    provider_name = "mock-image"

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1080, 1920), (24, 47, 68))
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 260, 1000, 1500), outline=(247, 214, 93), width=8)
        draw.text((110, 320), prompt[:120], fill=(255, 255, 255))
        draw.text((110, 420), narration_context[:120], fill=(220, 235, 245))
        image.save(output_path)
        return output_path

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self.generate_scene_image(prompt, "thumbnail", output_path)


class MockAudioProvider:
    provider_name = "mock-audio"

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(1.0, len(text.split()) * 0.32)
        framerate = 44100
        frames = int(duration * framerate)
        with wave.open(str(output_audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(framerate)
            wav.writeframes(b"\x00\x00" * frames)
        return AudioResult(
            audio_path=output_audio_path,
            timestamps=estimate_word_timestamps(text, duration),
            timestamp_source="mock-estimated",
            provider=self.provider_name,
        )
