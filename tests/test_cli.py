from run_pipeline import parse_args
from run_pipeline import build_services
from video_pipeline.config import Settings
from video_pipeline.providers.gemini_audio import GeminiAudioProvider
from video_pipeline.providers.gemini_images import GeminiImageProvider
from video_pipeline.providers.gemini_llm import GeminiPlanner
from video_pipeline.providers.deepgram_audio import DeepgramAudioProvider
from video_pipeline.providers.grok_images import GrokImageProvider


def test_parse_args_accepts_run_all():
    args = parse_args(["--idea", "AI myths", "--duration-minutes", "2", "--run-all", "--audio-provider", "gemini", "--mock"])

    assert args.idea == "AI myths"
    assert args.duration_minutes == 2
    assert args.run_all is True
    assert args.audio_provider == "gemini"
    assert args.mock is True


def test_build_services_defaults_to_gemini_only():
    settings = Settings(
        video_idea="AI myths",
        target_duration_minutes=1,
        gemini_api_key="gemini-key",
        audio_provider="gemini",
        image_model_tier="pro",
    )

    services = build_services(settings)

    assert isinstance(services.planner, GeminiPlanner)
    assert isinstance(services.audio, GeminiAudioProvider)
    assert isinstance(services.images, GeminiImageProvider)


def test_build_services_defaults_to_deepgram_and_grok_with_fallbacks():
    settings = Settings(
        video_idea="AI myths",
        target_duration_minutes=1,
        gemini_api_key="gemini-key",
        deepgram_api_key="deepgram-key",
        grok_api_key="grok-key",
        groq_api_key="groq-key",
    )

    services = build_services(settings)

    assert isinstance(services.planner, GeminiPlanner)
    assert isinstance(services.audio, DeepgramAudioProvider)
    assert isinstance(services.audio_fallback, type(services.audio_fallback))
    assert isinstance(services.images, GrokImageProvider)
    assert isinstance(services.image_fallback, GeminiImageProvider)
