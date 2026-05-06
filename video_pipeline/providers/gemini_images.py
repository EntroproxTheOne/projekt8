import base64
from pathlib import Path

import requests

from video_pipeline.providers.base import ProviderError


class GeminiImageProvider:
    def __init__(self, api_key: str | None, model: str = "gemini-2.5-flash-image", timeout_seconds: int = 300) -> None:
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
            raise ProviderError("GEMINI_API_KEY is required for image generation")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise ProviderError(f"Gemini image request timed out after {self.timeout_seconds} seconds") from exc
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                detail = f" Status {getattr(response, 'status_code', 'unknown')}: {getattr(response, 'text', '')[:500]}"
            raise ProviderError(f"Gemini image request failed.{detail}") from exc
        inline_data = self._extract_inline_image(response.json())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(inline_data["data"]))
        return output_path

    def _extract_inline_image(self, payload: dict) -> dict:
        try:
            parts = payload["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise ProviderError("Gemini image response did not contain image parts") from exc
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            mime_type = (inline_data or {}).get("mimeType", "")
            if inline_data and inline_data.get("data") and mime_type.startswith("image/"):
                return inline_data
        raise ProviderError("Gemini image response did not contain inline image data")
