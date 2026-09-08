import argparse
from pathlib import Path

from video_pipeline.assembly import render_video
from video_pipeline.config import Settings, load_settings
from video_pipeline.manifest import RunPaths
from video_pipeline.pipeline import PipelineServices, generate_assets, generate_plan
from video_pipeline.providers.deepgram_audio import DeepgramAudioProvider
from video_pipeline.providers.elevenlabs import ElevenLabsProvider
from video_pipeline.providers.gemini_audio import GeminiAudioProvider
from video_pipeline.providers.gemini_images import GeminiImageProvider
from video_pipeline.providers.gemini_llm import GeminiPlannerProvider
from video_pipeline.providers.groq_audio import GroqAudioProvider
from video_pipeline.providers.grok_images import GrokImageProvider
from video_pipeline.providers.mock import MockAudioProvider, MockImageProvider, MockPlannerProvider


def build_services(settings: Settings, mock: bool = False) -> PipelineServices:
    if mock:
        return PipelineServices(
            planner=MockPlannerProvider(),
            audio=MockAudioProvider(),
            images=MockImageProvider(),
            audio_fallback=MockAudioProvider(),
            image_fallback=MockImageProvider(),
        )

    planner = GeminiPlannerProvider(settings)
    image_fallback = GeminiImageProvider(settings)
    images = GrokImageProvider(settings) if settings.image_provider == "grok" else image_fallback

    groq_audio = GroqAudioProvider(settings)
    if settings.audio_provider == "elevenlabs":
        audio = ElevenLabsProvider(settings, alignment_fallback=groq_audio)
    elif settings.audio_provider == "gemini":
        audio = GeminiAudioProvider(settings, transcription_fallback=groq_audio)
    elif settings.audio_provider == "groq":
        audio = groq_audio
    else:
        audio = DeepgramAudioProvider(settings, transcription_fallback=groq_audio)

    return PipelineServices(
        planner=planner,
        audio=audio,
        images=images,
        audio_fallback=groq_audio,
        image_fallback=image_fallback,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea", required=True)
    parser.add_argument("--duration-minutes", type=int, required=True)
    parser.add_argument("--audio-provider", default="deepgram")
    parser.add_argument("--run-id")
    parser.add_argument("--generate-plan", action="store_true")
    parser.add_argument("--generate-assets", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    settings = load_settings(args.idea, args.duration_minutes, args.audio_provider)
    services = build_services(settings, mock=args.mock)
    run_id = args.run_id

    if args.generate_plan or args.run_all:
        manifest = generate_plan(
            args.idea,
            args.duration_minutes,
            settings.audio_provider,
            Path(settings.output_dir),
            run_id,
            services,
        )
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
