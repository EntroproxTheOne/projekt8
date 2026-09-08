import io
from types import SimpleNamespace
from PIL import Image
from fastapi.testclient import TestClient
from video_pipeline.webapp import app, run_history
from video_pipeline import markup
from video_pipeline.models import RunManifest
from video_pipeline.manifest import RunPaths, save_manifest


def png():
    data = io.BytesIO()
    Image.new('RGB', (64, 64), 'white').save(data, format='PNG')
    return data.getvalue()


def test_markup_validates_file_before_provider(monkeypatch):
    def unexpected(*args):
        raise AssertionError('Invalid input must not reach provider')
    monkeypatch.setattr(markup, 'generate_markup', unexpected)
    client = TestClient(app)
    for data in (b'not an image', b'x' * (markup.MAX_BYTES + 1)):
        assert client.post('/api/markup/generate', files={'image': ('fake.png', data, 'image/png')}).status_code == 422


def test_markup_key_error_and_success(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(markup, 'load_settings', lambda *args: SimpleNamespace(gemini_api_key=''))
    assert client.post('/api/markup/generate', files={'image': ('test.png', png(), 'image/png')}).status_code == 503
    monkeypatch.setattr(markup, 'load_settings', lambda *args: SimpleNamespace(gemini_api_key='test'))
    monkeypatch.setattr(markup, 'generate_markup', lambda data, settings: '<html><body><h1>Example</h1></body></html>')
    response = client.post('/api/markup/generate', files={'image': ('test.png', png(), 'image/png')})
    assert response.status_code == 200
    assert '<h1>Example</h1>' in response.json()['html']


def test_provider_builds_multimodal_request_and_rejects_truncation(monkeypatch):
    settings = SimpleNamespace(gemini_api_key='test-key', gemini_text_model='test-model', network_timeout_seconds=120)
    payload = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '```html\n<html><body>Hello</body></html>\n```'}]}}]}
    def post(url, **kwargs):
        assert 'test-key' not in url
        assert kwargs['headers']['x-goog-api-key'] == 'test-key'
        assert kwargs['json']['contents'][0]['parts'][1]['inlineData']['mimeType'] == 'image/png'
        return SimpleNamespace(status_code=200, json=lambda: payload)
    monkeypatch.setattr(markup.requests, 'post', post)
    assert markup.generate_markup(png(), settings).startswith('<html>')
    payload['candidates'][0]['finishReason'] = 'MAX_TOKENS'
    import pytest
    with pytest.raises(ValueError, match='finish'):
        markup.generate_markup(png(), settings)


def test_history_uses_only_completed_existing_videos(tmp_path):
    paths = RunPaths(tmp_path, 'example')
    manifest = RunManifest(run_id='example', idea='<script>title</script>', target_duration_minutes=1, audio_provider='mock')
    save_manifest(paths, manifest)
    paths.final_video_path.write_bytes(b'partial')
    assert '<video' not in run_history(tmp_path)
    manifest.final_video_path = paths.final_video_path.name
    save_manifest(paths, manifest)
    result = run_history(tmp_path)
    assert '<video controls' in result
    assert '&lt;script&gt;title' in result
    assert '<script>title' not in result
