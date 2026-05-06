import json
import re

import requests

from video_pipeline.models import VideoPlan
from video_pipeline.planning import build_planner_prompt, parse_video_plan
from video_pipeline.providers.base import ProviderError


class GeminiPlanner:
    def __init__(self, api_key: str | None, model: str = "gemini-3.1-flash-lite-preview", timeout_seconds: int = 300) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini story and script generation")
        prompt = build_planner_prompt(idea, target_word_count, suggested_image_count)
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Gemini plan request failed.{detail}") from exc
        return self.parse_response(response.json())

    def parse_response(self, payload: dict) -> VideoPlan:
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
            text = _strip_json_fence(text)
            return parse_video_plan(json.loads(text))
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"Gemini plan response was invalid: {exc}") from exc


def _strip_json_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text
