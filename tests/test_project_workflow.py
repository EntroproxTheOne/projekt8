from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from video_pipeline.project_store import ProjectStore
from video_pipeline.project_workflow import analyze_project, scene_durations, validate_upload_signature
from video_pipeline.webapp import app
from video_pipeline.providers.base import sanitize_provider_error


def test_sixty_seconds_is_split_into_eight_supported_clips():
    durations = scene_durations(60)
    assert len(durations) == 8
    assert sum(durations) == 60
    assert all(3 <= duration <= 10 for duration in durations)


def test_upload_signature_rejects_disguised_media():
    validate_upload_signature("reference.png", b"\x89PNG\r\n\x1a\nvalid-enough-header")
    with pytest.raises(ValueError, match="valid PNG"):
        validate_upload_signature("reference.png", b"this is not an image")


def test_provider_errors_redact_query_and_known_secrets():
    secret = "secret-value-123"
    message = sanitize_provider_error(
        f"request failed for https://example.test/run?key={secret} using {secret}",
        (secret,),
    )
    assert secret not in message
    assert message.count("[REDACTED]") >= 1


def test_delete_resequences_scenes(tmp_path, monkeypatch):
    from video_pipeline import webapp
    store = ProjectStore(tmp_path)
    project_id = store.create_project("generate", "test", 24, "9:16", "720p", False)
    store.replace_scenes(project_id, [
        {"duration_seconds": 8, "description": str(i), "dialogue": "", "camera": "Wide", "prompt": "Shot", "reference_ids": []}
        for i in range(3)
    ])
    middle_id = store.scenes(project_id)[1]["id"]
    monkeypatch.setattr(webapp, "project_store", lambda: store)
    response = TestClient(app).post(f"/projects/{project_id}/scenes/{middle_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert [scene["position"] for scene in store.scenes(project_id)] == [1, 2]


def test_scene_edit_invalidates_approval(tmp_path, monkeypatch):
    from video_pipeline import webapp
    store = ProjectStore(tmp_path)
    project_id = store.create_project("generate", "test", 8, "9:16", "720p", False)
    store.replace_scenes(project_id, [{"duration_seconds": 8, "description": "One", "dialogue": "Hi", "camera": "Wide", "prompt": "One shot", "reference_ids": []}])
    store.approve(project_id)
    scene = store.scenes(project_id)[0]
    monkeypatch.setattr(webapp, "project_store", lambda: store)
    response = TestClient(app).post(f"/projects/{project_id}/scenes/{scene['id']}/update", data={
        "duration_seconds": 8, "description": "Changed", "dialogue": "Hi", "camera": "Wide", "prompt": "One shot"}, follow_redirects=False)
    assert response.status_code == 303
    project = store.get_project(project_id)
    assert project["approved_revision"] is None


def test_generation_is_rejected_without_current_approval(tmp_path, monkeypatch):
    from video_pipeline import webapp
    store = ProjectStore(tmp_path)
    project_id = store.create_project("generate", "test", 8, "9:16", "720p", False)
    store.replace_scenes(project_id, [{"duration_seconds": 8, "description": "One", "dialogue": "", "camera": "Wide", "prompt": "One shot", "reference_ids": []}])
    monkeypatch.setattr(webapp, "project_store", lambda: store)
    response = TestClient(app).post(f"/projects/{project_id}/generate")
    assert response.status_code == 409


def test_analysis_falls_back_and_covers_every_attachment(tmp_path, monkeypatch):
    from video_pipeline import project_workflow
    from video_pipeline.providers.mock import MockImageProvider
    store = ProjectStore(tmp_path)
    project_id = store.create_project("generate", "A one minute story", 60, "9:16", "720p", False)
    upload_dir = store.project_dir(project_id) / "uploads"; upload_dir.mkdir(parents=True)
    image_path = upload_dir / "01-reference.png"; Image.new("RGB", (32, 48), "red").save(image_path)
    attachment_id = store.add_attachment(project_id, "reference.png", image_path.name, "image/png", image_path.stat().st_size, "image")
    job_id = store.start_job(project_id, "analysis", 1)
    monkeypatch.setattr(project_workflow, "_gemini_analyze", lambda *args: (_ for _ in ()).throw(RuntimeError("Gemini unavailable")))
    scenes = [{"description": f"Scene {i}", "dialogue": "", "camera": "Wide", "prompt": "Continuous shot", "reference_ids": [attachment_id]} for i in range(8)]
    monkeypatch.setattr(project_workflow, "_openai_compatible_analyze", lambda *args: {
        "intent": "story", "source_analysis": [{"attachment_id": attachment_id, "usage": "visual reference", "limitations": ""}],
        "characters": [], "visual_style": "cinematic", "dialogue_style": "natural", "scenes": scenes})
    class Services: images = MockImageProvider()
    monkeypatch.setattr(project_workflow, "build_services", lambda *args, **kwargs: Services())
    analyze_project(store, project_id, job_id)
    project = store.get_project(project_id)
    assert project["analysis_provider"] == "groq"
    assert len(store.scenes(project_id)) == 8
    assert store.scenes(project_id)[0]["reference_ids"] == [attachment_id]
    assert store.active_job(project_id)["status"] == "complete"


def test_malformed_scene_count_is_rejected(tmp_path, monkeypatch):
    from video_pipeline import project_workflow
    store = ProjectStore(tmp_path)
    project_id = store.create_project("generate", "A one minute story", 60, "9:16", "720p", False)
    job_id = store.start_job(project_id, "analysis")
    monkeypatch.setattr(project_workflow, "_gemini_analyze", lambda *args: {"scenes": []})
    with pytest.raises(ValueError, match="expected 8"):
        analyze_project(store, project_id, job_id)
