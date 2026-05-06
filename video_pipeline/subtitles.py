import html
from pathlib import Path

import numpy as np
from moviepy import ImageClip
from PIL import Image, ImageDraw, ImageFont

from video_pipeline.models import WordTimestamp


def group_words(words: list[WordTimestamp], max_words: int = 6) -> list[list[WordTimestamp]]:
    return [words[index:index + max_words] for index in range(0, len(words), max_words)]


def active_word_index(words: list[WordTimestamp], time_seconds: float) -> int | None:
    for index, word in enumerate(words):
        if word.start <= time_seconds < word.end:
            return index
    return None


def render_subtitle_html(words: list[WordTimestamp], active_index: int | None) -> str:
    parts = []
    for index, word in enumerate(words):
        escaped = html.escape(word.word)
        if index == active_index:
            parts.append(f'<span class="subtitle-active">{escaped}</span>')
        else:
            parts.append(f"<span>{escaped}</span>")
    return " ".join(parts)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=3)
    return box[2] - box[0], box[3] - box[1]


def _subtitle_image(group: list[WordTimestamp], active_index: int, video_size: tuple[int, int]) -> np.ndarray:
    width, _height = video_size
    canvas_h = 180
    image = Image.new("RGBA", (width, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    base_font = _font(58)
    active_font = _font(74)
    gap = 18
    measurements = []
    total_w = 0
    max_h = 0
    for index, word in enumerate(group):
        font = active_font if index == active_index else base_font
        size = _measure(draw, word.word, font)
        measurements.append((font, size))
        total_w += size[0]
        max_h = max(max_h, size[1])
    total_w += gap * (len(group) - 1)
    x = max(20, (width - total_w) // 2)
    y = (canvas_h - max_h) // 2
    for index, word in enumerate(group):
        font, (word_w, _word_h) = measurements[index]
        fill = (255, 230, 0, 255) if index == active_index else (255, 255, 255, 255)
        draw.text((x, y), word.word, font=font, fill=fill, stroke_width=4, stroke_fill=(0, 0, 0, 230))
        x += word_w + gap
    return np.array(image)


def build_dynamic_subtitle_clips(words: list[WordTimestamp], video_size: tuple[int, int]) -> list[ImageClip]:
    clips: list[ImageClip] = []
    _width, height = video_size
    y = int(height * 0.72)
    for group in group_words(words):
        for index, word in enumerate(group):
            clip = (
                ImageClip(_subtitle_image(group, index, video_size))
                .with_start(word.start)
                .with_duration(max(0.01, word.end - word.start))
                .with_position(("center", y))
            )
            clips.append(clip)
    return clips
