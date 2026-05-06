from pathlib import Path
from threading import Lock, Thread
import html

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from run_pipeline import build_services
from video_pipeline.assembly import render_video
from video_pipeline.config import load_settings
from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest
from video_pipeline.models import VideoPlan
from video_pipeline.pipeline import generate_assets, generate_plan
from video_pipeline.providers.base import ProviderError


app = FastAPI(title="Faceless Video Pipeline Tester")
app.mount("/outputs", StaticFiles(directory="outputs", check_dir=False), name="outputs")
_running_asset_jobs: set[str] = set()
_jobs_lock = Lock()


def page(content: str, head_extra: str = "") -> HTMLResponse:
    return HTMLResponse(f"""
<!doctype html>
<html>
<head>
  <title>Video Pipeline Tester</title>
  {head_extra}
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #111827; background: #f6f7f9; }}
    main {{ max-width: 1120px; margin: 0 auto; }}
    h1 {{ margin-bottom: 8px; }}
    form, .panel {{ background: white; border: 1px solid #d8dee8; border-radius: 8px; padding: 18px; }}
    label {{ display: block; margin-top: 12px; font-weight: 700; }}
    input, select {{ box-sizing: border-box; padding: 9px; width: 100%; max-width: 620px; border: 1px solid #b8c0cc; border-radius: 6px; }}
    button {{ margin-top: 16px; padding: 10px 14px; border: 0; border-radius: 6px; background: #14532d; color: white; font-weight: 700; cursor: pointer; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 18px; }}
    .box {{ background: white; border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; min-height: 96px; }}
    .box h2 {{ font-size: 18px; margin: 0 0 8px; }}
    .ok {{ color: #14532d; font-weight: 700; }}
    .wait {{ color: #92400e; font-weight: 700; }}
    .err {{ color: #991b1b; font-weight: 700; }}
    table {{ border-collapse: collapse; margin-top: 20px; width: 100%; background: white; }}
    th, td {{ border: 1px solid #d8dee8; padding: 8px; text-align: left; font-size: 14px; }}
    th {{ background: #edf2f7; }}
    code {{ background: #edf2f7; padding: 2px 4px; border-radius: 4px; }}
    .actions form {{ display: inline-block; margin-right: 8px; padding: 0; border: 0; background: transparent; }}
    img {{ max-width: 180px; border-radius: 6px; border: 1px solid #d8dee8; }}
  </style>
</head>
<body>
  <main>
    <h1>Video Pipeline Tester</h1>
    {content}
  </main>
</body>
</html>
""")


def run_history(output_dir: Path, limit: int = 10) -> str:
    if not output_dir.exists():
        return ""
    items = []
    for manifest_path in sorted(output_dir.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]:
        run_id = manifest_path.parent.name
        items.append(f"<li><a href='/status/{run_id}'>{run_id}</a></li>")
    if not items:
        return ""
    return f"<div class='panel'><h2>History</h2><ul>{''.join(items)}</ul></div>"


def script_preview(paths: RunPaths) -> str:
    if not paths.plan_path.exists():
        return ""
    try:
        plan = VideoPlan.model_validate_json(paths.plan_path.read_text(encoding="utf-8"))
    except Exception:
        return "<div class='panel'><h2>Script Preview</h2><p class='err'>Could not read plan.json.</p></div>"
    scenes = "".join(
        f"<div class='box'><h2>Scene {scene.paragraph_index}</h2><p>{html.escape(scene.narration)}</p></div>"
        for scene in plan.scenes
    )
    return f"<div class='panel'><h2>Script Preview</h2><div class='grid'>{scenes}</div></div>"


def audio_preview(run_id: str, manifest) -> str:
    players = []
    for scene in manifest.scenes:
        if scene.audio_path:
            players.append(
                f"<div class='box'><h2>Audio {scene.paragraph_index}</h2>"
                f"<audio controls src='/outputs/{run_id}/{scene.audio_path}'></audio>"
                f"<p><code>{html.escape(scene.audio_path)}</code></p></div>"
            )
    if not players:
        return ""
    return f"<div class='panel'><h2>Audio Preview</h2><div class='grid'>{''.join(players)}</div></div>"


def all_generated_items(run_id: str, paths: RunPaths, manifest) -> str:
    items: list[tuple[str, str]] = []
    for label, rel_path in [
        ("Plan", manifest.plan_path),
        ("Metadata", manifest.metadata_path),
        ("Thumbnail", manifest.thumbnail_path),
        ("Final video", manifest.final_video_path),
    ]:
        if rel_path:
            items.append((label, rel_path))
    for scene in manifest.scenes:
        for label, rel_path in [
            (f"Scene {scene.paragraph_index} image", scene.image_path),
            (f"Scene {scene.paragraph_index} audio", scene.audio_path),
            (f"Scene {scene.paragraph_index} timestamps", scene.timestamps_path),
        ]:
            if rel_path:
                items.append((label, rel_path))
    if not items:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td><a href='/outputs/{run_id}/{html.escape(path)}'>{html.escape(path)}</a></td></tr>"
        for label, path in items
    )
    return f"<div class='panel'><h2>All Generated Items</h2><table><tbody>{rows}</tbody></table></div>"


@app.get("/", response_class=HTMLResponse)
def home():
    settings = load_settings("home", 1)
    history = run_history(Path(settings.output_dir))
    return page("""
<form method="post" action="/generate-plan">
  <label>Video idea</label>
  <input name="idea" required>
  <label>Target duration</label>
  <input name="duration_minutes" type="number" min="1" max="60" value="1" required>
  <label>Audio provider</label>
  <select name="audio_provider">
    <option value="deepgram">Deepgram Aura 2</option>
    <option value="gemini">Gemini</option>
    <option value="groq">Groq</option>
    <option value="realtimetts">RealtimeTTS 1.5 Mini</option>
    <option value="inworld">Inworld Realtime TTS 1.5 Max</option>
  </select>
  <label><input name="mock" type="checkbox" value="true" style="width:auto"> Use mock providers</label>
  <button type="submit">Generate plan</button>
</form>
""" + history)


@app.post("/generate-plan")
def generate_plan_route(
    idea: str = Form(...),
    duration_minutes: int = Form(...),
    audio_provider: str = Form("deepgram"),
    mock: str | None = Form(None),
):
    settings = load_settings(idea, duration_minutes, audio_provider)
    services = build_services(settings, mock=mock == "true")
    try:
        manifest = generate_plan(idea, duration_minutes, settings.audio_provider, Path(settings.output_dir), None, services)
    except ProviderError as exc:
        return HTMLResponse(
            page(
                f"""
<div class="panel">
  <h2>Provider setup needed</h2>
  <p>{str(exc)}</p>
  <p>Add the required key to <code>.env</code>, or go back and enable <strong>Use mock providers</strong>.</p>
  <p><a href="/">Back to tester</a></p>
</div>
"""
            ).body.decode("utf-8"),
            status_code=400,
        )
    return RedirectResponse(f"/status/{manifest.run_id}", status_code=303)


@app.post("/generate-assets/{run_id}")
def generate_assets_route(run_id: str):
    settings = load_settings("status", 1)
    services = build_services(settings)
    paths = RunPaths(Path(settings.output_dir), run_id)
    with _jobs_lock:
        if run_id not in _running_asset_jobs:
            _running_asset_jobs.add(run_id)
            Thread(target=_safe_generate_assets, args=(run_id, settings.output_dir, settings.audio_provider), daemon=True).start()
    return RedirectResponse(f"/status/{run_id}", status_code=303)


@app.get("/generate-assets/{run_id}")
def generate_assets_get_route(run_id: str):
    return RedirectResponse(f"/status/{run_id}", status_code=303)


def _safe_generate_assets(run_id: str, output_dir: str, audio_provider: str) -> None:
    paths = RunPaths(Path(output_dir), run_id)
    try:
        settings = load_settings("status", 1, audio_provider)
        services = build_services(settings)
        generate_assets(Path(output_dir), run_id, services)
    except Exception as exc:
        manifest = create_or_load_manifest(paths, idea="status", duration=1, audio_provider=audio_provider)
        if manifest.scenes:
            manifest.scenes[-1].error = str(exc)
        save_manifest(paths, manifest)
    finally:
        with _jobs_lock:
            _running_asset_jobs.discard(run_id)


@app.post("/render/{run_id}")
def render_route(run_id: str):
    settings = load_settings("status", 1)
    try:
        render_video(RunPaths(Path(settings.output_dir), run_id), settings.video_width, settings.video_height)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(f"/status/{run_id}", status_code=303)


@app.post("/run-all")
def run_all_route(idea: str = Form(...), duration_minutes: int = Form(...), audio_provider: str = Form("deepgram")):
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
        f"<tr><td>{scene.paragraph_index}</td><td>{scene.audio_path or ''}</td><td>{scene.timestamps_path or ''}</td>"
        f"<td>{scene.image_path or ''}</td><td>{scene.timestamp_source or ''}</td><td>{scene.error or ''}</td></tr>"
        for scene in manifest.scenes
    )
    script_status = "Ready" if manifest.plan_path else "Waiting"
    total = max(1, len(manifest.scenes))
    image_done = sum(1 for scene in manifest.scenes if scene.image_path)
    audio_done = sum(1 for scene in manifest.scenes if scene.audio_path and scene.timestamps_path)
    errors = [scene.error for scene in manifest.scenes if scene.error]
    render_status = "Ready" if paths.final_video_path.exists() else "Waiting"
    incomplete = bool(manifest.plan_path and (image_done < total or audio_done < total) and not errors)
    running = run_id in _running_asset_jobs
    error_html = f"<p class='err'>{errors[0]}</p>" if errors else ""
    images = "".join(
        f"<img src='/outputs/{run_id}/{scene.image_path}' alt='scene {scene.paragraph_index}'> "
        for scene in manifest.scenes
        if scene.image_path and (paths.run_dir / scene.image_path).exists()
    )
    script_html = script_preview(paths)
    audio_html = audio_preview(run_id, manifest)
    items_html = all_generated_items(run_id, paths, manifest)
    video = f"<video src='/outputs/{run_id}/final_output_video.mp4' controls width='360'></video>" if paths.final_video_path.exists() else ""
    history = run_history(Path(settings.output_dir))
    head_extra = '<meta http-equiv="refresh" content="4">' if incomplete or running else ""
    return page(f"""
<div class="panel">
  <p>Run ID: <code>{run_id}</code></p>
  <p class="{'wait' if running or incomplete else 'ok'}">{'Generating assets...' if running else 'Waiting for next step' if incomplete else 'Idle'}</p>
  <div class="actions">
    <form method="post" action="/generate-assets/{run_id}"><button type="submit">Generate assets</button></form>
    <form method="post" action="/render/{run_id}"><button type="submit">Render video</button></form>
  </div>
</div>
<p><a href="/">Start another run</a></p>
<div class="grid">
  <div class="box"><h2>Script</h2><p class="{'ok' if manifest.plan_path else 'wait'}">{script_status}</p><p>{manifest.plan_path or 'Generate the story plan first.'}</p></div>
  <div class="box"><h2>Images</h2><p class="{'ok' if image_done == total else 'wait'}">{image_done}/{total}</p><p>Scene images and thumbnail.</p></div>
  <div class="box"><h2>Audio</h2><p class="{'ok' if audio_done == total else 'wait'}">{audio_done}/{total}</p><p>WAV chunks and word timestamps.</p></div>
  <div class="box"><h2>Render</h2><p class="{'ok' if paths.final_video_path.exists() else 'wait'}">{render_status}</p><p>{manifest.final_video_path or 'Final MP4 not rendered yet.'}</p></div>
</div>
{error_html}
{script_html}
{audio_html}
{items_html}
<table>
  <thead><tr><th>Scene</th><th>Audio</th><th>Timestamps</th><th>Image</th><th>Timestamp source</th><th>Error</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<h2>Images</h2>
<div>{images}</div>
<h2>Video</h2>
<div>{video}</div>
{history}
""", head_extra=head_extra)
