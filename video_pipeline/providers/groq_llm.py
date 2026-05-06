import json

import requests

from video_pipeline.models import VideoPlan
from video_pipeline.planning import build_planner_prompt, parse_video_plan
from video_pipeline.providers.base import ProviderError


class GroqPlanner:
    def __init__(self, api_key: str | None, model: str, timeout_seconds: int = 300) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is required for plan generation")
        prompt = build_planner_prompt(idea, target_word_count, suggested_image_count)
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Groq plan request failed.{detail}") from exc
        return self.parse_response(response.json())

    def parse_response(self, payload: dict) -> VideoPlan:
        try:
            content = payload["choices"][0]["message"]["content"]
            return parse_video_plan(json.loads(content))
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"Groq plan response was invalid: {exc}") from exc
