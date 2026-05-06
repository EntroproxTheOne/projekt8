import math
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_pipeline.models import ScenePlan, TitleDescription, VideoPlan
from video_pipeline.providers.base import AudioResult
from video_pipeline.timestamps import estimate_word_timestamps


class MockPlanner:
    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        scene_count = max(1, min(6, round(target_word_count / 75)))
        scenes = []
        for index in range(1, scene_count + 1):
            narration = (
                f"This is mock paragraph {index} for {idea}. "
                "It demonstrates resumable audio chunks, contextual images, and dynamic subtitles."
            )
            scenes.append(
                ScenePlan(
                    paragraph_index=index,
                    narration=narration,
                    image_prompt=f"A cinematic vertical scene about {idea}, paragraph {index}",
                )
            )
        return VideoPlan(
            scenes=scenes,
            thumbnail_prompt=f"A bold thumbnail about {idea}",
            title_and_description=TitleDescription(
                title=f"{idea}: Mock Video",
                description="Generated in mock mode for local pipeline testing.",
            ),
        )


class MockAudioProvider:
    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        words = text.split()
        duration = max(2.0, len(words) * 0.32)
        sample_rate = 24000
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_audio_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames = bytearray()
            for n in range(int(duration * sample_rate)):
                tone = int(9000 * math.sin(2 * math.pi * 220 * n / sample_rate))
                frames.extend(tone.to_bytes(2, byteorder="little", signed=True))
            wav_file.writeframes(bytes(frames))
        timestamps = estimate_word_timestamps(text, duration)
        output_timestamps_path.parent.mkdir(parents=True, exist_ok=True)
        output_timestamps_path.write_text(
            "[" + ",".join(item.model_dump_json() for item in timestamps) + "]",
            encoding="utf-8",
        )
        return AudioResult(output_audio_path, timestamps, "mock-estimated")


class MockImageProvider:
    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        return self._write_image(output_path, "Scene", prompt)

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self._write_image(output_path, "Thumbnail", prompt)

    def _write_image(self, output_path: Path, heading: str, body: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1080, 1920), (18, 26, 39))
        draw = ImageDraw.Draw(image)
        try:
            heading_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 72)
            body_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
        except OSError:
            heading_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
        draw.rectangle((70, 100, 1010, 1820), outline=(80, 180, 140), width=6)
        draw.text((120, 180), heading, fill=(255, 255, 255), font=heading_font)
        y = 340
        words = body.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > 34:
                draw.text((120, y), line, fill=(210, 230, 220), font=body_font)
                y += 58
                line = word
            else:
                line = candidate
        if line:
            draw.text((120, y), line, fill=(210, 230, 220), font=body_font)
        image.save(output_path)
        return output_path
