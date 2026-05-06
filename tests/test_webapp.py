from fastapi.testclient import TestClient

from video_pipeline.webapp import app


def test_homepage_contains_testing_form():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Video idea" in response.text
    assert "Target duration" in response.text


def test_status_page_shows_generation_boxes(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest

    paths = RunPaths(tmp_path, "run-a")
    manifest = create_or_load_manifest(paths, "idea", 1, "gemini")
    manifest.plan_path = "plan.json"
    paths.plan_path.write_text(
        '{"scenes":[{"paragraph_index":1,"narration":"Readable narration text","image_prompt":"Image prompt"}],"thumbnail_prompt":"Thumb","title_and_description":{"title":"Title","description":"Description"}}',
        encoding="utf-8",
    )
    manifest.scene_status(1).image_path = "images/image_001.png"
    manifest.scene_status(1).audio_path = "audio/wav_001.wav"
    manifest.scene_status(1).timestamps_path = "timestamps/timestamps_001.json"
    paths.audio_path(1).write_bytes(b"RIFF fake wav")
    paths.timestamps_path(1).write_text("[]", encoding="utf-8")
    paths.image_path(1).write_bytes(b"fake image")
    save_manifest(paths, manifest)
    client = TestClient(app)

    response = client.get("/status/run-a")

    assert response.status_code == 200
    assert "Script" in response.text
    assert "Images" in response.text
    assert "Audio" in response.text
    assert "Render" in response.text
    assert "Script Preview" in response.text
    assert "Readable narration text" in response.text
    assert "Audio Preview" in response.text
    assert "<audio" in response.text
    assert "All Generated Items" in response.text
    assert "timestamps/timestamps_001.json" in response.text


def test_status_page_auto_refreshes_when_assets_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest

    paths = RunPaths(tmp_path, "run-a")
    manifest = create_or_load_manifest(paths, "idea", 1, "gemini")
    manifest.plan_path = "plan.json"
    manifest.scene_status(1)
    save_manifest(paths, manifest)
    client = TestClient(app)

    response = client.get("/status/run-a")

    assert response.status_code == 200
    assert 'http-equiv="refresh"' in response.text


def test_homepage_shows_run_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from video_pipeline.manifest import RunPaths, create_or_load_manifest

    create_or_load_manifest(RunPaths(tmp_path, "run-a"), "idea", 1, "gemini")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "History" in response.text
    assert "/status/run-a" in response.text


def test_generate_plan_missing_api_key_returns_helpful_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/generate-plan",
        data={"idea": "test", "duration_minutes": "1", "audio_provider": "groq"},
    )

    assert response.status_code == 400
    assert "GEMINI_API_KEY" in response.text
    assert "Use mock providers" in response.text


def test_generate_assets_provider_error_redirects_to_status(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest
    from video_pipeline.providers.base import ProviderError

    paths = RunPaths(tmp_path, "run-a")
    manifest = create_or_load_manifest(paths, "idea", 1, "gemini")
    manifest.scene_status(1)
    save_manifest(paths, manifest)

    def fake_generate_assets(base_output_dir, run_id, services):
        raise ProviderError("Gemini image request timed out after 300 seconds")

    monkeypatch.setattr("video_pipeline.webapp.generate_assets", fake_generate_assets)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/generate-assets/run-a", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/status/run-a"
