import json
from pathlib import Path

from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_audioclips, concatenate_videoclips

from video_pipeline.manifest import RunPaths, save_manifest
from video_pipeline.models import RunManifest, WordTimestamp
from video_pipeline.subtitles import build_dynamic_subtitle_clips
from video_pipeline.timestamps import offset_timestamps, validate_word_timestamps


def distribute_clip_durations(audio_durations: list[float]) -> list[float]:
    return audio_durations


def ken_burns_clip(image_path: Path, duration: float, size: tuple[int, int]) -> ImageClip:
    width, height = size
    clip = ImageClip(str(image_path)).with_duration(duration)
    image_aspect = clip.w / clip.h
    target_aspect = width / height
    if image_aspect > target_aspect:
        clip = clip.resized(height=height)
    else:
        clip = clip.resized(width=width)
    return (
        clip.cropped(width=width, height=height, x_center=clip.w / 2, y_center=clip.h / 2)
        .resized(lambda t: 1.0 + 0.04 * (t / max(duration, 0.01)))
        .with_position("center")
    )


def render_video(paths: RunPaths, width: int = 1080, height: int = 1920) -> Path:
    manifest = RunManifest.model_validate_json(paths.manifest_path.read_text(encoding="utf-8"))
    audio_clips = []
    image_clips = []
    all_words: list[WordTimestamp] = []
    offset = 0.0
    for scene in manifest.scenes:
        if scene.error:
            raise ValueError(f"Cannot render with failed scene {scene.paragraph_index}: {scene.error}")
        if not scene.audio_path or not scene.image_path or not scene.timestamps_path:
            raise ValueError(f"Cannot render incomplete scene {scene.paragraph_index}")
        audio_path = paths.run_dir / scene.audio_path
        image_path = paths.run_dir / scene.image_path
        timestamps_path = paths.run_dir / scene.timestamps_path
        audio_clip = AudioFileClip(str(audio_path))
        audio_clips.append(audio_clip)
        image_clips.append(ken_burns_clip(image_path, audio_clip.duration, (width, height)))
        words = [WordTimestamp.model_validate(item) for item in json.loads(timestamps_path.read_text(encoding="utf-8"))]
        validate_word_timestamps(words)
        all_words.extend(offset_timestamps(words, offset))
        offset += audio_clip.duration
    if not audio_clips or not image_clips:
        raise ValueError("No complete scenes are available to render")
    video = concatenate_videoclips(image_clips, method="compose")
    audio = concatenate_audioclips(audio_clips)
    subtitle_clips = build_dynamic_subtitle_clips(all_words, (width, height))
    final = CompositeVideoClip([video, *subtitle_clips], size=(width, height)).with_audio(audio)
    final.write_videofile(str(paths.final_video_path), fps=30, codec="libx264", audio_codec="aac")
    manifest.final_video_path = str(paths.final_video_path.relative_to(paths.run_dir))
    save_manifest(paths, manifest)
    for clip in [*audio_clips, *image_clips, video, audio, final]:
        try:
            clip.close()
        except Exception:
            pass
    return paths.final_video_path
