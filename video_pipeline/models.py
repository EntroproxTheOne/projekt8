from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TitleAndDescription(BaseModel):
    title: str
    description: str


class ScenePlan(BaseModel):
    paragraph_index: int
    narration: str
    image_prompt: str


class VideoPlan(BaseModel):
    scenes: list[ScenePlan]
    thumbnail_prompt: str
    title_and_description: TitleAndDescription


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float


class AudioResult(BaseModel):
    audio_path: Path
    timestamps: list[WordTimestamp]
    timestamp_source: str
    provider: str = ""
    cost: float | None = None


class SceneStatus(BaseModel):
    paragraph_index: int
    audio_path: str | None = None
    timestamps_path: str | None = None
    image_path: str | None = None
    timestamp_source: str | None = None
    error: str | None = None


class RunManifest(BaseModel):
    mock: bool = False
    output_mode: str = "video"
    run_id: str
    idea: str
    target_duration_minutes: int
    audio_provider: str
    plan_path: str | None = None
    metadata_path: str | None = None
    thumbnail_path: str | None = None
    final_video_path: str | None = None
    scenes: list[SceneStatus] = Field(default_factory=list)

    def scene_status(self, paragraph_index: int) -> SceneStatus:
        for scene in self.scenes:
            if scene.paragraph_index == paragraph_index:
                return scene
        status = SceneStatus(paragraph_index=paragraph_index)
        self.scenes.append(status)
        self.scenes.sort(key=lambda item: item.paragraph_index)
        return status


class ArtifactKind(str, Enum):
    text = "text"
    script = "script"
    prompt = "prompt"
    image = "image"
    audio = "audio"
    transcript = "transcript"
    caption = "caption"
    video = "video"
    metadata = "metadata"
    privacy_mask = "privacy_mask"
    cost_record = "cost_record"


class ArtifactRecord(BaseModel):
    id: str
    kind: ArtifactKind
    path: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    cost: float | None = None


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"
    skipped = "skipped"


class OrchestratorStepRecord(BaseModel):
    id: str
    name: str
    status: StepStatus = StepStatus.pending
    dependencies: list[str] = Field(default_factory=list)
    provider_key: str | None = None
    attempts: int = 0
    error: str | None = None
    output_artifacts: list[str] = Field(default_factory=list)


class OrchestratorJobManifest(BaseModel):
    job_id: str
    name: str
    pipeline: str
    status: StepStatus = StepStatus.pending
    input_data: dict[str, Any] = Field(default_factory=dict)
    steps: list[OrchestratorStepRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    total_cost: float = 0.0

    def step(self, step_id: str) -> OrchestratorStepRecord:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)
