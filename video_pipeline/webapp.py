from pathlib import Path
from threading import Lock, Thread
import html
import json

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from run_pipeline import build_services
from video_pipeline.assembly import render_video
from video_pipeline.config import load_settings
from video_pipeline.manifest import RunPaths, create_or_load_manifest, save_manifest
from video_pipeline.models import OrchestratorJobManifest, VideoPlan
from video_pipeline.orchestrator import Orchestrator
from video_pipeline.orchestrator_pipelines import audio_to_captions_steps, image_to_video_steps, text_to_video_steps
from video_pipeline.pipeline import generate_assets, generate_plan
from video_pipeline.prompt_packs import PROMPT_PACKS
from video_pipeline.providers.base import ProviderError, sanitize_provider_error
from video_pipeline.project_store import ProjectStore
from video_pipeline.project_workflow import (
    ALLOWED, MAX_FILE_BYTES, MAX_PROJECT_UPLOAD_BYTES, analyze_project,
    generate_project, safe_filename, validate_upload_signature,
)


from video_pipeline.markup import router as markup_router

app = FastAPI(title="Projekt8")
app.include_router(markup_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs", check_dir=False), name="outputs")
_running_asset_jobs: set[str] = set()
_running_render_jobs: set[str] = set()
_render_errors: dict[str, str] = {}
_running_orchestrator_jobs: set[str] = set()
_jobs_lock = Lock()


def project_store() -> ProjectStore:
    return ProjectStore(Path(load_settings("project", 1).output_dir))


from video_pipeline.ui import page, studio_content


def run_history(output_dir: Path, limit: int = 10) -> str:
    from video_pipeline.models import RunManifest
    from urllib.parse import quote
    cards = []
    for manifest_path in sorted(output_dir.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]:
        try:
            manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        run_id = manifest_path.parent.name
        def asset_url(relative):
            if not relative:
                return None
            path = (manifest_path.parent / relative).resolve()
            if not path.is_relative_to(manifest_path.parent.resolve()) or not path.is_file():
                return None
            return '/outputs/' + quote(run_id + '/' + path.relative_to(manifest_path.parent.resolve()).as_posix())
        video = asset_url(manifest.final_video_path)
        poster = asset_url(manifest.thumbnail_path) or next((url for scene in manifest.scenes if (url := asset_url(scene.image_path))), None)
        audio = next((url for scene in manifest.scenes if (url := asset_url(scene.audio_path))), None)
        if video:
            preview = f'<video controls playsinline preload="metadata" src="{video}" aria-label="Video preview"></video>'
            state = 'Video ready'
        elif poster:
            preview = f'<img src="{poster}" alt="Generated scene preview" loading="lazy">'
            state = 'Images ready' if manifest.output_mode == 'image' else 'Not rendered yet'
        elif audio:
            preview = f'<div class="audio-tile"><audio controls preload="metadata" src="{audio}"></audio></div>'
            state = 'Audio ready'
        else:
            preview = '<div class="empty-preview">Plan ready<br><small>Generate assets to see a preview</small></div>'
            state = 'Plan ready'
        cards.append(f'<article class="creation-card">{preview}<div><span class="badge">{state}</span><h3>{html.escape(manifest.idea)}</h3><a href="/status/{quote(run_id)}">Open project ↗</a></div></article>')
    return '<section class="recent-creations"><h2>Recent creations</h2><div class="creation-grid">' + ''.join(cards) + '</div></section>' if cards else ''


def project_history(store: ProjectStore) -> str:
    cards = []
    for item in store.list_projects():
        title = item["brief"].strip().splitlines()[0][:100] or "Untitled video"
        cards.append(f'''<article class="creation-card"><div class="empty-preview"><strong>{html.escape(item['status'].replace('_', ' ').title())}</strong><small>{item['duration_seconds']} sec · {html.escape(item['aspect_ratio'])}</small></div><div><span class="badge">VIDEO PROJECT</span><h3>{html.escape(title)}</h3><a href="/projects/{item['id']}">Open project ↗</a></div></article>''')
    return '<section class="recent-creations"><h2>Video projects</h2><div class="creation-grid">' + ''.join(cards) + '</div></section>' if cards else ''


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
    return f"<div class='panel'><h2>Audio Preview</h2><div class='grid'>{''.join(players)}</div></div>" if players else ""


def all_generated_items(run_id: str, manifest) -> str:
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
    rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td><a href='/outputs/{run_id}/{html.escape(path)}'>{html.escape(path)}</a></td></tr>"
        for label, path in items
    )
    return f"<div class='panel'><h2>All Generated Items</h2><table><tbody>{rows}</tbody></table></div>" if rows else ""


@app.get("/", response_class=HTMLResponse)
def home():
    settings = load_settings("home", 1)
    store = ProjectStore(Path(settings.output_dir))
    return page(studio_content() + project_history(store) + run_history(Path(settings.output_dir), limit=4))


def _job_failure(store: ProjectStore, project_id: str, job_id: str, work, *args):
    try:
        work(store, project_id, job_id, *args)
    except Exception as exc:
        project = store.get_project(project_id) or {}
        settings = load_settings(project.get("brief", "project"), 1)
        error = sanitize_provider_error(exc, (
            settings.gemini_api_key, settings.groq_api_key, settings.grok_api_key,
            settings.deepgram_api_key, settings.elevenlabs_api_key, settings.openrouter_api_key,
        ))
        store.update_job(job_id, status="failed", stage="Failed", error=error)
        store.update_status(project_id, "failed", error)


@app.post("/projects")
async def create_project_route(
    workflow: str = Form("generate"), brief: str = Form(...), duration_seconds: int = Form(60),
    aspect_ratio: str = Form("9:16"), resolution: str = Form("720p"),
    tts_override: str | None = Form(None), files: list[UploadFile] = File(default=[]),
):
    if workflow not in {"generate", "caption_existing"} or not brief.strip():
        raise HTTPException(422, "Choose a workflow and enter a video brief.")
    if not 3 <= duration_seconds <= 3600 or aspect_ratio not in {"9:16", "16:9"} or resolution not in {"360p", "720p", "1080p", "4k"}:
        raise HTTPException(422, "Choose a duration from 3–3600 seconds and a supported frame and resolution.")
    store = project_store()
    project_id = store.create_project(workflow, brief.strip(), duration_seconds, aspect_ratio, resolution, tts_override == "true")
    upload_dir = store.project_dir(project_id) / "uploads"; upload_dir.mkdir(parents=True, exist_ok=True)
    total_upload_bytes = 0
    try:
        for index, upload in enumerate(files):
            if not upload.filename:
                continue
            extension = Path(upload.filename).suffix.lower()
            kind = ALLOWED.get(extension)
            if not kind:
                raise HTTPException(415, f"Unsupported attachment: {upload.filename}")
            data = await upload.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, f"{upload.filename} is larger than 100 MB.")
            total_upload_bytes += len(data)
            if total_upload_bytes > MAX_PROJECT_UPLOAD_BYTES:
                raise HTTPException(413, "Project attachments are larger than 500 MB in total.")
            try:
                validate_upload_signature(upload.filename, data)
            except ValueError as exc:
                raise HTTPException(415, str(exc)) from exc
            stored = f"{index + 1:02d}-{safe_filename(upload.filename)}"
            (upload_dir / stored).write_bytes(data)
            mime = upload.content_type or {"image": "image/jpeg", "audio": "audio/mpeg", "video": "video/mp4", "pdf": "application/pdf"}[kind]
            store.add_attachment(project_id, upload.filename, stored, mime, len(data), kind)
        if workflow == "caption_existing" and not any(item["kind"] == "video" for item in store.attachments(project_id)):
            raise HTTPException(422, "Caption existing footage requires a video attachment.")
    except Exception as exc:
        store.update_status(project_id, "failed", str(getattr(exc, "detail", exc)))
        raise
    job_id = store.start_job(project_id, "analysis", len(store.attachments(project_id)))
    Thread(target=_job_failure, args=(store, project_id, job_id, analyze_project), daemon=True).start()
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


def _media_preview(project_id: str, scene: dict) -> str:
    path = scene.get("clip_path") or scene.get("storyboard_path")
    if not path:
        return '<span>Preview pending</span>'
    safe = html.escape(path, quote=True)
    if path.lower().endswith(".mp4"):
        return f'<video controls preload="metadata" src="/project-files/{project_id}/{safe}"></video>'
    return f'<img src="/project-files/{project_id}/{safe}" alt="Storyboard preview">'


def project_page_content(store: ProjectStore, project: dict) -> str:
    project_id = project["id"]
    job = store.active_job(project_id)
    attachments = store.attachments(project_id)
    scenes = store.scenes(project_id)
    artifacts = store.artifacts(project_id)
    raw_title = project["brief"].strip().splitlines()[0] or "Video project"
    title = html.escape(raw_title if len(raw_title) <= 120 else raw_title[:117].rsplit(" ", 1)[0] + "…")
    job_html = ""
    if job:
        total = max(1, job["total_items"]); value = min(total, job["completed_items"])
        error = f'<div class="error-panel">{html.escape(job["error"] or "Unknown job error")}</div>' if job["status"] == "failed" else ""
        job_html = f'''<section class="job-panel"><div class="job-meter"><strong>{html.escape(job['stage'])}</strong><span>{job['completed_items']}/{job['total_items']} items</span><span>Updated {html.escape(job['updated_at'])}</span></div><progress max="{total}" value="{value}"></progress>{error}</section>'''
    attachment_html = "".join(f'<span class="badge">{html.escape(item["kind"].upper())} · {html.escape(item["original_name"])}</span>' for item in attachments) or '<span class="muted">No attachments · text-only project</span>'
    scene_html = []
    caption_workflow = project["workflow"] == "caption_existing"
    for scene in scenes:
        sid = scene["id"]
        selected_references = set(scene["reference_ids"])
        reference_inputs = ''.join(f'''<label><input type="checkbox" name="reference_ids" value="{item['id']}" {'checked' if item['id'] in selected_references else ''}><span>{html.escape(item['original_name'])} · {html.escape(item['kind'])}</span></label>''' for item in attachments)
        references = f'''<fieldset class="scene-references"><legend>Source references</legend><div class="scene-reference-list">{reference_inputs or '<span class="muted">No uploaded sources</span>'}</div></fieldset>''' if not caption_workflow else ""
        fields = (f'''<label>Description<textarea name="description" required>{html.escape(scene['description'])}</textarea></label><label>{'Corrected transcript' if caption_workflow else 'Dialogue / narration'}<textarea name="dialogue">{html.escape(scene['dialogue'])}</textarea></label>''' + ("" if caption_workflow else f'''<label>Camera direction<textarea name="camera">{html.escape(scene['camera'])}</textarea></label><label>Duration (seconds)<input name="duration_seconds" type="number" min="3" max="10" step="0.1" value="{scene['duration_seconds']}" required></label><label class="wide">Omni prompt<textarea name="prompt" required>{html.escape(scene['prompt'])}</textarea></label>{references}'''))
        hidden_references = ''.join(f'<input type="hidden" name="reference_ids" value="{html.escape(ref, quote=True)}">' for ref in scene["reference_ids"])
        hidden = f'''<input type="hidden" name="camera" value="{html.escape(scene['camera'], quote=True)}"><input type="hidden" name="duration_seconds" value="{scene['duration_seconds']}"><input type="hidden" name="prompt" value="{html.escape(scene['prompt'], quote=True)}">{hidden_references}''' if caption_workflow else ""
        controls = f'''<div class="scene-controls"><span><button class="secondary" formaction="/projects/{project_id}/scenes/{sid}/move/up">↑</button> <button class="secondary" formaction="/projects/{project_id}/scenes/{sid}/move/down">↓</button> <button class="secondary" formaction="/projects/{project_id}/scenes/{sid}/storyboard">Regenerate preview</button></span><span><button class="secondary" formaction="/projects/{project_id}/scenes/{sid}/delete">Delete</button> <button type="submit">Save scene</button></span></div>''' if not caption_workflow else '<div class="scene-controls"><span></span><button type="submit">Save transcript</button></div>'
        scene_html.append(f'''<article class="scene-card"><div class="scene-preview">{_media_preview(project_id, scene)}</div><form class="scene-fields" method="post" action="/projects/{project_id}/scenes/{sid}/update">{fields}{hidden}{controls}</form></article>''')
    if scenes:
        add = "" if caption_workflow else f'<form method="post" action="/projects/{project_id}/scenes/add"><button type="submit" class="secondary">＋ Add scene</button></form>'
        if project["approved_revision"] == project["revision"]:
            if project["status"] == "complete":
                approval = f'''<div class="approval-bar"><div><strong>Project complete</strong><p>The approved revision is rendered. Downloads are available below.</p></div><a class="badge" href="#downloads">View downloads ↓</a></div>'''
            elif job and job["status"] in {"queued", "running"}:
                approval = f'''<div class="approval-bar"><div><strong>Processing approved revision {project['revision']}</strong><p>{html.escape(job['stage'])}. This page updates automatically.</p></div><button disabled>Working…</button></div>'''
            else:
                approval = f'''<div class="approval-bar"><div><strong>{'Transcript' if caption_workflow else 'Storyboard'} revision {project['revision']} approved</strong><p>{'The source footage will be preserved while caption files and a captioned copy are created.' if caption_workflow else f'Generation will make {len(scenes)} paid Omni clips, then audio and captions.'}</p></div><form method="post" action="/projects/{project_id}/generate"><button type="submit">{'Retry caption exports' if caption_workflow and project['status'] == 'failed' else 'Retry processing' if project['status'] == 'failed' else 'Create caption exports' if caption_workflow else 'Generate video'} →</button></form></div>'''
        else:
            approval = f'''<div class="approval-bar"><div><strong>Review revision {project['revision']}</strong><p>Saving, reordering, adding, deleting, or regenerating a scene requires fresh approval.</p></div><form method="post" action="/projects/{project_id}/approve"><button type="submit">Approve scenes</button></form></div>'''
    else:
        add = ""
        approval = f'''<div class="approval-bar"><div><strong>Analysis needs another attempt</strong><p>Your locally stored brief and sources are preserved. Retry after checking the connection or provider settings.</p></div><form method="post" action="/projects/{project_id}/analyze"><button type="submit">Retry analysis →</button></form></div>''' if project["status"] == "failed" else ""
    artifacts_html = "".join(f'''<div class="artifact-card"><span class="badge">{html.escape(item['kind'].upper())}</span><strong>{html.escape(item['label'])}</strong><a href="/project-files/{project_id}/{html.escape(item['relative_path'], quote=True)}" download>Download ↓</a></div>''' for item in artifacts)
    return f'''<div class="project-shell"><section class="project-summary"><div class="eyebrow">VIDEO PROJECT · {project_id}</div><h1>{title}</h1><div class="project-meta"><span>{html.escape(project['workflow'].replace('_',' ').title())}</span><span>{project['duration_seconds']} sec</span><span>{html.escape(project['aspect_ratio'])}</span><span>{html.escape(project['resolution'])}</span><span>Status: {html.escape(project['status'])}</span><span>Analysis: {html.escape(project['analysis_provider'] or 'pending')}</span></div><div class="actions" style="margin-top:16px">{attachment_html}</div></section>{job_html}{f'<div class="error-panel">{html.escape(project["error"])}</div>' if project['error'] and (not job or job['status'] != 'failed') else ''}<div class="section-heading"><div><span class="section-kicker">STORYBOARD</span><h2>Review every scene</h2></div><span>{len(scenes)} scenes · revision {project['revision']}</span></div><section class="scene-list">{''.join(scene_html)}</section>{add}{approval}{f'<section id="downloads"><div class="section-heading"><h2>Downloads</h2></div><div class="artifact-grid">{artifacts_html}</div></section>' if artifacts_html else ''}</div>'''


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(project_id: str):
    store = project_store(); project = store.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    job = store.active_job(project_id)
    refresh = '<meta http-equiv="refresh" content="3">' if job and job["status"] in {"queued", "running"} else ""
    return page(project_page_content(store, project), refresh)


def _invalidate(db, project_id: str):
    db.execute("UPDATE projects SET revision=revision+1, approved_revision=NULL, status='storyboard', error=NULL, updated_at=datetime('now') WHERE id=?", (project_id,))


@app.post("/projects/{project_id}/scenes/{scene_id}/update")
def update_scene(project_id: str, scene_id: str, description: str = Form(...), dialogue: str = Form(""), camera: str = Form(""), prompt: str = Form(...), duration_seconds: float = Form(...), reference_ids: list[str] = Form(default=[])):
    store = project_store()
    project = store.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    limit = 3600 if project and project["workflow"] == "caption_existing" else 10
    if not 3 <= duration_seconds <= limit: raise HTTPException(422, f"Scene duration must be 3–{limit} seconds.")
    valid_reference_ids = {item["id"] for item in store.attachments(project_id)}
    if any(reference_id not in valid_reference_ids for reference_id in reference_ids):
        raise HTTPException(422, "A selected scene reference does not belong to this project.")
    with store.connect() as db:
        result = db.execute("UPDATE scenes SET description=?,dialogue=?,camera=?,prompt=?,duration_seconds=?,reference_ids=? WHERE id=? AND project_id=?", (description.strip(), dialogue.strip(), camera.strip(), prompt.strip(), duration_seconds, json.dumps(reference_ids), scene_id, project_id))
        if not result.rowcount: raise HTTPException(404, "Scene not found")
        _invalidate(db, project_id)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/analyze")
def retry_analysis(project_id: str):
    store = project_store(); project = store.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    latest = store.active_job(project_id)
    if latest and latest["status"] in {"queued", "running"}:
        return RedirectResponse(f"/projects/{project_id}", 303)
    job_id = store.start_job(project_id, "analysis", len(store.attachments(project_id)))
    store.update_status(project_id, "uploaded")
    Thread(target=_job_failure, args=(store, project_id, job_id, analyze_project), daemon=True).start()
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/scenes/add")
def add_scene(project_id: str):
    store = project_store(); scenes = store.scenes(project_id)
    scenes.append({"duration_seconds": 8, "description": "New scene", "dialogue": "", "camera": "Single continuous shot", "prompt": "Describe this scene", "reference_ids": []})
    store.replace_scenes(project_id, scenes)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/scenes/{scene_id}/delete")
def delete_scene(project_id: str, scene_id: str):
    store = project_store()
    with store.connect() as db:
        result = db.execute("DELETE FROM scenes WHERE id=? AND project_id=?", (scene_id, project_id))
        if not result.rowcount: raise HTTPException(404, "Scene not found")
        remaining = db.execute("SELECT id FROM scenes WHERE project_id=? ORDER BY position", (project_id,)).fetchall()
        for position, row in enumerate(remaining, 1):
            db.execute("UPDATE scenes SET position=? WHERE id=?", (position, row[0]))
        _invalidate(db, project_id)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/scenes/{scene_id}/move/{direction}")
def move_scene(project_id: str, scene_id: str, direction: str):
    if direction not in {"up", "down"}: raise HTTPException(422, "Invalid direction")
    store = project_store()
    with store.connect() as db:
        current = db.execute("SELECT position FROM scenes WHERE id=? AND project_id=?", (scene_id, project_id)).fetchone()
        if not current: raise HTTPException(404, "Scene not found")
        target_position = current[0] + (-1 if direction == "up" else 1)
        target = db.execute("SELECT id FROM scenes WHERE project_id=? AND position=?", (project_id, target_position)).fetchone()
        if target:
            db.execute("UPDATE scenes SET position=-1 WHERE id=?", (scene_id,)); db.execute("UPDATE scenes SET position=? WHERE id=?", (current[0], target[0])); db.execute("UPDATE scenes SET position=? WHERE id=?", (target_position, scene_id)); _invalidate(db, project_id)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/scenes/{scene_id}/storyboard")
def regenerate_storyboard(project_id: str, scene_id: str):
    store = project_store(); project = store.get_project(project_id)
    scene = next((item for item in store.scenes(project_id) if item["id"] == scene_id), None)
    if not project or not scene: raise HTTPException(404, "Project or scene not found")
    output = store.project_dir(project_id) / "storyboard" / f"scene-{scene['position']:03d}.png"
    services = build_services(load_settings(project["brief"], 1), mock=False)
    try: services.images.generate_scene_image(scene["prompt"], scene["dialogue"], output)
    except Exception as exc: raise HTTPException(502, str(exc))
    with store.connect() as db:
        db.execute("UPDATE scenes SET storyboard_path=?,error=NULL WHERE id=?", (str(output.relative_to(store.project_dir(project_id))).replace('\\','/'), scene_id)); _invalidate(db, project_id)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/approve")
def approve_project(project_id: str):
    store = project_store()
    if not store.scenes(project_id): raise HTTPException(409, "There are no scenes to approve.")
    store.approve(project_id)
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/projects/{project_id}/generate")
def generate_project_route(project_id: str):
    store = project_store(); project = store.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    if project["approved_revision"] != project["revision"]: raise HTTPException(409, "Approve the current storyboard before generating video.")
    latest = store.active_job(project_id)
    if latest and latest["status"] in {"queued", "running"}: return RedirectResponse(f"/projects/{project_id}", 303)
    job_id = store.start_job(project_id, "generation", len(store.scenes(project_id)))
    Thread(target=_job_failure, args=(store, project_id, job_id, generate_project), daemon=True).start()
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.get("/project-files/{project_id}/{relative_path:path}")
def project_file(project_id: str, relative_path: str):
    store = project_store(); root = store.project_dir(project_id).resolve(); path = (root / relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404, "File not found")
    return FileResponse(path)


@app.get("/studios/{studio}", response_class=HTMLResponse)
def studio_page(studio: str):
    if studio not in {"3d", "presentation", "markup"}:
        raise HTTPException(status_code=404, detail="Studio not found")
    return page(studio_content(studio))


@app.post("/generate-plan")
def generate_plan_route(
    idea: str = Form(...),
    duration_minutes: int = Form(...),
    audio_provider: str = Form("deepgram"),
    mock: str | None = Form(None),
    output_mode: str = Form("video"),
):
    if output_mode not in {"video", "image", "audio"} or not idea.strip() or not 1 <= duration_minutes <= 60:
        raise HTTPException(status_code=422, detail="Enter a prompt, valid output type, and duration between 1 and 60 minutes.")
    settings = load_settings(idea.strip(), duration_minutes, audio_provider)
    services = build_services(settings, mock=mock == "true")
    try:
        manifest = generate_plan(idea, duration_minutes, settings.audio_provider, Path(settings.output_dir), None, services)
    except ProviderError as exc:
        return HTMLResponse(page(f"<div class='panel'><h2>Provider setup needed</h2><p>{html.escape(str(exc))}</p></div>").body.decode("utf-8"), status_code=400)
    manifest.mock = mock == "true"
    manifest.output_mode = output_mode
    save_manifest(RunPaths(Path(settings.output_dir), manifest.run_id), manifest)
    return RedirectResponse(f"/status/{manifest.run_id}", status_code=303)


@app.post("/generate-assets/{run_id}")
def generate_assets_route(run_id: str):
    settings = load_settings("status", 1)
    with _jobs_lock:
        if run_id not in _running_asset_jobs and run_id not in _running_render_jobs:
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
        manifest = create_or_load_manifest(paths, idea="status", duration=1, audio_provider=audio_provider)
        settings = load_settings("status", 1, manifest.audio_provider)
        services = build_services(settings, mock=manifest.mock)
        generate_assets(Path(output_dir), run_id, services, output_mode=manifest.output_mode)
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
    paths = RunPaths(Path(settings.output_dir), run_id)
    if not paths.manifest_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    manifest = create_or_load_manifest(paths, "status", 1, settings.audio_provider)
    if manifest.output_mode != "video" or not manifest.scenes or any(
        scene.error or not (scene.image_path and scene.audio_path and scene.timestamps_path)
        for scene in manifest.scenes
    ):
        raise HTTPException(status_code=409, detail="Generate all video assets before rendering.")
    with _jobs_lock:
        if run_id in _running_asset_jobs:
            raise HTTPException(status_code=409, detail="Assets are still generating.")
        if run_id not in _running_render_jobs:
            _running_render_jobs.add(run_id)
            _render_errors.pop(run_id, None)
            Thread(target=_safe_render, args=(paths, settings.video_width, settings.video_height), daemon=True).start()
    return RedirectResponse(f"/status/{run_id}", status_code=303)


def _safe_render(paths: RunPaths, width: int, height: int) -> None:
    try:
        render_video(paths, width, height)
    except Exception as exc:
        _render_errors[paths.run_id] = str(exc)
    finally:
        with _jobs_lock:
            _running_render_jobs.discard(paths.run_id)


@app.get("/status/{run_id}", response_class=HTMLResponse)
def status(run_id: str):
    settings = load_settings("status", 1)
    paths = RunPaths(Path(settings.output_dir), run_id)
    manifest = create_or_load_manifest(paths, idea="status", duration=1, audio_provider=settings.audio_provider)
    total = max(1, len(manifest.scenes))
    image_done = sum(1 for scene in manifest.scenes if scene.image_path)
    audio_done = sum(1 for scene in manifest.scenes if scene.audio_path and scene.timestamps_path)
    errors = [scene.error for scene in manifest.scenes if scene.error]
    rendering = run_id in _running_render_jobs
    running = run_id in _running_asset_jobs or rendering
    if run_id in _render_errors:
        errors.append(_render_errors[run_id])
    head_extra = '<meta http-equiv="refresh" content="4">' if running else ""
    rows = "".join(
        f"<tr><td>{scene.paragraph_index}</td><td>{scene.audio_path or ''}</td><td>{scene.timestamps_path or ''}</td><td>{scene.image_path or ''}</td><td>{scene.timestamp_source or ''}</td><td>{scene.error or ''}</td></tr>"
        for scene in manifest.scenes
    )
    images = "".join(
        f"<img src='/outputs/{run_id}/{scene.image_path}' alt='scene {scene.paragraph_index}'> "
        for scene in manifest.scenes
        if scene.image_path and (paths.run_dir / scene.image_path).exists()
    )
    can_render = bool(manifest.scenes) and image_done == len(manifest.scenes) and audio_done == len(manifest.scenes) and not errors and not running
    render_disabled = "" if can_render and manifest.output_mode == "video" else "disabled"
    video = f"<video src='/outputs/{run_id}/final_output_video.mp4' controls width='360'></video>" if manifest.final_video_path and paths.final_video_path.exists() else ""
    return page(f"""
<div class="panel">
  <h1>Your {manifest.output_mode} project</h1><p>{html.escape(manifest.idea)}</p>
  <p><span class="badge">{"Demo · synthetic assets" if manifest.mock else "Live providers"}</span> &nbsp; Run ID: <code>{run_id}</code></p>
  <p class="{'wait' if running else 'ok'}">{'Rendering video…' if rendering else 'Generating assets…' if running else 'Ready'}</p>
  <div class="actions">
    <form method="post" action="/generate-assets/{run_id}"><button type="submit" {"disabled" if running else ""}>Generate assets</button></form>
    <form method="post" action="/render/{run_id}"><button type="submit" {render_disabled}>Render video</button></form>
  </div>
</div>
<div class="grid">
  <div class="box"><h2>Script</h2><p>{manifest.plan_path or 'Waiting'}</p></div>
  <div class="box"><h2>Images</h2><p>{image_done}/{total}</p></div>
  <div class="box"><h2>Audio</h2><p>{audio_done}/{total}</p></div>
  <div class="box"><h2>Render</h2><p>{manifest.final_video_path or 'Final MP4 not rendered yet.'}</p></div>
</div>
{"<p class='err'>" + html.escape(errors[0]) + "</p>" if errors else ""}
{script_preview(paths)}
{audio_preview(run_id, manifest)}
{all_generated_items(run_id, manifest)}
<table><thead><tr><th>Scene</th><th>Audio</th><th>Timestamps</th><th>Image</th><th>Timestamp source</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Images</h2><div>{images}</div>
<h2>Video</h2><div>{video}</div>
""", head_extra=head_extra)


@app.get("/builder", response_class=HTMLResponse)
def builder():
    return page("""
<h1>Pipeline Builder</h1><p class="notice">Experimental: these workflows produce placeholder artifacts, not generated media.</p>
<form method="post" action="/orchestrator/start">
  <label>Pipeline</label>
  <select name="pipeline">
    <option value="text_to_video">Text to final video</option>
    <option value="image_to_video">Image to video and captions</option>
    <option value="audio_to_captions">Audio to text/captions</option>
  </select>
  <label>Idea or notes</label>
  <textarea name="idea">A short documentary about attention and modern life</textarea>
  <label>Optional image path</label>
  <input name="image_path">
  <button type="submit">Start orchestrator job</button>
</form>
""")


@app.post("/orchestrator/start")
def start_orchestrator(pipeline: str = Form(...), idea: str = Form(""), image_path: str = Form("")):
    settings = load_settings(idea or "orchestrator", 1)
    orchestrator = Orchestrator(Path(settings.output_dir), max_workers=3)
    if pipeline == "image_to_video":
        steps = image_to_video_steps()
    elif pipeline == "audio_to_captions":
        steps = audio_to_captions_steps()
    else:
        pipeline = "text_to_video"
        steps = text_to_video_steps()
    manifest = orchestrator.create_job(
        name=f"{pipeline}: {idea[:48]}",
        pipeline=pipeline,
        input_data={"idea": idea, "image_path": image_path},
        steps=steps,
    )
    with _jobs_lock:
        _running_orchestrator_jobs.add(manifest.job_id)
    Thread(target=_safe_run_orchestrator, args=(manifest.job_id, pipeline), daemon=True).start()
    return RedirectResponse(f"/orchestrator/status/{manifest.job_id}", status_code=303)


def _safe_run_orchestrator(job_id: str, pipeline: str) -> None:
    settings = load_settings("orchestrator", 1)
    orchestrator = Orchestrator(Path(settings.output_dir), max_workers=3)
    steps = text_to_video_steps() if pipeline == "text_to_video" else image_to_video_steps() if pipeline == "image_to_video" else audio_to_captions_steps()
    try:
        orchestrator.run(orchestrator.load_job(job_id), steps)
    finally:
        with _jobs_lock:
            _running_orchestrator_jobs.discard(job_id)


@app.get("/orchestrator/status/{job_id}", response_class=HTMLResponse)
def orchestrator_status(job_id: str):
    settings = load_settings("orchestrator", 1)
    manifest_path = Path(settings.output_dir) / "orchestrator" / job_id / "job_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    manifest = OrchestratorJobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    running = job_id in _running_orchestrator_jobs
    step_rows = "".join(
        f"<tr><td>{html.escape(step.name)}</td><td>{step.status}</td><td>{step.attempts}</td><td>{html.escape(step.provider_key or '')}</td><td>{html.escape(step.error or '')}</td></tr>"
        for step in manifest.steps
    )
    artifact_rows = "".join(
        f"<tr><td>{artifact.kind}</td><td>{html.escape(artifact.id)}</td><td>{html.escape(artifact.path or '')}</td><td>{artifact.cost or ''}</td></tr>"
        for artifact in manifest.artifacts
    )
    return page(f"""
<div class="panel"><p>Job: <code>{job_id}</code></p><p class="{'wait' if running else 'ok'}">{'Running' if running else manifest.status}</p></div>
<h2>Job Graph</h2>
<table><thead><tr><th>Step</th><th>Status</th><th>Attempts</th><th>Provider</th><th>Error</th></tr></thead><tbody>{step_rows}</tbody></table>
<h2>Artifacts</h2>
<table><thead><tr><th>Kind</th><th>ID</th><th>Path</th><th>Cost</th></tr></thead><tbody>{artifact_rows}</tbody></table>
""", '<meta http-equiv="refresh" content="3">' if running else "")


@app.get("/gallery", response_class=HTMLResponse)
def gallery():
    settings = load_settings("gallery", 1)
    output_dir = Path(settings.output_dir)
    links = []
    for path in sorted(output_dir.glob("**/*"), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True):
        if path.is_file() and path.suffix.lower() in {".mp4", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".json", ".txt", ".srt"}:
            rel = path.relative_to(output_dir).as_posix()
            links.append(f"<li><a href='/outputs/{html.escape(rel)}'>{html.escape(rel)}</a></li>")
        if len(links) >= 100:
            break
    return page(f"<div class='panel'><h2>Generated Artifacts</h2><ul>{''.join(links)}</ul></div>")


@app.get("/settings", response_class=HTMLResponse)
def provider_settings():
    settings = load_settings("settings", 1)
    rows = []
    for key in [
        "audio_provider",
        "image_provider",
        "planner_provider",
        "gemini_text_model",
        "gemini_image_model",
        "gemini_tts_model",
        "gemini_omni_model",
        "grok_image_model",
        "deepgram_tts_model",
        "groq_transcription_model",
        "openrouter_text_model",
        "openrouter_image_model",
        "elevenlabs_tts_model",
    ]:
        rows.append(f"<tr><td>{key}</td><td>{html.escape(str(getattr(settings, key)))}</td></tr>")
    return page(f"<div class='panel'><h2>Provider and Model Settings</h2><table>{''.join(rows)}</table><p>API keys are read from .env and intentionally hidden.</p></div>")


@app.get("/prompt-packs", response_class=HTMLResponse)
def prompt_packs():
    boxes = "".join(
        f"<div class='box'><h2>{html.escape(name)}</h2><pre>{html.escape(pack.render())}</pre></div>"
        for name, pack in PROMPT_PACKS.items()
    )
    return page(f"<div class='panel'><h2>Prompt Packs</h2><div class='grid'>{boxes}</div></div>")


@app.get("/privacy", response_class=HTMLResponse)
def privacy_tools():
    return page("""
<div class="panel">
  <h2>Privacy Tools</h2>
  <p>Local face hiding and background blur hooks are implemented through LocalVisionProvider. Use the image-to-video pipeline with an image path to create a privacy-mask artifact.</p>
</div>
""")
