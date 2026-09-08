import base64
from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.providers.base import ProviderError


class GeminiImageProvider:
    provider_name = "gemini-image"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        full_prompt = f"{prompt}\n\nNarration context: {narration_context}\nVertical cinematic 9:16 frame."
        return self._generate(full_prompt, output_path)

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self._generate(f"YouTube thumbnail, bold readable concept: {prompt}", output_path)

    def _generate(self, prompt: str, output_path: Path) -> Path:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini image generation.")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_image_model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        response = requests.post(url, headers={"x-goog-api-key": self.settings.gemini_api_key}, json=payload, timeout=self.settings.network_timeout_seconds)
        if response.status_code >= 400:
            raise ProviderError(f"Gemini image failed: {response.text[:500]}")
        for candidate in response.json().get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(base64.b64decode(inline["data"]))
                    return output_path
        raise ProviderError("Gemini image response did not include image bytes.")
