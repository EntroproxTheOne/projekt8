# Paragraph-Chunked Faceless Video Pipeline Design

## Goal

Build a standalone Python MVP for an automated faceless video generation pipeline. It accepts a video idea and target duration, generates a paragraph-based video plan, creates resumable audio/image/timestamp assets per paragraph, renders dynamic pop-out subtitles, and assembles a final MP4. A simple local webpage will exercise the same backend pipeline for testing.

## Scope

The MVP is a soft wrapper around external APIs and local rendering libraries. It prioritizes correctness, resumability, and modular provider boundaries over rendering speed.

Included:

- Command-line pipeline entrypoint.
- Lightweight FastAPI testing webpage.
- Groq-backed script/video-plan generation.
- Gemini-backed image generation.
- Selectable audio provider: Groq or Gemini.
- Paragraph-level artifact saving for rate-limit recovery.
- Dynamic subtitles using word-level timestamps.
- MoviePy-based Ken Burns image motion and final MP4 assembly.
- Tests for core planning, manifest, timestamp, and subtitle logic.

Not included:

- Production job queue.
- User authentication.
- Cloud storage.
- High-performance subtitle rendering optimization.
- Guaranteed provider-specific timestamp support if an API does not expose it.

## Inputs

The pipeline accepts:

- `video_idea`: topic or idea for the video.
- `target_duration_minutes`: integer from 1 to 60.
- `audio_provider`: `groq` or `gemini`.
- `output_dir`: base directory for generated runs.
- Optional `run_id`: lets a previous run resume.

Duration planning:

- Target word count: `target_duration_minutes * 150`.
- Suggested paragraph/scene count: mostly one scene per paragraph. The LLM should create enough paragraph scenes to roughly match the target duration while keeping each paragraph coherent.
- Historical image-count guidance remains useful as an upper bound: about `target_duration_minutes * 12`, but the MVP default is one image per paragraph unless the LLM splits a long idea into more scene beats.

## Output Layout

Each run writes to:

```text
outputs/<run_id>/
  manifest.json
  metadata.txt
  plan.json
  audio/
    wav_001.wav
    wav_002.wav
  timestamps/
    timestamps_001.json
    timestamps_002.json
  images/
    image_001.png
    image_002.png
    thumbnail.png
  final_output_video.mp4
```

The manifest records step completion, provider choices, asset paths, errors, and enough scene metadata to resume without regenerating completed work.

## LLM Plan Shape

Groq returns structured JSON:

```json
{
  "scenes": [
    {
      "paragraph_index": 1,
      "narration": "Exact spoken paragraph text.",
      "image_prompt": "Context-aware prompt for this paragraph."
    }
  ],
  "thumbnail_prompt": "YouTube thumbnail prompt.",
  "title_and_description": {
    "title": "SEO title",
    "description": "SEO description"
  }
}
```

The parser validates required fields, ensures scene order is stable, and rejects empty narration or image prompts.

## Provider Boundaries

Provider modules live behind small interfaces:

- `GroqPlanner.generate_video_plan(...)`
- `GroqAudioProvider.synthesize_with_timestamps(...)`
- `GeminiAudioProvider.synthesize_with_timestamps(...)`
- `GeminiImageProvider.generate_scene_image(...)`
- `GeminiImageProvider.generate_thumbnail(...)`

The pipeline should not know provider-specific HTTP details. Provider keys come from `.env`.

Expected environment variables:

- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `AUDIO_PROVIDER`
- Optional model overrides, such as `GROQ_LLM_MODEL`, `GROQ_TTS_MODEL`, `GEMINI_IMAGE_MODEL`, and `GEMINI_TTS_MODEL`.

## Audio And Timestamp Rules

Each scene is synthesized independently:

- `audio/wav_001.wav`
- `timestamps/timestamps_001.json`

The audio provider must supply word-level timestamps or a reliable equivalent. If timestamps are missing for a scene, the pipeline marks that scene as failed and stops before final render. Previously completed scene assets remain usable on rerun.

During assembly, per-scene timestamps are offset by the cumulative duration of previous audio files so subtitles align with the full timeline.

## Image Rules

Gemini generates:

- One contextual scene image per paragraph by default.
- One thumbnail image from `thumbnail_prompt`.

Scene image generation uses the paragraph narration and image prompt so the visual reflects local context rather than a generic global topic. Character/style consistency parameters should be passed through when supported by the Gemini image API.

## Subtitle Behavior

The subtitle engine parses word-level timestamps and creates dynamic overlays:

- The active spoken word is highlighted yellow.
- The active word is scaled by about 20-30%.
- Surrounding words remain readable in white.
- Text appears center-bottom.
- Subtitle groups should be short enough to fit mobile and desktop video frames.

The initial MVP can use MoviePy `TextClip` composition even if it is slower.

## Assembly

MoviePy assembles the final video:

- Load scene images in order.
- Match each image clip duration to its corresponding audio chunk duration.
- Apply slow Ken Burns zoom or pan to each static image.
- Concatenate image clips.
- Concatenate audio chunks.
- Overlay dynamic subtitle clips.
- Render `final_output_video.mp4`.

The final video resolution defaults to vertical 1080x1920 for Shorts-style content, while still allowing configuration for other formats later.

## Testing Webpage

Add a local FastAPI app for manual testing:

- Form fields: idea, target duration, audio provider, optional run id.
- Actions: generate plan, generate assets, render video, run all.
- Status table: one row per paragraph showing plan, audio, timestamps, image, and errors.
- Preview area: metadata, generated images, and final video when available.

The webpage calls the same Python service functions as the CLI.

## Error Handling And Resumability

All provider calls should have:

- Timeouts.
- Clear exception messages.
- Scene-level failure recording in `manifest.json`.
- Skip logic for already completed files.

Rerunning with the same `run_id` should continue from missing or failed assets without replacing completed assets unless explicitly requested later.

## Testing Strategy

Core tests should cover:

- Duration and planning calculations.
- LLM JSON validation.
- Manifest creation and resume decisions.
- Timestamp validation and global offsetting.
- Subtitle grouping and active-word detection.
- Asset path generation.

Provider calls are tested with fake provider implementations so tests do not require paid APIs.

## Open Assumptions

- The project will start as a new standalone Python package in the current empty folder.
- The first real render path uses MoviePy for speed of implementation, not best possible render performance.
- If Groq or Gemini audio cannot provide word-level timestamps directly, that provider will fail for the MVP until a timestamp-capable alternative or alignment step is added.
