from fastapi.testclient import TestClient

from video_pipeline.webapp import app


def test_home_has_orchestrator_navigation():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Pipeline Builder" in response.text
    assert "Prompt Packs" in response.text


def test_builder_can_start_placeholder_job(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    response = TestClient(app).post(
        "/orchestrator/start",
        data={"pipeline": "audio_to_captions", "idea": "test", "image_path": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/orchestrator/status/" in response.headers["location"]
    import time
    from video_pipeline.webapp import _running_orchestrator_jobs
    job_id = response.headers["location"].split("/")[-1]
    deadline = time.monotonic() + 5
    while job_id in _running_orchestrator_jobs and time.monotonic() < deadline:
        time.sleep(0.01)
    assert job_id not in _running_orchestrator_jobs


def test_demo_mode_and_voice_selection_survive_asset_generation(tmp_path, monkeypatch):
    from video_pipeline import webapp
    from video_pipeline.models import RunManifest
    from run_pipeline import build_services as actual_services
    monkeypatch.setenv('OUTPUT_DIR', str(tmp_path))
    response = TestClient(app).post('/generate-plan', data={
        'idea': 'A quiet ocean', 'duration_minutes': 1, 'audio_provider': 'elevenlabs',
        'mock': 'true', 'output_mode': 'audio'}, follow_redirects=False)
    assert response.status_code == 303
    run_id = response.headers['location'].split('/')[-1]
    calls = []
    def checked_services(settings, mock=False):
        calls.append((settings.audio_provider, mock))
        assert mock, 'Demo run must never call live providers'
        return actual_services(settings, mock=mock)
    monkeypatch.setattr(webapp, 'build_services', checked_services)
    webapp._safe_generate_assets(run_id, str(tmp_path), 'deepgram')
    manifest = RunManifest.model_validate_json((tmp_path / run_id / 'manifest.json').read_text())
    assert calls == [('elevenlabs', True)]
    assert all(scene.audio_path and not scene.image_path and not scene.error for scene in manifest.scenes)


def test_invalid_output_is_rejected_before_generation():
    response = TestClient(app).post('/generate-plan', data={
        'idea': 'A story', 'duration_minutes': 1, 'output_mode': '3d', 'mock': 'true'})
    assert response.status_code == 422


def test_render_runs_in_background_and_reports_failure(tmp_path, monkeypatch):
    import threading
    from video_pipeline import webapp
    from video_pipeline.manifest import RunPaths, save_manifest
    from video_pipeline.models import RunManifest, SceneStatus
    monkeypatch.setenv('OUTPUT_DIR', str(tmp_path))
    manifest = RunManifest(run_id='render-test', idea='Test', target_duration_minutes=1,
        audio_provider='mock', scenes=[SceneStatus(paragraph_index=1, image_path='image.png',
        audio_path='audio.wav', timestamps_path='timestamps.json')])
    save_manifest(RunPaths(tmp_path, manifest.run_id), manifest)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def render(*args):
        started.set()
        release.wait(5)
        raise ValueError('Test render failure')
    original = webapp._safe_render
    def tracked(*args):
        try:
            original(*args)
        finally:
            finished.set()
    monkeypatch.setattr(webapp, 'render_video', render)
    monkeypatch.setattr(webapp, '_safe_render', tracked)
    client = TestClient(app)
    try:
        response = client.post('/render/render-test', follow_redirects=False)
        assert response.status_code == 303
        assert started.wait(2)
        assert 'Rendering video' in client.get('/status/render-test').text
    finally:
        release.set()
        assert finished.wait(5)
    assert 'Test render failure' in client.get('/status/render-test').text
    webapp._render_errors.pop('render-test', None)
