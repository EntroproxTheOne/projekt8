# Projekt8 current status

## Verified

- The primary workspace accepts a video brief plus optional image, audio, video, and PDF sources. It supports new-video generation and captioning existing footage.
- Projects, attachments, analysis packets, storyboard revisions, approvals, background jobs, and artifacts persist in SQLite. Uploaded and generated files remain on local disk.
- Analysis uses Gemini, Groq, then Grok fallback. Provider failures and incomplete source processing are recorded instead of silently dropping inputs.
- Target duration is divided into 3–10 second scenes, targeting eight seconds. A 60-second project produces eight 7.5-second scenes.
- Storyboards expose editable scene description, dialogue, camera direction, duration, source references, and Omni prompt. Adding, deleting, reordering, editing, or regenerating a scene invalidates approval.
- Mixed-source uploads show byte progress, enforce per-file and project-size limits, and reject empty or extension-disguised media before it reaches a provider.
- Server-side approval enforcement prevents generation from an unapproved or stale storyboard revision.
- `gemini-omni-1.1-flash` generates real video clips with native audio. Completed clips are reused during retries so paid requests are not repeated.
- The final stage exports the source clips, clean MP4, captioned MP4, audio, transcript, SRT, VTT, analysis packet, and caption-provider metadata.
- Legacy demo runs remain available in the gallery and are identified as synthetic demo assets.
- 27 automated tests pass, including disguised-upload rejection, scene resequencing, and provider-error credential redaction.

## Live acceptance run

Project `51f03930c863` completed one approved 3-second Gemini Omni scene. Inspection confirmed a 3.01-second 640×360 video at 24 fps, changing frames, and a non-silent native audio track. The project page exposes all expected downloads.

The configured Gemini credential can list `gemini-omni-1.1-flash`. The configured Deepgram credential returns `INVALID_AUTH`; the configured Groq credential returns `expired_api_key`. The no-dialogue acceptance scene correctly bypassed transcription and generated empty caption files. Projects containing speech will retain their clean video and report caption transcription failure until one transcription credential is replaced.

## Remaining integration limits

- Gemini Omni currently does not accept raw audio references. Uploaded audio is transcribed for planning instead.
- Video references are constrained by the provider API. Projekt8 uses their extracted frames and transcripts during planning; image references can be passed directly to generation.
- Deepgram TTS voiceover requires a valid Deepgram credential.
- PDF extraction requires the installed `pypdf` dependency.
