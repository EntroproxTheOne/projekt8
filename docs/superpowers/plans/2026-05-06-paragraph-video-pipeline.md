# Paragraph Video Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python MVP that generates paragraph-chunked narration, images, timestamps, subtitles, and a rendered faceless video with a simple local testing webpage.

**Architecture:** The codebase is a small Python package with provider adapters for Groq and Gemini, a resumable manifest-driven pipeline, MoviePy assembly, and FastAPI routes that call the same service functions as the CLI. External APIs are isolated behind interfaces so core behavior is tested with fakes.

**Tech Stack:** Python 3.11+, pytest, pydantic, python-dotenv, requests, FastAPI, uvicorn, MoviePy, Pillow.

---

## File Structure

- `requirements.txt`: Python dependencies.
- `.env.example`: required environment variables and defaults.
- `run_pipeline.py`: CLI entrypoint.
- `video_pipeline/config.py`: environment and runtime settings.
- `video_pipeline/models.py`: pydantic data models for scenes, plans, timestamps, manifests, and status.
- `video_pipeline/planning.py`: duration math and plan validation helpers.
- `video_pipeline/manifest.py`: run directory creation, manifest read/write, skip/resume logic.
- `video_pipeline/providers/base.py`: provider protocols and shared exceptions.
- `video_pipeline/providers/groq_llm.py`: Groq JSON video-plan client.
- `video_pipeline/providers/groq_audio.py`: Groq audio adapter.
- `video_pipeline/providers/gemini_audio.py`: Gemini audio adapter.
- `video_pipeline/providers/gemini_images.py`: Gemini image adapter.
- `video_pipeline/timestamps.py`: timestamp validation and global offsetting.
- `video_pipeline/subtitles.py`: subtitle grouping and dynamic MoviePy TextClip creation.
- `video_pipeline/assembly.py`: audio/image concatenation, Ken Burns clips, final render.
- `video_pipeline/pipeline.py`: orchestration for plan, assets, render, and run-all.
- `video_pipeline/webapp.py`: FastAPI app and HTML testing page.
- `tests/`: focused pytest suite with fake providers.

## Task 1: Project Skeleton And Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `video_pipeline/__init__.py`
- Create: `video_pipeline/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing config tests**

```python
# tests/test_config.py
from video_pipeline.config import Settings, load_settings


def test_settings_validate_duration_range():
    settings = Settings(video_idea="AI history", target_duration_minutes=5)

    assert settings.target_word_count == 750
    assert settings.suggested_image_count == 60


def test_load_settings_reads_provider_from_env(monkeypatch):
    monkeypatch.setenv("AUDIO_PROVIDER", "gemini")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    settings = load_settings(video_idea="Space mystery", target_duration_minutes=3)

    assert settings.audio_provider == "gemini"
    assert settings.groq_api_key == "groq-key"
    assert settings.gemini_api_key == "gemini-key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`

Expected: FAIL because `video_pipeline.config` does not exist.

- [ ] **Step 3: Add dependencies and env example**

```text
# requirements.txt
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
python-dotenv>=1.0.1
requests>=2.32.0
moviepy>=1.0.3
pillow>=10.3.0
pytest>=8.2.0
```

```text
# .env.example
GROQ_API_KEY=
GEMINI_API_KEY=
AUDIO_PROVIDER=groq
GROQ_LLM_MODEL=llama-3.3-70b-versatile
GROQ_TTS_MODEL=
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image-preview
GEMINI_TTS_MODEL=
OUTPUT_DIR=outputs
VIDEO_WIDTH=1080
VIDEO_HEIGHT=1920
```

- [ ] **Step 4: Implement config**

```python
# video_pipeline/__init__.py
__all__ = ["__version__"]

__version__ = "0.1.0"
```

```python
# video_pipeline/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    video_idea: str
    target_duration_minutes: int
    audio_provider: str = "groq"
    output_dir: str = "outputs"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    groq_llm_model: str = "llama-3.3-70b-versatile"
    groq_tts_model: str | None = None
    gemini_image_model: str = "gemini-2.5-flash-image-preview"
    gemini_tts_model: str | None = None
    video_width: int = 1080
    video_height: int = 1920

    def __post_init__(self) -> None:
        if not self.video_idea.strip():
            raise ValueError("video_idea is required")
        if not 1 <= self.target_duration_minutes <= 60:
            raise ValueError("target_duration_minutes must be between 1 and 60")
        if self.audio_provider not in {"groq", "gemini"}:
            raise ValueError("audio_provider must be 'groq' or 'gemini'")

    @property
    def target_word_count(self) -> int:
        return self.target_duration_minutes * 150

    @property
    def suggested_image_count(self) -> int:
        return self.target_duration_minutes * 12


def load_settings(video_idea: str, target_duration_minutes: int, audio_provider: str | None = None) -> Settings:
    load_dotenv()
    return Settings(
        video_idea=video_idea,
        target_duration_minutes=target_duration_minutes,
        audio_provider=audio_provider or os.getenv("AUDIO_PROVIDER", "groq"),
        output_dir=os.getenv("OUTPUT_DIR", "outputs"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        groq_llm_model=os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"),
        groq_tts_model=os.getenv("GROQ_TTS_MODEL"),
        gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image-preview"),
        gemini_tts_model=os.getenv("GEMINI_TTS_MODEL"),
        video_width=int(os.getenv("VIDEO_WIDTH", "1080")),
        video_height=int(os.getenv("VIDEO_HEIGHT", "1920")),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

## Task 2: Models, Planning, And Validation

**Files:**
- Create: `video_pipeline/models.py`
- Create: `video_pipeline/planning.py`
- Test: `tests/test_planning.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_planning.py
import pytest

from video_pipeline.planning import build_planner_prompt, parse_video_plan


def test_build_planner_prompt_includes_duration_targets():
    prompt = build_planner_prompt("Ocean myths", target_word_count=300, suggested_image_count=24)

    assert "Ocean myths" in prompt
    assert "300 words" in prompt
    assert "24" in prompt
    assert "scenes" in prompt


def test_parse_video_plan_rejects_empty_scene_prompt():
    payload = {
        "scenes": [{"paragraph_index": 1, "narration": "Hello world", "image_prompt": ""}],
        "thumbnail_prompt": "A bright thumbnail",
        "title_and_description": {"title": "Title", "description": "Description"},
    }

    with pytest.raises(ValueError, match="image_prompt"):
        parse_video_plan(payload)


def test_parse_video_plan_normalizes_scene_order():
    payload = {
        "scenes": [
            {"paragraph_index": 2, "narration": "Second", "image_prompt": "Second image"},
            {"paragraph_index": 1, "narration": "First", "image_prompt": "First image"},
        ],
        "thumbnail_prompt": "Thumb",
        "title_and_description": {"title": "Title", "description": "Description"},
    }

    plan = parse_video_plan(payload)

    assert [scene.paragraph_index for scene in plan.scenes] == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planning.py -v`

Expected: FAIL because model and planning modules do not exist.

- [ ] **Step 3: Implement models**

```python
# video_pipeline/models.py
from pathlib import Path
from pydantic import BaseModel, Field, field_validator


class ScenePlan(BaseModel):
    paragraph_index: int = Field(ge=1)
    narration: str
    image_prompt: str

    @field_validator("narration", "image_prompt")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value.strip()


class TitleDescription(BaseModel):
    title: str
    description: str

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value.strip()


class VideoPlan(BaseModel):
    scenes: list[ScenePlan]
    thumbnail_prompt: str
    title_and_description: TitleDescription

    @field_validator("scenes")
    @classmethod
    def has_scenes(cls, value: list[ScenePlan]) -> list[ScenePlan]:
        if not value:
            raise ValueError("at least one scene is required")
        return sorted(value, key=lambda scene: scene.paragraph_index)

    @field_validator("thumbnail_prompt")
    @classmethod
    def thumbnail_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("thumbnail_prompt must not be blank")
        return value.strip()


class WordTimestamp(BaseModel):
    word: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @field_validator("word")
    @classmethod
    def word_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("word must not be blank")
        return value.strip()


class SceneStatus(BaseModel):
    paragraph_index: int
    audio_path: str | None = None
    timestamps_path: str | None = None
    image_path: str | None = None
    error: str | None = None


class RunManifest(BaseModel):
    run_id: str
    idea: str
    target_duration_minutes: int
    audio_provider: str
    plan_path: str | None = None
    metadata_path: str | None = None
    thumbnail_path: str | None = None
    final_video_path: str | None = None
    scenes: list[SceneStatus] = []

    def scene_status(self, paragraph_index: int) -> SceneStatus:
        for scene in self.scenes:
            if scene.paragraph_index == paragraph_index:
                return scene
        scene = SceneStatus(paragraph_index=paragraph_index)
        self.scenes.append(scene)
        self.scenes.sort(key=lambda item: item.paragraph_index)
        return scene
```

- [ ] **Step 4: Implement planning helpers**

```python
# video_pipeline/planning.py
from typing import Any
from pydantic import ValidationError

from video_pipeline.models import VideoPlan


def build_planner_prompt(video_idea: str, target_word_count: int, suggested_image_count: int) -> str:
    return f"""
You are generating a paragraph-chunked faceless video plan.
Topic: {video_idea}
Target narration length: about {target_word_count} words.
Visual guidance: do not exceed about {suggested_image_count} images unless needed.

Return strict JSON with:
- scenes: paragraph-indexed objects with narration and image_prompt.
- thumbnail_prompt.
- title_and_description with title and description.
Each scene should mostly map to one paragraph, one audio chunk, and one image.
""".strip()


def parse_video_plan(payload: dict[str, Any]) -> VideoPlan:
    try:
        return VideoPlan.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_planning.py -v`

Expected: PASS.

## Task 3: Manifest And Resumable Paths

**Files:**
- Create: `video_pipeline/manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_manifest.py
from pathlib import Path

from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest


def test_create_manifest_makes_expected_directories(tmp_path):
    paths = RunPaths(base_dir=tmp_path, run_id="run-a")
    manifest = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")

    assert manifest.run_id == "run-a"
    assert paths.audio_dir.exists()
    assert paths.timestamps_dir.exists()
    assert paths.images_dir.exists()


def test_save_and_reload_manifest_preserves_scene_status(tmp_path):
    paths = RunPaths(base_dir=tmp_path, run_id="run-a")
    manifest = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")
    manifest.scene_status(1).audio_path = "audio/wav_001.wav"
    save_manifest(paths, manifest)

    reloaded = create_or_load_manifest(paths, idea="Topic", duration=2, audio_provider="groq")

    assert reloaded.scene_status(1).audio_path == "audio/wav_001.wav"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manifest.py -v`

Expected: FAIL because `video_pipeline.manifest` does not exist.

- [ ] **Step 3: Implement manifest paths and persistence**

```python
# video_pipeline/manifest.py
import json
from dataclasses import dataclass
from pathlib import Path

from video_pipeline.models import RunManifest


@dataclass(frozen=True)
class RunPaths:
    base_dir: Path
    run_id: str

    @property
    def run_dir(self) -> Path:
        return self.base_dir / self.run_id

    @property
    def audio_dir(self) -> Path:
        return self.run_dir / "audio"

    @property
    def timestamps_dir(self) -> Path:
        return self.run_dir / "timestamps"

    @property
    def images_dir(self) -> Path:
        return self.run_dir / "images"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def plan_path(self) -> Path:
        return self.run_dir / "plan.json"

    @property
    def metadata_path(self) -> Path:
        return self.run_dir / "metadata.txt"

    @property
    def final_video_path(self) -> Path:
        return self.run_dir / "final_output_video.mp4"

    def audio_path(self, paragraph_index: int) -> Path:
        return self.audio_dir / f"wav_{paragraph_index:03d}.wav"

    def timestamps_path(self, paragraph_index: int) -> Path:
        return self.timestamps_dir / f"timestamps_{paragraph_index:03d}.json"

    def image_path(self, paragraph_index: int) -> Path:
        return self.images_dir / f"image_{paragraph_index:03d}.png"


def ensure_run_dirs(paths: RunPaths) -> None:
    paths.audio_dir.mkdir(parents=True, exist_ok=True)
    paths.timestamps_dir.mkdir(parents=True, exist_ok=True)
    paths.images_dir.mkdir(parents=True, exist_ok=True)


def create_or_load_manifest(paths: RunPaths, idea: str, duration: int, audio_provider: str) -> RunManifest:
    ensure_run_dirs(paths)
    if paths.manifest_path.exists():
        return RunManifest.model_validate_json(paths.manifest_path.read_text(encoding="utf-8"))
    manifest = RunManifest(
        run_id=paths.run_id,
        idea=idea,
        target_duration_minutes=duration,
        audio_provider=audio_provider,
    )
    save_manifest(paths, manifest)
    return manifest


def save_manifest(paths: RunPaths, manifest: RunManifest) -> None:
    ensure_run_dirs(paths)
    paths.manifest_path.write_text(
        json.dumps(manifest.model_dump(), indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py -v`

Expected: PASS.

## Task 4: Timestamp Utilities

**Files:**
- Create: `video_pipeline/timestamps.py`
- Test: `tests/test_timestamps.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_timestamps.py
import pytest

from video_pipeline.models import WordTimestamp
from video_pipeline.timestamps import offset_timestamps, validate_word_timestamps


def test_validate_rejects_missing_timestamps():
    with pytest.raises(ValueError, match="word-level timestamps"):
        validate_word_timestamps([])


def test_validate_rejects_non_increasing_times():
    words = [
        WordTimestamp(word="one", start=0.5, end=0.8),
        WordTimestamp(word="two", start=0.7, end=1.0),
    ]

    with pytest.raises(ValueError, match="overlap"):
        validate_word_timestamps(words)


def test_offset_timestamps_adds_scene_offset():
    words = [WordTimestamp(word="hello", start=0.0, end=0.4)]

    shifted = offset_timestamps(words, offset_seconds=10.0)

    assert shifted[0].start == 10.0
    assert shifted[0].end == 10.4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_timestamps.py -v`

Expected: FAIL because timestamp utilities do not exist.

- [ ] **Step 3: Implement timestamp utilities**

```python
# video_pipeline/timestamps.py
from video_pipeline.models import WordTimestamp


def validate_word_timestamps(words: list[WordTimestamp]) -> list[WordTimestamp]:
    if not words:
        raise ValueError("audio provider must return word-level timestamps")
    previous_end = 0.0
    for word in words:
        if word.end <= word.start:
            raise ValueError(f"timestamp for {word.word!r} has end before start")
        if word.start < previous_end:
            raise ValueError(f"timestamp overlap before {word.word!r}")
        previous_end = word.end
    return words


def offset_timestamps(words: list[WordTimestamp], offset_seconds: float) -> list[WordTimestamp]:
    return [
        WordTimestamp(word=item.word, start=item.start + offset_seconds, end=item.end + offset_seconds)
        for item in words
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_timestamps.py -v`

Expected: PASS.

## Task 5: Provider Interfaces And Fake-Friendly Adapters

**Files:**
- Create: `video_pipeline/providers/__init__.py`
- Create: `video_pipeline/providers/base.py`
- Create: `video_pipeline/providers/groq_llm.py`
- Create: `video_pipeline/providers/groq_audio.py`
- Create: `video_pipeline/providers/gemini_audio.py`
- Create: `video_pipeline/providers/gemini_images.py`
- Test: `tests/test_provider_contracts.py`

- [ ] **Step 1: Write failing contract tests**

```python
# tests/test_provider_contracts.py
from pathlib import Path

from video_pipeline.models import VideoPlan, WordTimestamp
from video_pipeline.providers.base import AudioResult
from video_pipeline.providers.groq_llm import GroqPlanner


def test_audio_result_requires_timestamps(tmp_path):
    path = tmp_path / "wav_001.wav"
    path.write_bytes(b"RIFF")

    result = AudioResult(audio_path=path, timestamps=[WordTimestamp(word="Hi", start=0, end=0.2)])

    assert result.audio_path == path
    assert result.timestamps[0].word == "Hi"


def test_groq_planner_extracts_json_from_response():
    planner = GroqPlanner(api_key="key", model="model")
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"scenes":[{"paragraph_index":1,"narration":"Hi","image_prompt":"A scene"}],"thumbnail_prompt":"Thumb","title_and_description":{"title":"T","description":"D"}}'
                }
            }
        ]
    }

    plan = planner.parse_response(payload)

    assert isinstance(plan, VideoPlan)
    assert plan.scenes[0].narration == "Hi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provider_contracts.py -v`

Expected: FAIL because provider modules do not exist.

- [ ] **Step 3: Implement provider base**

```python
# video_pipeline/providers/__init__.py
```

```python
# video_pipeline/providers/base.py
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from video_pipeline.models import VideoPlan, WordTimestamp


class ProviderError(RuntimeError):
    pass


class MissingTimestampsError(ProviderError):
    pass


@dataclass(frozen=True)
class AudioResult:
    audio_path: Path
    timestamps: list[WordTimestamp]


class PlannerProvider(Protocol):
    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        ...


class AudioProvider(Protocol):
    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        ...


class ImageProvider(Protocol):
    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        ...

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        ...
```

- [ ] **Step 4: Implement Groq planner and placeholder audio adapters**

```python
# video_pipeline/providers/groq_llm.py
import json
import requests

from video_pipeline.models import VideoPlan
from video_pipeline.planning import build_planner_prompt, parse_video_plan
from video_pipeline.providers.base import ProviderError


class GroqPlanner:
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 90) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_video_plan(self, idea: str, target_word_count: int, suggested_image_count: int) -> VideoPlan:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is required for plan generation")
        prompt = build_planner_prompt(idea, target_word_count, suggested_image_count)
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self.parse_response(response.json())

    def parse_response(self, payload: dict) -> VideoPlan:
        try:
            content = payload["choices"][0]["message"]["content"]
            return parse_video_plan(json.loads(content))
        except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"Groq plan response was invalid: {exc}") from exc
```

```python
# video_pipeline/providers/groq_audio.py
from pathlib import Path
from video_pipeline.providers.base import AudioResult, MissingTimestampsError


class GroqAudioProvider:
    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        raise MissingTimestampsError(
            "Groq audio adapter is configured but no timestamp-capable Groq TTS endpoint is implemented yet"
        )
```

```python
# video_pipeline/providers/gemini_audio.py
from pathlib import Path
from video_pipeline.providers.base import AudioResult, MissingTimestampsError


class GeminiAudioProvider:
    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model

    def synthesize_with_timestamps(self, text: str, output_audio_path: Path, output_timestamps_path: Path) -> AudioResult:
        raise MissingTimestampsError(
            "Gemini audio adapter is configured but no timestamp-capable Gemini TTS endpoint is implemented yet"
        )
```

- [ ] **Step 5: Implement Gemini image adapter**

```python
# video_pipeline/providers/gemini_images.py
import base64
from pathlib import Path
import requests

from video_pipeline.providers.base import ProviderError


class GeminiImageProvider:
    def __init__(self, api_key: str | None, model: str, timeout_seconds: int = 120) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate_scene_image(self, prompt: str, narration_context: str, output_path: Path) -> Path:
        full_prompt = f"{prompt}\n\nNarration context:\n{narration_context}"
        return self._generate_image(full_prompt, output_path)

    def generate_thumbnail(self, prompt: str, output_path: Path) -> Path:
        return self._generate_image(prompt, output_path)

    def _generate_image(self, prompt: str, output_path: Path) -> Path:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is required for image generation")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            image_part = next(part for part in parts if "inline_data" in part or "inlineData" in part)
            inline_data = image_part.get("inline_data") or image_part.get("inlineData")
            data = inline_data["data"]
        except (KeyError, IndexError, StopIteration) as exc:
            raise ProviderError("Gemini image response did not contain inline image data") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(data))
        return output_path
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_provider_contracts.py -v`

Expected: PASS.

## Task 6: Pipeline Orchestration With Fakes

**Files:**
- Create: `video_pipeline/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing orchestration tests**

```python
# tests/test_pipeline.py
import json
from pathlib import Path

from video_pipeline.models import VideoPlan, ScenePlan, TitleDescription, WordTimestamp
from video_pipeline.pipeline import PipelineServices, generate_plan, generate_assets
from video_pipeline.providers.base import AudioResult


class FakePlanner:
    def generate_video_plan(self, idea, target_word_count, suggested_image_count):
        return VideoPlan(
            scenes=[ScenePlan(paragraph_index=1, narration="Hello world", image_prompt="A bright scene")],
            thumbnail_prompt="Thumb",
            title_and_description=TitleDescription(title="Title", description="Description"),
        )


class FakeAudio:
    def synthesize_with_timestamps(self, text, output_audio_path, output_timestamps_path):
        output_audio_path.write_bytes(b"RIFF fake wav")
        words = [WordTimestamp(word="Hello", start=0, end=0.2), WordTimestamp(word="world", start=0.25, end=0.5)]
        output_timestamps_path.write_text(json.dumps([item.model_dump() for item in words]), encoding="utf-8")
        return AudioResult(audio_path=output_audio_path, timestamps=words)


class FakeImages:
    def generate_scene_image(self, prompt, narration_context, output_path):
        output_path.write_bytes(b"fake image")
        return output_path

    def generate_thumbnail(self, prompt, output_path):
        output_path.write_bytes(b"fake thumbnail")
        return output_path


def test_generate_plan_writes_plan_and_metadata(tmp_path):
    services = PipelineServices(planner=FakePlanner(), audio=FakeAudio(), images=FakeImages())

    manifest = generate_plan(
        idea="Topic",
        duration=1,
        audio_provider="groq",
        base_output_dir=tmp_path,
        run_id="run-a",
        services=services,
    )

    assert (tmp_path / "run-a" / "plan.json").exists()
    assert (tmp_path / "run-a" / "metadata.txt").read_text(encoding="utf-8").startswith("Title")
    assert manifest.scenes[0].paragraph_index == 1


def test_generate_assets_skips_existing_audio(tmp_path):
    services = PipelineServices(planner=FakePlanner(), audio=FakeAudio(), images=FakeImages())
    manifest = generate_plan("Topic", 1, "groq", tmp_path, "run-a", services)
    generate_assets(tmp_path, "run-a", services)
    first_audio = tmp_path / "run-a" / "audio" / "wav_001.wav"
    first_audio.write_bytes(b"existing")

    generate_assets(tmp_path, "run-a", services)

    assert first_audio.read_bytes() == b"existing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`

Expected: FAIL because `video_pipeline.pipeline` does not exist.

- [ ] **Step 3: Implement orchestration**

```python
# video_pipeline/pipeline.py
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest
from video_pipeline.models import VideoPlan, WordTimestamp
from video_pipeline.providers.base import AudioProvider, ImageProvider, PlannerProvider
from video_pipeline.timestamps import validate_word_timestamps


@dataclass(frozen=True)
class PipelineServices:
    planner: PlannerProvider
    audio: AudioProvider
    images: ImageProvider


def new_run_id() -> str:
    return uuid4().hex[:12]


def generate_plan(
    idea: str,
    duration: int,
    audio_provider: str,
    base_output_dir: Path,
    run_id: str | None,
    services: PipelineServices,
) -> object:
    resolved_run_id = run_id or new_run_id()
    paths = RunPaths(base_output_dir, resolved_run_id)
    manifest = create_or_load_manifest(paths, idea, duration, audio_provider)
    if paths.plan_path.exists():
        return manifest
    plan = services.planner.generate_video_plan(idea, duration * 150, duration * 12)
    paths.plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    manifest.plan_path = str(paths.plan_path.relative_to(paths.run_dir))
    manifest.metadata_path = str(paths.metadata_path.relative_to(paths.run_dir))
    manifest.scenes = []
    for scene in plan.scenes:
        manifest.scene_status(scene.paragraph_index)
    title = plan.title_and_description.title
    description = plan.title_and_description.description
    paths.metadata_path.write_text(f"{title}\n\n{description}\n", encoding="utf-8")
    save_manifest(paths, manifest)
    return manifest


def load_plan(paths: RunPaths) -> VideoPlan:
    return VideoPlan.model_validate_json(paths.plan_path.read_text(encoding="utf-8"))


def generate_assets(base_output_dir: Path, run_id: str, services: PipelineServices) -> object:
    paths = RunPaths(base_output_dir, run_id)
    manifest = create_or_load_manifest(paths, idea="", duration=1, audio_provider="groq")
    plan = load_plan(paths)
    for scene in plan.scenes:
        status = manifest.scene_status(scene.paragraph_index)
        audio_path = paths.audio_path(scene.paragraph_index)
        timestamps_path = paths.timestamps_path(scene.paragraph_index)
        image_path = paths.image_path(scene.paragraph_index)
        try:
            if not audio_path.exists() or not timestamps_path.exists():
                result = services.audio.synthesize_with_timestamps(scene.narration, audio_path, timestamps_path)
                validate_word_timestamps(result.timestamps)
                timestamps_path.write_text(
                    json.dumps([item.model_dump() for item in result.timestamps], indent=2),
                    encoding="utf-8",
                )
            if not image_path.exists():
                services.images.generate_scene_image(scene.image_prompt, scene.narration, image_path)
            status.audio_path = str(audio_path.relative_to(paths.run_dir))
            status.timestamps_path = str(timestamps_path.relative_to(paths.run_dir))
            status.image_path = str(image_path.relative_to(paths.run_dir))
            status.error = None
        except Exception as exc:
            status.error = str(exc)
            save_manifest(paths, manifest)
            raise
        save_manifest(paths, manifest)
    thumbnail_path = paths.images_dir / "thumbnail.png"
    if not thumbnail_path.exists():
        services.images.generate_thumbnail(plan.thumbnail_prompt, thumbnail_path)
    manifest.thumbnail_path = str(thumbnail_path.relative_to(paths.run_dir))
    save_manifest(paths, manifest)
    return manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`

Expected: PASS.

## Task 7: Subtitle Grouping And Dynamic Clips

**Files:**
- Create: `video_pipeline/subtitles.py`
- Test: `tests/test_subtitles.py`

- [ ] **Step 1: Write failing subtitle tests**

```python
# tests/test_subtitles.py
from video_pipeline.models import WordTimestamp
from video_pipeline.subtitles import active_word_index, group_words


def test_group_words_limits_group_size():
    words = [WordTimestamp(word=f"w{i}", start=i * 0.2, end=i * 0.2 + 0.1) for i in range(10)]

    groups = group_words(words, max_words=4)

    assert [len(group) for group in groups] == [4, 4, 2]


def test_active_word_index_finds_current_word():
    words = [
        WordTimestamp(word="hello", start=0.0, end=0.3),
        WordTimestamp(word="world", start=0.3, end=0.6),
    ]

    assert active_word_index(words, 0.4) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_subtitles.py -v`

Expected: FAIL because `video_pipeline.subtitles` does not exist.

- [ ] **Step 3: Implement subtitle helpers and MoviePy clip builder**

```python
# video_pipeline/subtitles.py
from moviepy.editor import CompositeVideoClip, TextClip

from video_pipeline.models import WordTimestamp


def group_words(words: list[WordTimestamp], max_words: int = 6) -> list[list[WordTimestamp]]:
    return [words[index:index + max_words] for index in range(0, len(words), max_words)]


def active_word_index(words: list[WordTimestamp], time_seconds: float) -> int | None:
    for index, word in enumerate(words):
        if word.start <= time_seconds < word.end:
            return index
    return None


def build_dynamic_subtitle_clips(
    words: list[WordTimestamp],
    video_size: tuple[int, int],
    font: str = "Arial-Bold",
) -> list[CompositeVideoClip]:
    clips = []
    width, height = video_size
    y = int(height * 0.74)
    for group in group_words(words):
        group_start = group[0].start
        group_end = group[-1].end
        for word_index, word in enumerate(group):
            text = " ".join(item.word for item in group)
            active = active_word_index(group, word.start) == word_index
            fontsize = 70 if active else 56
            color = "yellow" if active else "white"
            clip = (
                TextClip(text, fontsize=fontsize, color=color, font=font, stroke_color="black", stroke_width=3)
                .set_start(word.start)
                .set_duration(max(0.01, word.end - word.start))
                .set_position(("center", y))
            )
            clips.append(clip)
        if group_end > group_start:
            pass
    return clips
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_subtitles.py -v`

Expected: PASS.

## Task 8: Assembly

**Files:**
- Create: `video_pipeline/assembly.py`
- Test: `tests/test_assembly.py`

- [ ] **Step 1: Write failing assembly tests**

```python
# tests/test_assembly.py
from video_pipeline.assembly import distribute_clip_durations


def test_distribute_clip_durations_uses_audio_durations():
    durations = distribute_clip_durations([1.0, 2.5, 3.0])

    assert durations == [1.0, 2.5, 3.0]
```

- [ ] **Step 2: Run tests to verify it fails**

Run: `pytest tests/test_assembly.py -v`

Expected: FAIL because assembly module does not exist.

- [ ] **Step 3: Implement assembly helpers and render function**

```python
# video_pipeline/assembly.py
import json
from pathlib import Path

from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_audioclips, concatenate_videoclips

from video_pipeline.manifest import RunPaths
from video_pipeline.models import WordTimestamp
from video_pipeline.subtitles import build_dynamic_subtitle_clips
from video_pipeline.timestamps import offset_timestamps, validate_word_timestamps


def distribute_clip_durations(audio_durations: list[float]) -> list[float]:
    return audio_durations


def ken_burns_clip(image_path: Path, duration: float, size: tuple[int, int]) -> ImageClip:
    width, height = size
    return (
        ImageClip(str(image_path))
        .resize(height=height)
        .crop(width=width, height=height, x_center=width / 2, y_center=height / 2)
        .set_duration(duration)
        .resize(lambda t: 1.0 + 0.04 * (t / max(duration, 0.01)))
    )


def render_video(paths: RunPaths, width: int = 1080, height: int = 1920) -> Path:
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    audio_clips = []
    image_clips = []
    all_words: list[WordTimestamp] = []
    offset = 0.0
    for scene in manifest["scenes"]:
        if scene.get("error"):
            raise ValueError(f"Cannot render with failed scene {scene['paragraph_index']}: {scene['error']}")
        audio_path = paths.run_dir / scene["audio_path"]
        image_path = paths.run_dir / scene["image_path"]
        timestamps_path = paths.run_dir / scene["timestamps_path"]
        audio_clip = AudioFileClip(str(audio_path))
        audio_clips.append(audio_clip)
        image_clips.append(ken_burns_clip(image_path, audio_clip.duration, (width, height)))
        words = [WordTimestamp.model_validate(item) for item in json.loads(timestamps_path.read_text(encoding="utf-8"))]
        validate_word_timestamps(words)
        all_words.extend(offset_timestamps(words, offset))
        offset += audio_clip.duration
    video = concatenate_videoclips(image_clips, method="compose")
    audio = concatenate_audioclips(audio_clips)
    subtitle_clips = build_dynamic_subtitle_clips(all_words, (width, height))
    final = CompositeVideoClip([video, *subtitle_clips], size=(width, height)).set_audio(audio)
    final.write_videofile(str(paths.final_video_path), fps=30, codec="libx264", audio_codec="aac")
    return paths.final_video_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_assembly.py -v`

Expected: PASS.

## Task 9: CLI Entrypoint

**Files:**
- Create: `run_pipeline.py`
- Modify: `video_pipeline/pipeline.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI parser test**

```python
# tests/test_cli.py
from run_pipeline import parse_args


def test_parse_args_accepts_run_all():
    args = parse_args(["--idea", "AI myths", "--duration-minutes", "2", "--run-all", "--audio-provider", "gemini"])

    assert args.idea == "AI myths"
    assert args.duration_minutes == 2
    assert args.run_all is True
    assert args.audio_provider == "gemini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`

Expected: FAIL because `run_pipeline.py` does not exist.

- [ ] **Step 3: Implement CLI**

```python
# run_pipeline.py
import argparse
from pathlib import Path

from video_pipeline.config import load_settings
from video_pipeline.manifest import RunPaths
from video_pipeline.pipeline import PipelineServices, generate_assets, generate_plan
from video_pipeline.assembly import render_video
from video_pipeline.providers.groq_llm import GroqPlanner
from video_pipeline.providers.groq_audio import GroqAudioProvider
from video_pipeline.providers.gemini_audio import GeminiAudioProvider
from video_pipeline.providers.gemini_images import GeminiImageProvider


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea", required=True)
    parser.add_argument("--duration-minutes", type=int, required=True)
    parser.add_argument("--audio-provider", choices=["groq", "gemini"], default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--generate-plan", action="store_true")
    parser.add_argument("--generate-assets", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    return parser.parse_args(argv)


def build_services(settings):
    audio = (
        GeminiAudioProvider(settings.gemini_api_key, settings.gemini_tts_model)
        if settings.audio_provider == "gemini"
        else GroqAudioProvider(settings.groq_api_key, settings.groq_tts_model)
    )
    return PipelineServices(
        planner=GroqPlanner(settings.groq_api_key or "", settings.groq_llm_model),
        audio=audio,
        images=GeminiImageProvider(settings.gemini_api_key, settings.gemini_image_model),
    )


def main(argv=None):
    args = parse_args(argv)
    settings = load_settings(args.idea, args.duration_minutes, args.audio_provider)
    services = build_services(settings)
    run_id = args.run_id
    if args.generate_plan or args.run_all:
        manifest = generate_plan(args.idea, args.duration_minutes, settings.audio_provider, Path(settings.output_dir), run_id, services)
        run_id = manifest.run_id
        print(f"Plan ready: {run_id}")
    if args.generate_assets or args.run_all:
        if not run_id:
            raise SystemExit("--run-id is required when generating assets without --generate-plan")
        generate_assets(Path(settings.output_dir), run_id, services)
        print(f"Assets ready: {run_id}")
    if args.render or args.run_all:
        if not run_id:
            raise SystemExit("--run-id is required when rendering without --generate-plan")
        output = render_video(RunPaths(Path(settings.output_dir), run_id), settings.video_width, settings.video_height)
        print(f"Rendered: {output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`

Expected: PASS.

## Task 10: FastAPI Testing Webpage

**Files:**
- Create: `video_pipeline/webapp.py`
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Write failing webapp test**

```python
# tests/test_webapp.py
from fastapi.testclient import TestClient

from video_pipeline.webapp import app


def test_homepage_contains_testing_form():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Video idea" in response.text
    assert "Target duration" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_webapp.py -v`

Expected: FAIL because webapp module does not exist.

- [ ] **Step 3: Implement simple webpage**

```python
# video_pipeline/webapp.py
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from run_pipeline import build_services
from video_pipeline.config import load_settings
from video_pipeline.manifest import RunPaths, create_or_load_manifest
from video_pipeline.pipeline import generate_assets, generate_plan
from video_pipeline.assembly import render_video


app = FastAPI(title="Faceless Video Pipeline Tester")


def page(content: str) -> HTMLResponse:
    return HTMLResponse(f"""
<!doctype html>
<html>
<head>
  <title>Video Pipeline Tester</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; max-width: 1080px; }}
    label {{ display: block; margin-top: 12px; font-weight: 700; }}
    input, select {{ padding: 8px; width: 100%; max-width: 560px; }}
    button {{ margin-top: 16px; padding: 10px 14px; }}
    table {{ border-collapse: collapse; margin-top: 24px; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  </style>
</head>
<body>
  <h1>Video Pipeline Tester</h1>
  {content}
</body>
</html>
""")


@app.get("/", response_class=HTMLResponse)
def home():
    return page("""
<form method="post" action="/run-all">
  <label>Video idea</label>
  <input name="idea" required>
  <label>Target duration</label>
  <input name="duration_minutes" type="number" min="1" max="60" value="1" required>
  <label>Audio provider</label>
  <select name="audio_provider">
    <option value="groq">Groq</option>
    <option value="gemini">Gemini</option>
  </select>
  <button type="submit">Run all</button>
</form>
""")


@app.post("/run-all")
def run_all(idea: str = Form(...), duration_minutes: int = Form(...), audio_provider: str = Form("groq")):
    settings = load_settings(idea, duration_minutes, audio_provider)
    services = build_services(settings)
    manifest = generate_plan(idea, duration_minutes, settings.audio_provider, Path(settings.output_dir), None, services)
    generate_assets(Path(settings.output_dir), manifest.run_id, services)
    render_video(RunPaths(Path(settings.output_dir), manifest.run_id), settings.video_width, settings.video_height)
    return RedirectResponse(f"/status/{manifest.run_id}", status_code=303)


@app.get("/status/{run_id}", response_class=HTMLResponse)
def status(run_id: str):
    settings = load_settings("status", 1)
    paths = RunPaths(Path(settings.output_dir), run_id)
    manifest = create_or_load_manifest(paths, idea="status", duration=1, audio_provider=settings.audio_provider)
    rows = "".join(
        f"<tr><td>{scene.paragraph_index}</td><td>{scene.audio_path or ''}</td><td>{scene.timestamps_path or ''}</td><td>{scene.image_path or ''}</td><td>{scene.error or ''}</td></tr>"
        for scene in manifest.scenes
    )
    video = f"<video src='/outputs/{run_id}/final_output_video.mp4' controls width='360'></video>" if paths.final_video_path.exists() else ""
    return page(f"""
<p>Run ID: {run_id}</p>
<table><thead><tr><th>Scene</th><th>Audio</th><th>Timestamps</th><th>Image</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>
{video}
""")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_webapp.py -v`

Expected: PASS.

## Task 11: End-To-End Verification

**Files:**
- All created files.

- [ ] **Step 1: Install dependencies**

Run: `pip install -r requirements.txt`

Expected: dependencies install successfully.

- [ ] **Step 2: Run all tests**

Run: `pytest -v`

Expected: all tests pass.

- [ ] **Step 3: Start the testing webpage**

Run: `uvicorn video_pipeline.webapp:app --reload --port 8000`

Expected: server starts at `http://127.0.0.1:8000`.

- [ ] **Step 4: Manual provider limitation check**

Run: `python run_pipeline.py --idea "A short history of AI" --duration-minutes 1 --generate-plan`

Expected: plan generation either succeeds with valid `GROQ_API_KEY` or fails clearly that the key is missing. Asset generation with Groq/Gemini audio should fail clearly until a timestamp-capable TTS implementation is configured.

## Self-Review

- Spec coverage: plan covers CLI, webpage, Groq planning, Gemini image adapter, selectable audio adapters, manifest resumability, paragraph assets, dynamic subtitles, assembly, and tests.
- Known implementation gap: Groq/Gemini audio adapters intentionally fail until a real timestamp-capable endpoint is chosen. This matches the spec requirement to fail clearly if timestamps are unavailable.
- Placeholder scan: no TBD/TODO language remains in task instructions.
- Type consistency: shared names are `VideoPlan`, `ScenePlan`, `WordTimestamp`, `RunManifest`, `RunPaths`, and `PipelineServices` throughout.
