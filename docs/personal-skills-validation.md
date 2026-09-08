# Personal skills validation — 2026-09-07

Installed in `C:/Users/masoo/.codex/skills`: intentional-ui-security, natural-specific-writing, and ui-style-references. All three passed the bundled skill validator. Their UI metadata parses, automatic discovery is enabled, and all relative reference links resolve. The refreshed session skill catalog lists all three.

## Representative scenario review

These are author-performed tabletop applications of the completed guidance, not independent agent evaluations or browser-tested implementations.

### Responsive UI

Request: Improve a server-rendered upload workspace while keeping its purple brand and existing stack.

Applied result: Retain the purple accent and HTML/CSS stack; give the upload action visual priority, associate a text label with the file input, retain the filename after recoverable failure, expose upload status, and stack preview and controls on narrow screens. Check keyboard focus, long filenames, contrast, and reduced motion. Do not add React, fabricated customer proof, or an unrelated full security audit.

Assessment: The guidance preserves the user's visual preference and scope while producing concrete usability checks. Rendering remains an implementation-time check.

### Security review

Hypothetical fixture: An authenticated artifact download handler returns `artifacts[id]` without comparing the artifact owner with the current user. The interface hides other users' download buttons.

Applied result: Flag a potential object-authorization defect at the handler. Confirm with two controlled accounts: owner access should succeed and another user's request for the same ID should fail. If cross-user access is observed for private artifacts, report the evidence and impact, add a server-side ownership check, and verify both cases. With no reproduction or deployment context, label the concern unverified rather than inventing a proven exploit or severity score. Do not scan an external service.

Assessment: The workflow distinguishes an actual server boundary from UI appearance, requires evidence and regression verification, and preserves review-only scope. No audit of Projekt8 was performed.

### Prose rewrite

Input: “We are thrilled to announce our revolutionary export feature. Local tests pass, but live provider integration has not been checked.”

Applied result: “Export is implemented and the local tests pass. The live provider integration still needs verification.”

Assessment: Removes unsupported praise while retaining the limitation. No invented metrics, anecdotes, or detector claims. A technical instruction would retain its required sequence rather than adopt nonlinear fiction advice.

### Reference-led design

Request: Add a distinctive animated hover treatment to a plain HTML/CSS site using the video references.

Applied result: Use the verified Vengeance UI site as visual inspiration and implement a small original CSS treatment in the existing stack. Provide an equivalent focus state, preserve the link's function, and remove decorative motion under reduced-motion preferences. If copying component source instead, inspect its MIT notice and dependencies. Do not install an unidentified Animaster library or treat Skiper's public demos as unrestricted source.

Assessment: Reference selection, compatibility, reuse rights, and interaction checks are explicit. No third-party component code was copied.

## Server smoke test

The supplied `.env` was copied from the Desktop project folder to the OneDrive application folder; the original remains. Only key-presence booleans were inspected. Gemini, Grok, Deepgram, and Groq are populated; ElevenLabs and OpenRouter are blank. No paid provider requests were made.

The server runs at `http://127.0.0.1:8000/`. The main Studio, 3D, Presentation, and Markup routes returned HTTP 200, as did provider settings. The app browser open request was queued successfully. These checks establish local page availability, not live generation or visual correctness.

## Reference limits

All five videos were reviewed through approximately two-second frame samples and selected enlarged images. The audio narration was not transcribed; the installed notes distinguish visible captions from unverified narration. One library identity remains unresolved and is excluded from code-reuse recommendations. Official source links and license distinctions are included in the skill references. The writing research is treated as fiction-specific evidence, not a universal authorship detector.
