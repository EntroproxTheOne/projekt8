import base64
import json
import math
import mimetypes
import re
from pathlib import Path

import requests
from moviepy import AudioFileClip, CompositeVideoClip, VideoFileClip, concatenate_videoclips
from PIL import Image

from run_pipeline import build_services
from video_pipeline.config import load_settings
from video_pipeline.project_store import ProjectStore
from video_pipeline.providers.base import ProviderError, sanitize_provider_error
from video_pipeline.providers.deepgram_audio import DeepgramAudioProvider
from video_pipeline.providers.groq_audio import GroqAudioProvider
from video_pipeline.providers.omni_video import GeminiOmniVideoProvider
from video_pipeline.subtitles import build_dynamic_subtitle_clips
from video_pipeline.timestamps import estimate_word_timestamps


ALLOWED = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".ogg": "audio",
    ".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
    ".pdf": "pdf",
}
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PROJECT_UPLOAD_BYTES = 500 * 1024 * 1024


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-")
    return cleaned[:120] or "upload"


def validate_upload_signature(filename: str, data: bytes) -> None:
    """Reject empty files and obvious extension/content mismatches at the upload boundary."""
    extension = Path(filename).suffix.lower()
    if not data:
        raise ValueError(f"{filename} is empty.")
    signatures = {
        ".png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".webp": lambda value: value.startswith(b"RIFF") and value[8:12] == b"WEBP",
        ".pdf": lambda value: value.startswith(b"%PDF-"),
        ".wav": lambda value: value.startswith(b"RIFF") and value[8:12] == b"WAVE",
        ".ogg": lambda value: value.startswith(b"OggS"),
        ".webm": lambda value: value.startswith(b"\x1aE\xdf\xa3"),
        ".mkv": lambda value: value.startswith(b"\x1aE\xdf\xa3"),
        ".mp3": lambda value: value.startswith(b"ID3") or (len(value) > 1 and value[0] == 0xFF and value[1] & 0xE0 == 0xE0),
        ".mp4": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
        ".mov": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
        ".m4a": lambda value: len(value) >= 12 and value[4:8] == b"ftyp",
    }
    validator = signatures.get(extension)
    if validator and not validator(data[:64]):
        raise ValueError(f"{filename} does not contain valid {extension[1:].upper()} data.")


def scene_durations(total_seconds: int) -> list[float]:
    count = max(1, math.ceil(total_seconds / 8))
    duration = total_seconds / count
    return [round(duration, 3) for _ in range(count - 1)] + [round(total_seconds - duration * (count - 1), 3)]


def _extract_local(path: Path, kind: str, project_dir: Path, settings) -> dict:
    result = {"kind": kind, "status": "processed"}
    try:
        if kind == "image":
            with Image.open(path) as image:
                result.update({"width": image.width, "height": image.height, "format": image.format})
        elif kind == "pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("PDF extraction requires pypdf; install project requirements.") from exc
            reader = PdfReader(str(path))
            result.update({"pages": len(reader.pages), "text": "\n".join((p.extract_text() or "") for p in reader.pages)[:100000]})
        elif kind == "audio":
            words = GroqAudioProvider(settings).transcribe_word_timestamps(path)
            result["transcript"] = " ".join(word.word for word in words)
            result["word_timestamps"] = [word.model_dump() for word in words]
        elif kind == "video":
            clip = VideoFileClip(str(path))
            result.update({"duration": clip.duration, "width": clip.w, "height": clip.h, "fps": clip.fps})
            frame_path = project_dir / "derived" / f"{path.stem}-frame.jpg"
            frame_path.parent.mkdir(parents=True, exist_ok=True)
            clip.save_frame(str(frame_path), t=min(max(0, clip.duration / 2), 3))
            result["representative_frame"] = str(frame_path.relative_to(project_dir)).replace("\\", "/")
            if clip.audio:
                audio_path = project_dir / "derived" / f"{path.stem}-audio.wav"
                clip.audio.write_audiofile(str(audio_path), logger=None)
                words = GroqAudioProvider(settings).transcribe_word_timestamps(audio_path)
                result["transcript"] = " ".join(word.word for word in words)
                result["word_timestamps"] = [word.model_dump() for word in words]
            clip.close()
    except Exception as exc:
        result.update({"status": "processing_error", "error": str(exc)})
    return result


def _json_from_text(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def _analysis_prompt(project: dict, sources: list[dict], durations: list[float]) -> str:
    return f"""You are the planning stage for a video production orchestrator.
Create one coherent storyboard using every supplied source. Do not claim a source was inspected if its status reports an error.
User brief: {project['brief']}
Workflow: {project['workflow']}
Target duration: {project['duration_seconds']} seconds
Aspect ratio: {project['aspect_ratio']}
Required scene durations: {durations}
Locally extracted source information: {json.dumps(sources)}

Return strict JSON with these keys:
intent (string), source_analysis (array with attachment_id, usage, limitations),
characters (array of strings), visual_style (string), dialogue_style (string),
scenes (array exactly {len(durations)} long). Each scene needs description, dialogue, camera, prompt, reference_ids.
Each prompt must request a single continuous scene, specify sound/dialogue, preserve shared characters and style, and contain no duration longer than its assigned clip.
"""


def _gemini_analyze(settings, prompt: str, attachments: list[dict], project_dir: Path) -> dict:
    parts = [{"text": prompt}]
    for attachment in attachments:
        path = project_dir / "uploads" / attachment["stored_name"]
        if path.stat().st_size <= 20 * 1024 * 1024:
            parts.append({"inline_data": {"mime_type": attachment["mime_type"], "data": base64.b64encode(path.read_bytes()).decode()}})
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_text_model}:generateContent",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}},
        timeout=settings.network_timeout_seconds,
    )
    if response.status_code >= 400:
        raise ProviderError(f"Gemini analysis failed: {response.text[:600]}")
    return _json_from_text(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def _openai_compatible_analyze(url: str, key: str, model: str, prompt: str, label: str) -> dict:
    if not key:
        raise ProviderError(f"{label} API key is missing")
    response = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             json={"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}, timeout=300)
    if response.status_code >= 400:
        raise ProviderError(f"{label} analysis failed: {response.text[:600]}")
    return _json_from_text(response.json()["choices"][0]["message"]["content"])


def analyze_project(store: ProjectStore, project_id: str, job_id: str):
    project = store.get_project(project_id)
    settings = load_settings(project["brief"], max(1, math.ceil(project["duration_seconds"] / 60)))
    attachments = store.attachments(project_id)
    project_dir = store.project_dir(project_id)
    store.update_job(job_id, status="running", stage="Inspecting local sources")
    sources = []
    for index, attachment in enumerate(attachments, 1):
        path = project_dir / "uploads" / attachment["stored_name"]
        analysis = {"attachment_id": attachment["id"], "name": attachment["original_name"]}
        analysis.update(_extract_local(path, attachment["kind"], project_dir, settings))
        store.update_attachment_analysis(attachment["id"], analysis)
        sources.append(analysis)
        store.update_job(job_id, completed=index)
    durations = scene_durations(project["duration_seconds"])
    if project["workflow"] == "caption_existing":
        videos = [item for item in attachments if item["kind"] == "video"]
        if not videos:
            raise ValueError("Caption existing footage requires at least one uploaded video.")
        video_source = next(item for item in sources if item["attachment_id"] == videos[0]["id"])
        packet = {"schema_version": 1, "project_id": project_id, "analysis_provider": "local+groq",
                  "intent": "Caption existing footage", "source_analysis": sources,
                  "characters": [], "visual_style": "Preserve source footage", "dialogue_style": "Source audio",
                  "sources": sources, "scene_durations": [float(video_source.get("duration") or project["duration_seconds"])]}
        store.set_analysis(project_id, "local+groq", packet)
        store.replace_scenes(project_id, [{"duration_seconds": packet["scene_durations"][0],
            "description": f"Caption {videos[0]['original_name']}", "dialogue": video_source.get("transcript", ""),
            "camera": "Preserve source", "prompt": "Preserve uploaded footage", "reference_ids": [videos[0]["id"]],
            "storyboard_path": video_source.get("representative_frame")}])
        store.update_job(job_id, status="complete", stage="Transcript ready for review", completed=len(attachments), total=len(attachments))
        return
    prompt = _analysis_prompt(project, sources, durations)
    attempts = []
    packet, provider = None, None
    for name, call in [
        ("gemini", lambda: _gemini_analyze(settings, prompt, attachments, project_dir)),
        ("groq", lambda: _openai_compatible_analyze("https://api.groq.com/openai/v1/chat/completions", settings.groq_api_key, "openai/gpt-oss-120b", prompt, "Groq")),
        ("grok", lambda: _openai_compatible_analyze("https://api.x.ai/v1/chat/completions", settings.grok_api_key, "grok-4-fast-reasoning", prompt, "Grok")),
    ]:
        try:
            store.update_job(job_id, stage=f"Planning with {name.title()}")
            packet, provider = call(), name
            break
        except Exception as exc:
            attempts.append({"provider": name, "error": sanitize_provider_error(exc, (
                settings.gemini_api_key, settings.groq_api_key, settings.grok_api_key,
            ))})
    if packet is None:
        raise ProviderError("All analysis providers failed: " + "; ".join(f"{a['provider']}: {a['error']}" for a in attempts))
    raw_scenes = packet.get("scenes") or []
    if len(raw_scenes) != len(durations):
        raise ValueError(f"Analysis returned {len(raw_scenes)} scenes; expected {len(durations)}")
    scenes = []
    all_ids = {item["id"] for item in attachments}
    for index, (scene, duration) in enumerate(zip(raw_scenes, durations), 1):
        refs = [value for value in scene.get("reference_ids", []) if value in all_ids]
        scenes.append({"duration_seconds": duration, "description": str(scene.get("description", "")),
                       "dialogue": str(scene.get("dialogue", "")), "camera": str(scene.get("camera", "")),
                       "prompt": str(scene.get("prompt", scene.get("description", ""))), "reference_ids": refs})
    packet.update({"schema_version": 1, "project_id": project_id, "analysis_provider": provider,
                   "provider_attempts": attempts, "sources": sources, "scene_durations": durations})
    store.set_analysis(project_id, provider, packet)
    store.replace_scenes(project_id, scenes)
    store.update_job(job_id, stage="Generating storyboard images", total_items=len(scenes), completed=0)
    services = build_services(settings, mock=False)
    current = store.scenes(project_id)
    for index, scene in enumerate(current, 1):
        output = project_dir / "storyboard" / f"scene-{index:03d}.png"
        try:
            services.images.generate_scene_image(scene["prompt"], scene["dialogue"], output)
            scene["storyboard_path"] = str(output.relative_to(project_dir)).replace("\\", "/")
        except Exception as exc:
            scene["error"] = f"Storyboard image: {exc}"
        store.update_job(job_id, completed=index)
    # Updating generated preview paths must not invalidate the user's first editable revision.
    with store.connect() as db:
        for scene in current:
            db.execute("UPDATE scenes SET storyboard_path=?, error=? WHERE id=?", (scene.get("storyboard_path"), scene.get("error"), scene["id"]))
    store.update_job(job_id, status="complete", stage="Storyboard ready", completed=len(scenes))


def _timestamp_lines(words, vtt=False):
    def stamp(value):
        millis = int(round(value * 1000)); hours, rem = divmod(millis, 3600000); minutes, rem = divmod(rem, 60000); seconds, ms = divmod(rem, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{'.' if vtt else ','}{ms:03d}"
    chunks = [words[i:i + 6] for i in range(0, len(words), 6)]
    lines = ["WEBVTT", ""] if vtt else []
    for index, chunk in enumerate(chunks, 1):
        if not vtt: lines.append(str(index))
        lines.extend([f"{stamp(chunk[0].start)} --> {stamp(chunk[-1].end)}", " ".join(w.word for w in chunk), ""])
    return "\n".join(lines)


def _transcribe_with_fallback(settings, audio_path: Path):
    try:
        return DeepgramAudioProvider(settings).transcribe_word_timestamps(audio_path), "deepgram-nova-3"
    except Exception as deepgram_error:
        try:
            return GroqAudioProvider(settings).transcribe_word_timestamps(audio_path), f"groq-{settings.groq_transcription_model}"
        except Exception as groq_error:
            raise ProviderError(f"Caption transcription failed. Deepgram: {deepgram_error}; Groq: {groq_error}") from groq_error


def _declares_no_dialogue(scenes: list[dict]) -> bool:
    text = " ".join(scene.get("dialogue", "") for scene in scenes).strip().lower()
    return bool(text) and (text.startswith("none") or "no dialogue" in text or "no spoken" in text)


def generate_project(store: ProjectStore, project_id: str, job_id: str):
    project = store.get_project(project_id)
    if project["approved_revision"] is None or project["approved_revision"] != project["revision"]:
        raise ValueError("The current storyboard revision has not been approved.")
    settings = load_settings(project["brief"], max(1, math.ceil(project["duration_seconds"] / 60)))
    scenes, attachments = store.scenes(project_id), {a["id"]: a for a in store.attachments(project_id)}
    project_dir = store.project_dir(project_id)
    if project["workflow"] == "caption_existing":
        return caption_existing_project(store, project_id, job_id)
    provider = GeminiOmniVideoProvider(settings)
    store.update_status(project_id, "generating")
    store.update_job(job_id, status="running", stage="Generating Omni clips", total_items=len(scenes), completed=0)
    clip_paths = []
    for index, scene in enumerate(scenes, 1):
        existing = project_dir / scene["clip_path"] if scene.get("clip_path") else None
        if existing and existing.is_file() and existing.stat().st_size > 0:
            clip_paths.append(existing)
            store.update_job(job_id, completed=index, operation_id="resumed-existing-clip")
            continue
        refs = []
        for ref_id in scene["reference_ids"]:
            item = attachments.get(ref_id)
            if item and item["kind"] == "image": refs.append(project_dir / "uploads" / item["stored_name"])
        audio_direction = "No spoken dialogue; ambient sound only." if project["tts_override"] else f"Dialogue and sound: {scene['dialogue']}"
        prompt = f"In a single continuous shot lasting about {scene['duration_seconds']} seconds. {scene['prompt']} Camera: {scene['camera']} {audio_direction}"
        output = project_dir / "clips" / f"scene-{index:03d}.mp4"
        output, operation_id = provider.generate_clip(prompt, output, project["aspect_ratio"], project["resolution"], refs)
        clip_paths.append(output)
        with store.connect() as db:
            db.execute("UPDATE scenes SET clip_path=?, error=NULL WHERE id=?", (str(output.relative_to(project_dir)).replace("\\", "/"), scene["id"]))
        store.add_artifact(project_id, "clip", str(output.relative_to(project_dir)).replace("\\", "/"), f"Scene {index} clip")
        store.update_job(job_id, completed=index, operation_id=operation_id or "completed-inline")
    store.update_job(job_id, stage="Assembling clean video")
    clips = [VideoFileClip(str(path)) for path in clip_paths]
    replacement_audio = []
    if project["tts_override"]:
        store.update_job(job_id, stage="Generating Deepgram voiceover")
        voiced = []
        for index, (clip, scene) in enumerate(zip(clips, scenes), 1):
            result = DeepgramAudioProvider(settings).synthesize_with_timestamps(
                scene["dialogue"], project_dir / "voiceover" / f"scene-{index:03d}.wav",
                project_dir / "voiceover" / f"scene-{index:03d}.json")
            source_audio = AudioFileClip(str(result.audio_path))
            replacement_audio.append(source_audio)
            audio = source_audio.subclipped(0, min(clip.duration, source_audio.duration))
            voiced.append(clip.with_audio(audio))
        clips = voiced
    final = concatenate_videoclips(clips, method="compose")
    clean_path = project_dir / "final" / "video-clean.mp4"
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(str(clean_path), fps=24, codec="libx264", audio_codec="aac", logger=None)
    store.add_artifact(project_id, "video", "final/video-clean.mp4", "Clean video")
    audio_path = project_dir / "final" / "audio.mp3"
    if final.audio:
        final.audio.write_audiofile(str(audio_path), logger=None)
        store.add_artifact(project_id, "audio", "final/audio.mp3", "Audio track")
        store.update_job(job_id, stage="Transcribing and captioning")
        if _declares_no_dialogue(scenes):
            words, transcript_provider = [], "not-required-no-spoken-dialogue"
        else:
            words, transcript_provider = _transcribe_with_fallback(settings, audio_path)
        (project_dir / "final" / "captions.srt").write_text(_timestamp_lines(words), encoding="utf-8")
        (project_dir / "final" / "captions.vtt").write_text(_timestamp_lines(words, True), encoding="utf-8")
        (project_dir / "final" / "transcript.txt").write_text(" ".join(w.word for w in words), encoding="utf-8")
        for kind, filename, label in [("caption", "captions.srt", "SRT captions"), ("caption", "captions.vtt", "WebVTT captions"), ("transcript", "transcript.txt", "Transcript")]:
            store.add_artifact(project_id, kind, f"final/{filename}", label)
        store.add_artifact(project_id, "metadata", "final/transcription-provider.txt", "Caption provider")
        (project_dir / "final" / "transcription-provider.txt").write_text(transcript_provider, encoding="utf-8")
        subtitle_clips = build_dynamic_subtitle_clips(words, (final.w, final.h))
        captioned = CompositeVideoClip([final, *subtitle_clips], size=(final.w, final.h)).with_audio(final.audio)
        captioned_path = project_dir / "final" / "video-captioned.mp4"
        captioned.write_videofile(str(captioned_path), fps=24, codec="libx264", audio_codec="aac", logger=None)
        store.add_artifact(project_id, "video", "final/video-captioned.mp4", "Captioned video")
        captioned.close()
        for clip in subtitle_clips: clip.close()
    for clip in clips: clip.close()
    for audio in replacement_audio: audio.close()
    final.close()
    store.update_status(project_id, "complete")
    store.update_job(job_id, status="complete", stage="Complete", completed=len(scenes))


def caption_existing_project(store: ProjectStore, project_id: str, job_id: str):
    project, scenes = store.get_project(project_id), store.scenes(project_id)
    attachments = {item["id"]: item for item in store.attachments(project_id)}
    if not scenes or not scenes[0]["reference_ids"]:
        raise ValueError("No source video is attached to this caption project.")
    source = attachments[scenes[0]["reference_ids"][0]]
    if source["kind"] != "video":
        raise ValueError("The caption source is not a video.")
    project_dir = store.project_dir(project_id)
    source_path = project_dir / "uploads" / source["stored_name"]
    settings = load_settings(project["brief"], 1)
    store.update_status(project_id, "generating")
    store.update_job(job_id, status="running", stage="Extracting source audio", total_items=1)
    clip = VideoFileClip(str(source_path))
    if not clip.audio:
        raise ValueError("The uploaded video has no audio track to caption.")
    final_dir = project_dir / "final"; final_dir.mkdir(parents=True, exist_ok=True)
    audio_path = final_dir / "audio.mp3"; clip.audio.write_audiofile(str(audio_path), logger=None)
    words, transcript_provider = _transcribe_with_fallback(settings, audio_path)
    transcript = " ".join(item.word for item in words)
    corrected = scenes[0]["dialogue"].strip()
    if corrected and corrected != transcript:
        words = estimate_word_timestamps(corrected, clip.duration)
        transcript = corrected
    (final_dir / "captions.srt").write_text(_timestamp_lines(words), encoding="utf-8")
    (final_dir / "captions.vtt").write_text(_timestamp_lines(words, True), encoding="utf-8")
    (final_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
    subtitle_clips = build_dynamic_subtitle_clips(words, (clip.w, clip.h))
    captioned = CompositeVideoClip([clip, *subtitle_clips], size=(clip.w, clip.h)).with_audio(clip.audio)
    output = final_dir / "video-captioned.mp4"
    captioned.write_videofile(str(output), fps=clip.fps or 24, codec="libx264", audio_codec="aac", logger=None)
    store.add_artifact(project_id, "video", f"uploads/{source['stored_name']}", "Original video")
    for kind, rel, label in [("video", "final/video-captioned.mp4", "Captioned video"), ("audio", "final/audio.mp3", "Audio track"),
                             ("caption", "final/captions.srt", "SRT captions"), ("caption", "final/captions.vtt", "WebVTT captions"),
                             ("transcript", "final/transcript.txt", "Transcript")]: store.add_artifact(project_id, kind, rel, label)
    (final_dir / "transcription-provider.txt").write_text(transcript_provider, encoding="utf-8")
    store.add_artifact(project_id, "metadata", "final/transcription-provider.txt", "Caption provider")
    captioned.close(); clip.close()
    for item in subtitle_clips: item.close()
    store.update_status(project_id, "complete")
    store.update_job(job_id, status="complete", stage="Complete", completed=1)
