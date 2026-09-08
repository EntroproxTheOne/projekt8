import base64
import json
from pathlib import Path
from typing import Any

import requests

from video_pipeline.config import Settings
from video_pipeline.providers.base import ProviderError


class OpenRouterProvider:
    provider_name = "openrouter"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        if not self.settings.openrouter_api_key:
            raise ProviderError("OPENROUTER_API_KEY is required for OpenRouter.")
        return {"Authorization": f"Bearer {self.settings.openrouter_api_key}", "Content-Type": "application/json"}

    def list_models(self, output_modalities: str = "all") -> dict[str, Any]:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=self.headers,
            params={"output_modalities": output_modalities},
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"OpenRouter model discovery failed: {response.text[:500]}")
        return response.json()

    def list_image_models(self) -> dict[str, Any]:
        response = requests.get(
            "https://openrouter.ai/api/v1/images/models",
            headers=self.headers,
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"OpenRouter image model discovery failed: {response.text[:500]}")
        return response.json()

    def structured_text(self, prompt: str, schema: dict[str, Any], model: str | None = None) -> dict[str, Any]:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=self.headers,
            json={
                "model": model or self.settings.openrouter_text_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "orchestrator_output", "strict": True, "schema": schema},
                },
            },
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"OpenRouter structured text failed: {response.text[:500]}")
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        reference_images: list[Path] | None = None,
        model: str | None = None,
    ) -> Path:
        payload: dict[str, Any] = {"model": model or self.settings.openrouter_image_model, "prompt": prompt}
        if reference_images:
            payload["images"] = [
                {"b64_json": base64.b64encode(path.read_bytes()).decode("ascii")}
                for path in reference_images
            ]
        response = requests.post(
            "https://openrouter.ai/api/v1/images",
            headers=self.headers,
            json=payload,
            timeout=self.settings.network_timeout_seconds,
        )
        if response.status_code >= 400:
            raise ProviderError(f"OpenRouter image failed: {response.text[:500]}")
        data = response.json().get("data", [])
        if not data or not data[0].get("b64_json"):
            raise ProviderError("OpenRouter image response did not include b64_json.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(data[0]["b64_json"]))
        return output_path
