import json
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Callable
from uuid import uuid4

from video_pipeline.models import (
    ArtifactRecord,
    OrchestratorJobManifest,
    OrchestratorStepRecord,
    StepStatus,
)


StepHandler = Callable[["OrchestratorContext"], list[ArtifactRecord]]


@dataclass(frozen=True)
class OrchestratorStep:
    id: str
    name: str
    handler: StepHandler
    dependencies: list[str] = field(default_factory=list)
    provider_key: str | None = None
    max_attempts: int = 2
    allow_parallel: bool = True


@dataclass
class OrchestratorContext:
    job_dir: Path
    manifest: OrchestratorJobManifest
    step: OrchestratorStep

    def artifact_path(self, filename: str) -> Path:
        path = self.job_dir / "artifacts" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class Orchestrator:
    def __init__(self, output_dir: Path, max_workers: int = 3):
        self.output_dir = output_dir
        self.max_workers = max_workers
        self._provider_locks: dict[str, Lock] = {}
        self._manifest_lock = Lock()

    def create_job(
        self,
        name: str,
        pipeline: str,
        input_data: dict,
        steps: list[OrchestratorStep],
        job_id: str | None = None,
    ) -> OrchestratorJobManifest:
        resolved = job_id or uuid4().hex[:12]
        manifest = OrchestratorJobManifest(
            job_id=resolved,
            name=name,
            pipeline=pipeline,
            input_data=input_data,
            steps=[
                OrchestratorStepRecord(
                    id=step.id,
                    name=step.name,
                    dependencies=step.dependencies,
                    provider_key=step.provider_key,
                )
                for step in steps
            ],
        )
        self._save(manifest)
        return manifest

    def load_job(self, job_id: str) -> OrchestratorJobManifest:
        path = self._manifest_path(job_id)
        with self._manifest_lock:
            return OrchestratorJobManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def run(self, manifest: OrchestratorJobManifest, steps: list[OrchestratorStep]) -> OrchestratorJobManifest:
        steps_by_id = {step.id: step for step in steps}
        manifest.status = StepStatus.running
        self._save(manifest)
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {}
            while True:
                changed = False
                for record in manifest.steps:
                    if record.status != StepStatus.pending:
                        continue
                    if all(manifest.step(dep).status == StepStatus.complete for dep in record.dependencies):
                        step = steps_by_id[record.id]
                        record.status = StepStatus.running
                        changed = True
                        future = pool.submit(self._run_one, manifest.job_id, step)
                        futures[future] = record.id
                        if not step.allow_parallel:
                            break
                if changed:
                    self._save(manifest)
                if not futures:
                    break
                done, _pending = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    step_id = futures.pop(future)
                    updated = future.result()
                    current = manifest.step(step_id)
                    replacement = updated.step(step_id)
                    current.status = replacement.status
                    current.attempts = replacement.attempts
                    current.error = replacement.error
                    current.output_artifacts = replacement.output_artifacts
                    manifest.artifacts = updated.artifacts
                    manifest.total_cost = sum(item.cost or 0.0 for item in manifest.artifacts)
                    self._save(manifest)
                    if current.status == StepStatus.failed:
                        manifest.status = StepStatus.failed
                        self._save(manifest)
                        return manifest
        manifest.status = StepStatus.complete if all(step.status == StepStatus.complete for step in manifest.steps) else StepStatus.failed
        self._save(manifest)
        return manifest

    def _run_one(self, job_id: str, step: OrchestratorStep) -> OrchestratorJobManifest:
        manifest = self.load_job(job_id)
        record = manifest.step(step.id)
        context = OrchestratorContext(job_dir=self._job_dir(job_id), manifest=manifest, step=step)
        lock = self._provider_locks.setdefault(step.provider_key, Lock()) if step.provider_key else None
        for attempt in range(1, step.max_attempts + 1):
            record.attempts = attempt
            try:
                if lock:
                    with lock:
                        artifacts = step.handler(context)
                else:
                    artifacts = step.handler(context)
                record.status = StepStatus.complete
                record.error = None
                manifest.artifacts.extend(artifacts)
                record.output_artifacts = [artifact.id for artifact in artifacts]
                break
            except Exception as exc:
                record.error = str(exc)
                if attempt >= step.max_attempts:
                    record.status = StepStatus.failed
                else:
                    sleep(0.5 * attempt)
        self._save(manifest)
        return manifest

    def _job_dir(self, job_id: str) -> Path:
        return self.output_dir / "orchestrator" / job_id

    def _manifest_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job_manifest.json"

    def _save(self, manifest: OrchestratorJobManifest) -> None:
        with self._manifest_lock:
            path = self._manifest_path(manifest.job_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2), encoding="utf-8")
