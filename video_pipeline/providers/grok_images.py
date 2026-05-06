import base64
from pathlib import Path

import requests

from video_pipeline.providers.base import ProviderError


class GrokImageProvider:
    def __init__(self, api_key: str | None, model: str = "grok-imagine-image", timeout_seconds: int = 300) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        full_prompt = (
            f"{prompt}\n\nNarration context:\n{narration_context}\n\n"
            "Create a vertical 9:16 cinematic image suitable for a faceless YouTube video. "
            "Avoid text in the image unless explicitly requested."
        )
        return self._generate_image(full_prompt, output_path)

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self._generate_image(f"{prompt}\n\nCreate a high-contrast YouTube thumbnail image.", output_path)

    def _generate_image(self, prompt: str, output_path: Path) -> Path:
        if not self.api_key:
            raise ProviderError("GROK_API_KEY is required for Grok image generation")
        try:
            response = requests.post(
                "https://api.x.ai/v1/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "prompt": prompt, "aspect_ratio": "9:16"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(f"Grok image request timed out after {self.timeout_seconds} seconds") from exc
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Grok image request failed.{detail}") from exc

        item = (response.json().get("data") or [{}])[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("b64_json"):
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
            return output_path
        if item.get("url"):
            try:
                image_response = requests.get(item["url"], timeout=self.timeout_seconds)
                image_response.raise_for_status()
            except requests.RequestException as exc:
                raise ProviderError("Grok image URL download failed") from exc
            output_path.write_bytes(image_response.content)
            return output_path
        raise ProviderError("Grok image response did not contain image data")
