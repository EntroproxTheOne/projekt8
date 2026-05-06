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
    timestamp_source: str | None = None
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
    scenes: list[SceneStatus] = Field(default_factory=list)

    def scene_status(self, paragraph_index: int) -> SceneStatus:
        for scene in self.scenes:
            if scene.paragraph_index == paragraph_index:
                return scene
        scene = SceneStatus(paragraph_index=paragraph_index)
        self.scenes.append(scene)
        self.scenes.sort(key=lambda item: item.paragraph_index)
        return scene
