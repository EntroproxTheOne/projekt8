import argparse
from pathlib import Path

from video_pipeline.assembly import render_video
from video_pipeline.config import load_settings
from video_pipeline.manifest import RunPaths
from video_pipeline.pipeline import PipelineServices, generate_assets, generate_plan
from video_pipeline.providers.base import UnsupportedAudioProvider, UnsupportedImageProvider
from video_pipeline.providers.deepgram_audio import DeepgramAudioProvider
from video_pipeline.providers.gemini_audio import GeminiAudioProvider
from video_pipeline.providers.gemini_images import GeminiImageProvider
from video_pipeline.providers.gemini_llm import GeminiPlanner
from video_pipeline.providers.groq_audio import GroqAudioProvider
from video_pipeline.providers.grok_images import GrokImageProvider


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate faceless videos from an idea.")
    parser.add_argument("--idea", required=True)
    parser.add_argument("--duration-minutes", type=int, required=True)
    parser.add_argument("--audio-provider", choices=["deepgram", "groq", "gemini", "realtimetts", "inworld"], default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--generate-plan", action="store_true")
    parser.add_argument("--generate-assets", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use local fake providers for end-to-end testing without API keys.")
    return parser.parse_args(argv)


def build_services(settings, mock: bool = False):
    if mock:
        from video_pipeline.providers.mock import MockAudioProvider, MockImageProvider, MockPlanner

        return PipelineServices(planner=MockPlanner(), audio=MockAudioProvider(), images=MockImageProvider())
    groq_audio = GroqAudioProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_tts_model,
        voice=settings.groq_tts_voice,
        transcription_model=settings.groq_transcription_model,
        allow_estimated_timestamps=settings.allow_estimated_timestamps,
    )
    if settings.audio_provider == "deepgram":
        audio = DeepgramAudioProvider(
            api_key=settings.deepgram_api_key,
            model=settings.deepgram_tts_model,
            groq_api_key=settings.groq_api_key,
            transcription_model=settings.groq_transcription_model,
        )
    elif settings.audio_provider == "gemini":
        audio = GeminiAudioProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_tts_model,
            voice=settings.gemini_tts_voice,
            groq_api_key=settings.groq_api_key,
            transcription_model=settings.groq_transcription_model,
            allow_estimated_timestamps=settings.allow_estimated_timestamps,
        )
    elif settings.audio_provider == "groq":
        audio = groq_audio
    elif settings.audio_provider == "realtimetts":
        audio = UnsupportedAudioProvider("realtimetts", settings.realtime_tts_model)
    else:
        audio = UnsupportedAudioProvider("inworld", settings.inworld_tts_model)

    image_model = settings.resolved_image_model
    gemini_images = GeminiImageProvider(settings.gemini_api_key, settings.gemini_image_model)
    if image_model.startswith("gemini"):
        images = gemini_images
    elif image_model.startswith("grok"):
        images = GrokImageProvider(settings.grok_api_key, image_model)
    else:
        images = UnsupportedImageProvider("image", image_model)
    return PipelineServices(
        planner=GeminiPlanner(settings.gemini_api_key, settings.gemini_text_model),
        audio=audio,
        audio_fallback=groq_audio,
        images=images,
        image_fallback=gemini_images,
    )


def main(argv=None):
    args = parse_args(argv)
    settings = load_settings(args.idea, args.duration_minutes, args.audio_provider)
    services = build_services(settings, mock=args.mock)
    run_id = args.run_id
    if args.generate_plan or args.run_all:
        manifest = generate_plan(args.idea, args.duration_minutes, settings.audio_provider, Path(settings.output_dir), run_id, services)
        run_id = manifest.run_id
        print(f"Plan ready: {run_id}")
    if args.generate_assets or args.run_all:
        if not run_id:
            raise SystemExit("--run-id is required when generating assets without --generate-plan")
        generate_assets(Path(settings.output_dir), run_id, services)
        print(f"Assets ready: {run_id}")
    if args.render or args.run_all:
        if not run_id:
            raise SystemExit("--run-id is required when rendering without --generate-plan")
        output = render_video(RunPaths(Path(settings.output_dir), run_id), settings.video_width, settings.video_height)
        print(f"Rendered: {output}")
    if not any([args.generate_plan, args.generate_assets, args.render, args.run_all]):
        raise SystemExit("Choose --generate-plan, --generate-assets, --render, or --run-all")


if __name__ == "__main__":
    main()
