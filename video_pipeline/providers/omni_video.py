import base64
from pathlib import Path

import requests

from video_pipeline.config import Settings
from video_pipeline.providers.base import ProviderError


class GeminiOmniVideoProvider:
    provider_name = "gemini-omni"

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_clip(self, prompt: str, output_path: Path, aspect_ratio: str = "9:16", resolution: str = "720p", references: list[Path] | None = None) -> tuple[Path, str | None]:
        if not self.settings.gemini_api_key:
            raise ProviderError("GEMINI_API_KEY is required for Gemini Omni video generation.")
        inputs = []
        for path in (references or [])[:4]:
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                inputs.append({"type": "image", "data": base64.b64encode(path.read_bytes()).decode(), "mime_type": mime})
        inputs.append({"type": "text", "text": prompt})
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            json={"model": self.settings.gemini_omni_model, "input": inputs,
                  "response_format": {"type": "video", "aspect_ratio": aspect_ratio, "resolution": resolution}},
            timeout=max(600, self.settings.network_timeout_seconds),
        )
        if response.status_code >= 400:
            raise ProviderError(f"Gemini Omni failed: {response.text[:800]}")
        payload = response.json()
        video = None
        for step in payload.get("steps", []):
            for item in step.get("content", []):
                if item.get("type") == "video":
                    video = item
        if not video and payload.get("output_video"):
            video = payload["output_video"]
        if not video:
            raise ProviderError(f"Gemini Omni returned no video: {str(payload)[:800]}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if video.get("data"):
            output_path.write_bytes(base64.b64decode(video["data"]))
        elif video.get("uri"):
            download = requests.get(video["uri"], timeout=self.settings.network_timeout_seconds)
            download.raise_for_status()
            output_path.write_bytes(download.content)
        else:
            raise ProviderError("Gemini Omni video output had neither inline data nor a URI.")
        return output_path, payload.get("id")
