import json
import re

import requests

from video_pipeline.config import Settings
from video_pipeline.models import VideoPlan
from video_pipeline.prompt_packs import SCRIPT_AGENT
from video_pipeline.providers.base import ProviderError


class GeminiPlannerProvider:
    provider_name = "gemini-planner"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_video_plan(self, idea: str, target_word_count: int, target_image_count: int) -> VideoPlan:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini planning.")
        scene_count = max(1, min(2, target_image_count))
        prompt = f"""
{SCRIPT_AGENT.render()}

Create a faceless video plan for:
{idea}

Target spoken words: about {target_word_count}.
Target image count requested: {target_image_count}.
For this MVP return exactly {scene_count} scene objects.

Return strict JSON:
{{
  "script": "full spoken narration",
  "image_prompts": ["visual prompt"],
  "thumbnail_prompt": "thumbnail prompt",
  "title_and_description": {{"title": "SEO title", "description": "SEO description"}}
}}
"""
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_text_model}:generateContent"
        )
        response = requests.post(
            url,
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Gemini planner failed: {response.text[:500]}")
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = _parse_json(text)
        script = data.get("script", "")
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", script) if part.strip()]
        if len(paragraphs) < scene_count:
            sentences = re.split(r"(?<=[.!?])\s+", script)
            midpoint = max(1, len(sentences) // scene_count)
            paragraphs = [" ".join(sentences[index:index + midpoint]) for index in range(0, len(sentences), midpoint)]
        image_prompts = data.get("image_prompts") or []
        scenes = []
        for index in range(scene_count):
            narration = paragraphs[index] if index < len(paragraphs) else script
            image_prompt = image_prompts[index] if index < len(image_prompts) else f"Cinematic faceless visual for {idea}"
            scenes.append({"paragraph_index": index + 1, "narration": narration, "image_prompt": image_prompt})
        return VideoPlan(
            scenes=scenes,
            thumbnail_prompt=data.get("thumbnail_prompt", f"YouTube thumbnail about {idea}"),
            title_and_description=data.get(
                "title_and_description",
                {"title": idea, "description": f"A faceless video about {idea}."},
            ),
        )


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)
