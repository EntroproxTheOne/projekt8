from pathlib import Path

from video_pipeline.models import ArtifactKind, ArtifactRecord, StepStatus
from video_pipeline.orchestrator import Orchestrator, OrchestratorContext, OrchestratorStep


def test_orchestrator_runs_dependencies_and_saves_artifacts(tmp_path: Path):
    order = []

    def first(context: OrchestratorContext):
        order.append("first")
        return [ArtifactRecord(id="a", kind=ArtifactKind.text, data={"ok": True})]

    def second(context: OrchestratorContext):
        order.append("second")
        return [ArtifactRecord(id="b", kind=ArtifactKind.metadata, cost=0.5)]

    steps = [
        OrchestratorStep("first", "First", first),
        OrchestratorStep("second", "Second", second, dependencies=["first"]),
    ]
    orchestrator = Orchestrator(tmp_path)
    manifest = orchestrator.create_job("job", "test", {}, steps)
    result = orchestrator.run(manifest, steps)

    assert result.status == StepStatus.complete
    assert order == ["first", "second"]
    assert result.total_cost == 0.5
    assert (tmp_path / "orchestrator" / manifest.job_id / "job_manifest.json").exists()


def test_orchestrator_retries_failed_step(tmp_path: Path):
    calls = {"count": 0}

    def flaky(context: OrchestratorContext):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return [ArtifactRecord(id="ok", kind=ArtifactKind.text)]

    steps = [OrchestratorStep("flaky", "Flaky", flaky, max_attempts=2)]
    orchestrator = Orchestrator(tmp_path)
    manifest = orchestrator.create_job("job", "test", {}, steps)
    result = orchestrator.run(manifest, steps)

    assert result.status == StepStatus.complete
    assert result.step("flaky").attempts == 2
