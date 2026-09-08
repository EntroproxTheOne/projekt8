import base64
from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.providers.base import ProviderError


class GrokImageProvider:
    provider_name = "grok-image"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        return self._generate(f"{prompt}\nNarration context: {narration_context}", output_path)

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self._generate(f"High-retention YouTube thumbnail: {prompt}", output_path)

    def _generate(self, prompt: str, output_path: Path) -> Path:
        if not self.settings.grok_api_key:
            raise ProviderError("GROK_API_KEY is required for Grok image generation.")
        response = requests.post(
            "https://api.x.ai/v1/images/generations",
            headers={"Authorization": f"Bearer {self.settings.grok_api_key}", "Content-Type": "application/json"},
            json={"model": self.settings.grok_image_model, "prompt": prompt, "n": 1},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Grok image failed: {response.text[:500]}")
        data = response.json().get("data", [])
        if not data:
            raise ProviderError("Grok image response did not include data.")
        item = data[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("b64_json"):
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
            return output_path
        if item.get("url"):
            image = requests.get(item["url"], timeout=self.settings.network_timeout_seconds)
            image.raise_for_status()
            output_path.write_bytes(image.content)
            return output_path
        raise ProviderError("Grok image response did not include url or b64_json.")
