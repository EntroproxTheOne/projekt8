# Paragraph Video Pipeline MVP

Standalone Python 3.11 backend for generating paragraph-chunked faceless videos with resumable audio, timestamps, images, dynamic subtitles, and a simple local testing webpage.

## Setup

Install dependencies directly into Python 3.11:

```powershell
py -3.11 -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in keys:

```text
GROQ_API_KEY=
GROK_API_KEY=
GEMINI_API_KEY=
DEEPGRAM_API_KEY=
```

Model tier notes:

```text
Primary image choice: grok-imagine-image
Image fallback: gemini-3.1-flash-image-preview
Primary audio choices: aura-2-asteria-en, aura-2-zeus-en
Audio fallback: Groq TTS with whisper-large-v3 transcription
```

## CLI

Mock end-to-end run without API keys:

```powershell
py -3.11 run_pipeline.py --idea "A short history of AI" --duration-minutes 1 --run-all --mock
```

Real provider run:

```powershell
py -3.11 run_pipeline.py --idea "Your topic" --duration-minutes 1 --run-all --audio-provider deepgram
```

Use `--run-id <id>` with `--generate-assets` or `--render` to resume a saved run.

## Web Tester

```powershell
py -3.11 -m uvicorn video_pipeline.webapp:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Output Layout

```text
outputs/<run_id>/
  manifest.json
  plan.json
  metadata.txt
  audio/wav_001.wav
  timestamps/timestamps_001.json
  images/image_001.png
  images/thumbnail.png
  final_output_video.mp4
```

Each paragraph scene is saved independently so rate limits or failures can be resumed without regenerating completed chunks.
