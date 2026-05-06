import json
from typing import Any

from pydantic import ValidationError

from video_pipeline.models import VideoPlan


def build_planner_prompt(video_idea: str, target_word_count: int, suggested_image_count: int) -> str:
    return f"""
You are generating a paragraph-chunked faceless video plan.
Topic: {video_idea}
Target narration length: about {target_word_count} words.
Visual guidance: do not exceed about {suggested_image_count} images unless the story needs it.

Fixed agentic writing prompt for the first script generation:
- Write a human, real sounding essay voiceover, not AI-written content.
- Sound like a thoughtful person telling the story out loud, with lived-in phrasing and natural contractions.
- Use short pauses by inserting light punctuation and paragraph breaks where a narrator would breathe.
- Avoid robotic signposting, generic motivational language, corporate phrasing, and listicle rhythm.
- Prefer concrete images, small observations, tension, curiosity, and clean transitions.
- Keep sentences varied: some short and intimate, some longer and reflective.
- Make every paragraph feel spoken, cinematic, and emotionally grounded.
- The narration must be exact spoken text, ready for TTS, with no stage directions.

Return strict JSON only with this schema:
{{
  "scenes": [
    {{
      "paragraph_index": 1,
      "narration": "Exact spoken paragraph text.",
      "image_prompt": "Detailed image prompt for this paragraph."
    }}
  ],
  "thumbnail_prompt": "A YouTube thumbnail prompt.",
  "title_and_description": {{
    "title": "SEO title",
    "description": "SEO description"
  }}
}}

Rules:
- Each scene maps to one paragraph, one audio chunk, and mostly one image.
- Keep narration natural for voiceover.
- Image prompts must understand the local paragraph context.
- Use paragraph_index values starting at 1 with no gaps.
""".strip()


def parse_video_plan(payload: dict[str, Any] | str) -> VideoPlan:
    if isinstance(payload, str):
        payload = json.loads(payload)
    try:
        return VideoPlan.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
