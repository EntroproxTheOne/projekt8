# Markup Studio

A Projekt8-native implementation of the screenshot-to-code workflow, informed by https://github.com/abi/screenshot-to-code (MIT; copyright 2023 Abi Raja).

Reviewed upstream README, LICENSE, backend/prompts/message_builder.py and backend/prompts/system_prompt.py on 2026-09-05. No upstream source or prompt text was copied into this implementation. If upstream code is incorporated later, retain the applicable MIT copyright and permission notice with that code; visual similarity is not the license test.

## MVP

- Choose or drop a PNG, JPEG, or WebP screenshot, up to 8 MB and 20 million pixels.
- Local image preview with removal/replacement.
- Generate a single editable HTML + CSS page with Gemini. The server normalizes images to PNG, strips metadata by re-encoding, and resizes to at most 2048 pixels per side.
- Edit returned code, refresh its sandboxed preview, and download HTML.
- Preview disables scripts, navigation links, forms, and remote resources. Export contains the generated/edited source; it is not the sanitized preview document.
- The upload and generated code are held in memory and not persisted on the server.

Set GEMINI_API_KEY and, optionally, GEMINI_TEXT_MODEL in the server .env, then restart the server. The generation button sends the selected image to Gemini; selecting a file alone does not.

This is a single-model, single-page MVP, not upstream's multi-model agent, iterative visual evaluation, asset extraction, React/Vue exporter, or video reconstruction. Missing provider credentials produce a visible setup error rather than a pretend result.

Validation: file rejection, missing-key handling, successful response wiring, image/text request construction, truncation rejection, and completed-video card selection are tested with local fixtures. Live model quality is not verified without credentials.
