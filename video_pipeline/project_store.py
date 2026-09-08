import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.db_path = output_dir / "projekt8.sqlite3"
        self.projects_dir = output_dir / "projects"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY, workflow TEXT NOT NULL, brief TEXT NOT NULL,
              duration_seconds INTEGER NOT NULL, aspect_ratio TEXT NOT NULL,
              resolution TEXT NOT NULL, tts_override INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL, analysis_provider TEXT, analysis_packet TEXT,
              revision INTEGER NOT NULL DEFAULT 0, approved_revision INTEGER,
              error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attachments (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              original_name TEXT NOT NULL, stored_name TEXT NOT NULL, mime_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL, kind TEXT NOT NULL, analysis TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scenes (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              position INTEGER NOT NULL, duration_seconds REAL NOT NULL,
              description TEXT NOT NULL, dialogue TEXT NOT NULL, camera TEXT NOT NULL,
              prompt TEXT NOT NULL, reference_ids TEXT NOT NULL DEFAULT '[]',
              storyboard_path TEXT, clip_path TEXT, error TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
              completed_items INTEGER NOT NULL DEFAULT 0, total_items INTEGER NOT NULL DEFAULT 0,
              provider_operation_id TEXT, error TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              kind TEXT NOT NULL, relative_path TEXT NOT NULL, label TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(project_id)
              WHERE status IN ('queued','running');
            """)

    def create_project(self, workflow: str, brief: str, duration: int, aspect: str, resolution: str, tts_override: bool) -> str:
        project_id, now = uuid4().hex[:12], utcnow()
        with self.connect() as db:
            db.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, workflow, brief, duration, aspect, resolution, int(tts_override),
                 "uploaded", None, None, 0, None, None, now, now),
            )
        self.project_dir(project_id).mkdir(parents=True, exist_ok=True)
        return project_id

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def get_project(self, project_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self, limit: int = 8):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def add_attachment(self, project_id: str, original: str, stored: str, mime: str, size: int, kind: str) -> str:
        attachment_id = uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?)",
                       (attachment_id, project_id, original, stored, mime, size, kind, None, utcnow()))
        return attachment_id

    def attachments(self, project_id: str):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM attachments WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_attachment_analysis(self, attachment_id: str, analysis: dict):
        with self.connect() as db:
            db.execute("UPDATE attachments SET analysis=? WHERE id=?", (json.dumps(analysis), attachment_id))

    def replace_scenes(self, project_id: str, scenes: list[dict]):
        now = utcnow()
        with self.connect() as db:
            db.execute("DELETE FROM scenes WHERE project_id=?", (project_id,))
            for position, scene in enumerate(scenes, 1):
                db.execute("INSERT INTO scenes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                    scene.get("id") or uuid4().hex[:12], project_id, position,
                    float(scene["duration_seconds"]), scene.get("description", ""),
                    scene.get("dialogue", ""), scene.get("camera", ""), scene.get("prompt", ""),
                    json.dumps(scene.get("reference_ids", [])), scene.get("storyboard_path"),
                    scene.get("clip_path"), scene.get("error")))
            db.execute("UPDATE projects SET revision=revision+1, approved_revision=NULL, status='storyboard', error=NULL, updated_at=? WHERE id=?", (now, project_id))

    def scenes(self, project_id: str):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY position", (project_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["reference_ids"] = json.loads(item["reference_ids"] or "[]")
            result.append(item)
        return result

    def set_analysis(self, project_id: str, provider: str, packet: dict):
        packet_path = self.project_dir(project_id) / "analysis_packet.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        with self.connect() as db:
            db.execute("UPDATE projects SET analysis_provider=?, analysis_packet=?, status='storyboard', error=NULL, updated_at=? WHERE id=?",
                       (provider, json.dumps(packet), utcnow(), project_id))
        self.add_artifact(project_id, "analysis", "analysis_packet.json", "Analysis packet")

    def approve(self, project_id: str):
        with self.connect() as db:
            db.execute("UPDATE projects SET approved_revision=revision, status='approved', updated_at=? WHERE id=?", (utcnow(), project_id))

    def update_status(self, project_id: str, status: str, error: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE projects SET status=?, error=?, updated_at=? WHERE id=?", (status, error, utcnow(), project_id))

    def start_job(self, project_id: str, kind: str, total: int = 0) -> str:
        job_id, now = uuid4().hex[:12], utcnow()
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id, project_id, kind, "queued", "Queued", 0, total, None, None, now, now))
        return job_id

    def update_job(self, job_id: str, *, status=None, stage=None, completed=None, total_items=None, operation_id=None, error=None):
        fields, values = [], []
        for column, value in (("status", status), ("stage", stage), ("completed_items", completed), ("total_items", total_items),
                              ("provider_operation_id", operation_id), ("error", error)):
            if value is not None:
                fields.append(f"{column}=?")
                values.append(value)
        fields.append("updated_at=?")
        values.extend([utcnow(), job_id])
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", values)

    def active_job(self, project_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY started_at DESC LIMIT 1", (project_id,)).fetchone()
        return dict(row) if row else None

    def add_artifact(self, project_id: str, kind: str, relative_path: str, label: str):
        with self.connect() as db:
            existing = db.execute("SELECT id FROM artifacts WHERE project_id=? AND relative_path=?", (project_id, relative_path)).fetchone()
            if not existing:
                db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?)", (uuid4().hex[:12], project_id, kind, relative_path, label, utcnow()))

    def artifacts(self, project_id: str):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall()
        return [dict(row) for row in rows]
