import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    idea: str
    duration_minutes: int
    audio_provider: str = "deepgram"
    image_provider: str = "grok"
    planner_provider: str = "gemini"
    output_dir: str = "outputs"
    video_width: int = 1080
    video_height: int = 1920
    network_timeout_seconds: int = 300
    gemini_api_key: str = ""
    groq_api_key: str = ""
    grok_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    openrouter_api_key: str = ""
    gemini_text_model: str = "gemini-3.1-flash-lite-preview"
    gemini_image_model: str = "gemini-3.1-flash-image-preview"
    gemini_tts_model: str = "gemini-3.1-flash-tts-preview"
    gemini_omni_model: str = "gemini-omni-1.1-flash"
    grok_image_model: str = "grok-imagine-image"
    deepgram_tts_model: str = "aura-2-asteria-en"
    groq_transcription_model: str = "whisper-large-v3"
    openrouter_text_model: str = "google/gemini-2.5-flash"
    openrouter_image_model: str = "bytedance-seed/seedream-4.5"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"


def load_settings(idea: str, duration_minutes: int, audio_provider: str | None = None) -> Settings:
    _load_dotenv()
    return Settings(
        idea=idea,
        duration_minutes=duration_minutes,
        audio_provider=audio_provider or os.getenv("AUDIO_PROVIDER", "deepgram"),
        image_provider=os.getenv("IMAGE_PROVIDER", "grok"),
        planner_provider=os.getenv("PLANNER_PROVIDER", "gemini"),
        output_dir=os.getenv("OUTPUT_DIR", "outputs"),
        video_width=int(os.getenv("VIDEO_WIDTH", "1080")),
        video_height=int(os.getenv("VIDEO_HEIGHT", "1920")),
        network_timeout_seconds=int(os.getenv("NETWORK_TIMEOUT_SECONDS", "300")),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        grok_api_key=os.getenv("GROK_API_KEY", ""),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        gemini_text_model=os.getenv("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite-preview"),
        gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"),
        gemini_tts_model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
        gemini_omni_model=os.getenv("GEMINI_OMNI_MODEL", "gemini-omni-1.1-flash"),
        grok_image_model=os.getenv("GROK_IMAGE_MODEL", "grok-imagine-image"),
        deepgram_tts_model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-asteria-en"),
        groq_transcription_model=os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3"),
        openrouter_text_model=os.getenv("OPENROUTER_TEXT_MODEL", "google/gemini-2.5-flash"),
        openrouter_image_model=os.getenv("OPENROUTER_IMAGE_MODEL", "bytedance-seed/seedream-4.5"),
        elevenlabs_tts_model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2"),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
    )
