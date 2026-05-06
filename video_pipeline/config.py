import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    video_idea: str
    target_duration_minutes: int
    audio_provider: str = "deepgram"
    output_dir: str = "outputs"
    groq_api_key: str | None = None
    grok_api_key: str | None = None
    gemini_api_key: str | None = None
    deepgram_api_key: str | None = None
    groq_llm_model: str = "llama-3.3-70b-versatile"
    gemini_text_model: str = "gemini-3.1-flash-lite-preview"
    groq_tts_model: str = "playai-tts"
    groq_tts_voice: str = "Fritz-PlayAI"
    groq_transcription_model: str = "whisper-large-v3"
    deepgram_tts_model: str = "aura-2-asteria-en"
    image_model_tier: str = "cheap"
    image_model_choice: str = "grok-imagine-image"
    gemini_image_model: str = "gemini-3.1-flash-image-preview"
    gemini_tts_model: str = "gemini-3.1-flash-tts-preview"
    gemini_tts_voice: str = "Kore"
    realtime_tts_model: str = "realtimetts-1.5-mini"
    inworld_tts_model: str = "inworld-realtime-tts-1.5max"
    allow_estimated_timestamps: bool = True
    video_width: int = 1080
    video_height: int = 1920

    def __post_init__(self) -> None:
        if not self.video_idea.strip():
            raise ValueError("video_idea is required")
        if not 1 <= self.target_duration_minutes <= 60:
            raise ValueError("target_duration_minutes must be between 1 and 60")
        if self.audio_provider not in {"deepgram", "groq", "gemini", "realtimetts", "inworld"}:
            raise ValueError("audio_provider must be 'deepgram', 'groq', 'gemini', 'realtimetts', or 'inworld'")
        if self.image_model_tier not in {"cheap", "pro"}:
            raise ValueError("image_model_tier must be 'cheap' or 'pro'")

    @property
    def image_model_options(self) -> dict[str, list[str]]:
        return {
            "cheap": ["grok-imagine-image"],
            "pro": ["gemini-3.1-flash-image-preview"],
        }

    @property
    def audio_model_options(self) -> dict[str, list[str]]:
        return {
            "cheap": [
                "aura-2-asteria-en",
                "aura-2-zeus-en",
                "gemini-3.1-flash-tts-preview",
                "realtimetts-1.5-mini",
                "inworld-realtime-tts-1.5max",
            ],
        }

    @property
    def resolved_image_model(self) -> str:
        if self.image_model_tier == "pro":
            return self.gemini_image_model
        return self.image_model_choice

    @property
    def target_word_count(self) -> int:
        return self.target_duration_minutes * 150

    @property
    def suggested_image_count(self) -> int:
        return self.target_duration_minutes * 12


def load_settings(video_idea: str, target_duration_minutes: int, audio_provider: str | None = None) -> Settings:
    load_dotenv()
    return Settings(
        video_idea=video_idea,
        target_duration_minutes=target_duration_minutes,
        audio_provider=audio_provider or os.getenv("AUDIO_PROVIDER", "deepgram"),
        output_dir=os.getenv("OUTPUT_DIR", "outputs"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        grok_api_key=os.getenv("GROK_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY"),
        groq_llm_model=os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"),
        gemini_text_model=os.getenv("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite-preview"),
        groq_tts_model=os.getenv("GROQ_TTS_MODEL", "playai-tts"),
        groq_tts_voice=os.getenv("GROQ_TTS_VOICE", "Fritz-PlayAI"),
        groq_transcription_model=os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3"),
        deepgram_tts_model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-asteria-en"),
        image_model_tier=os.getenv("IMAGE_MODEL_TIER", "cheap"),
        image_model_choice=os.getenv("IMAGE_MODEL_CHOICE", "grok-imagine-image"),
        gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"),
        gemini_tts_model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
        gemini_tts_voice=os.getenv("GEMINI_TTS_VOICE", "Kore"),
        realtime_tts_model=os.getenv("REALTIMETTS_MODEL", "realtimetts-1.5-mini"),
        inworld_tts_model=os.getenv("INWORLD_TTS_MODEL", "inworld-realtime-tts-1.5max"),
        allow_estimated_timestamps=_as_bool(os.getenv("ALLOW_ESTIMATED_TIMESTAMPS"), True),
        video_width=int(os.getenv("VIDEO_WIDTH", "1080")),
        video_height=int(os.getenv("VIDEO_HEIGHT", "1920")),
    )
