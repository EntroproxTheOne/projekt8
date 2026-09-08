# All-In-One Media Orchestrator

Python 3.11 soft-wrapper MVP for faceless video generation and multi-modal media workflows.

## Run

```powershell
py -3.11 -m uvicorn video_pipeline.webapp:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

## Environment

Create `.env` with any providers you want to use:

```text
GEMINI_API_KEY=
GROQ_API_KEY=
GROK_API_KEY=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
OPENROUTER_API_KEY=
```

Defaults are provider-ready but the web tester can also use mock providers.

## CLI Examples

```powershell
py -3.11 -m run_pipeline --idea "Why people procrastinate" --duration-minutes 1 --run-all --mock
py -3.11 -m run_pipeline --idea "resume" --duration-minutes 1 --run-id <run_id> --render
```

## Video workspace

The homepage creates persistent video projects with a staged workflow:

1. Enter a brief and optionally attach images, audio, video, or PDFs. Upload progress and validation are shown in the workspace.
2. Projekt8 stores source files locally and analyzes them with Gemini, then Groq and Grok fallbacks.
3. Review and edit descriptions, dialogue, camera direction, source references, prompts, timing, and scene order. Video generation is server-blocked until the current revision is approved.
4. Gemini Omni Flash creates real 3–10 second clips, which are assembled into clean and captioned videos with separate audio, transcript, SRT, and VTT downloads.

`outputs/projekt8.sqlite3` contains project metadata. Source and generated files are under `outputs/projects/<project_id>/`.

The configured Gemini account must expose `gemini-omni-1.1-flash`. Deepgram transcription falls back to Groq; invalid credentials are shown in the project instead of producing fake media.

## What Is Implemented

- Mixed-source video projects, editable scene plans, revision approval, real Omni clips, native audio, captions, and MP4 assembly.
- Sequential scene assets for rate-limit friendliness.
- Provider fallback hooks.
- All-in-one orchestrator foundation with DAG steps, artifacts, retries, provider locks, costs, and resume manifests.
- Provider-ready adapters for Gemini, Groq, Grok, Deepgram, ElevenLabs, OpenRouter, and local privacy/vision utilities.
- SQLite project/job/artifact persistence plus the legacy pipeline builder, gallery, settings, prompt packs, and privacy tools.

## Studio UI and current status

Projekt8 now groups creation into Studio, 3D Studio, Presentation Studio, and Markup Studio. See [current status](docs/current-status.md) for verified features and remaining integrations. Run `python serve.py` to use the bundled dependencies.
