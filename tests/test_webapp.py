"""Tests for the PaperBanana web application integration."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, Request
from PIL import Image
from pydantic import ValidationError

from paperbanana.core.types import PipelineProgressEvent, PipelineProgressStage
from webapp import main as webapp_main
from webapp.main import GenerateRequest, jobs, update_job_progress


async def _post_generate_asgi(body_chunks: list[bytes], headers: list[tuple[bytes, bytes]]):
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(body_chunks) - 1,
        }
        for index, chunk in enumerate(body_chunks)
    ]
    sent: list[dict] = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await webapp_main.app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/generate",
            "raw_path": b"/api/generate",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json"), *headers],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    return next(message["status"] for message in sent if message["type"] == "http.response.start")


async def test_generate_rejects_oversized_content_length_before_json_parsing(monkeypatch) -> None:
    monkeypatch.setattr(webapp_main, "MAX_REQUEST_BYTES", 32, raising=False)

    status = await _post_generate_asgi(
        [b"{}"],
        [(b"content-length", b"33")],
    )

    assert status == 413


async def test_generate_rejects_streamed_body_over_limit_before_json_parsing(monkeypatch) -> None:
    monkeypatch.setattr(webapp_main, "MAX_REQUEST_BYTES", 8)

    status = await _post_generate_asgi(
        [b"xxxxx", b"xxxx"],
        [],
    )

    assert status == 413


def test_update_job_progress_maps_visualizer_event() -> None:
    """Structured pipeline progress updates the web job shown to clients."""
    job_id = "job-1"
    jobs[job_id] = {
        "phase": "planning",
        "agent": None,
        "iteration": None,
        "progress": "Starting...",
    }
    event = PipelineProgressEvent(
        stage=PipelineProgressStage.VISUALIZER_START,
        message="Generating candidate image",
        iteration=2,
    )

    update_job_progress(job_id, event)

    assert jobs[job_id]["phase"] == "refinement"
    assert jobs[job_id]["agent"] == "visualizer"
    assert jobs[job_id]["iteration"] == 2
    assert jobs[job_id]["progress"] == "Generating candidate image"


def test_generate_request_rejects_oversized_text() -> None:
    """Generation inputs are bounded before an operator-funded job is queued."""
    with pytest.raises(ValidationError):
        GenerateRequest(text="x" * 40_001, caption="Diagram", iterations=1)


def test_generate_request_rejects_unknown_fields() -> None:
    """Oversized padding cannot hide in ignored JSON fields."""
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate(
            {
                "text": "method",
                "caption": "diagram",
                "iterations": 1,
                "unexpected_padding": "x",
            }
        )


def test_generation_limits_reject_when_capacity_is_full(monkeypatch) -> None:
    """No additional operator-funded job is accepted at global capacity."""
    jobs.clear()
    jobs["active-job"] = {"status": "running"}
    monkeypatch.setattr(webapp_main, "MAX_ACTIVE_JOBS", 1)

    with pytest.raises(HTTPException) as exc_info:
        webapp_main.enforce_generation_limits("client-1", now=100.0)

    assert exc_info.value.status_code == 429


async def test_queuing_job_reserves_space_within_stored_job_limit(monkeypatch) -> None:
    """Accepting a new job never grows in-memory state past its configured bound."""
    jobs.clear()
    webapp_main.global_request_history.clear()
    webapp_main.client_request_history.clear()
    monkeypatch.setattr(webapp_main, "MAX_STORED_JOBS", 3)
    monkeypatch.setattr(webapp_main, "MAX_ACTIVE_JOBS", 10)
    monkeypatch.setattr(webapp_main, "MAX_GLOBAL_REQUESTS_PER_HOUR", 10)
    monkeypatch.setattr(webapp_main, "MAX_CLIENT_REQUESTS_PER_HOUR", 10)
    for index in range(3):
        jobs[f"old-{index}"] = {
            "status": "completed",
            "finished_at": float(index),
        }
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/generate",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )

    await webapp_main.generate(
        GenerateRequest(text="method", caption="diagram", iterations=1),
        BackgroundTasks(),
        request,
    )

    assert len(jobs) == 3
    assert "old-0" not in jobs


async def test_queuing_rejects_when_stored_jobs_are_all_active(monkeypatch) -> None:
    """The total job registry remains bounded even when no terminal job is prunable."""
    jobs.clear()
    webapp_main.global_request_history.clear()
    webapp_main.client_request_history.clear()
    monkeypatch.setattr(webapp_main, "MAX_STORED_JOBS", 2)
    monkeypatch.setattr(webapp_main, "MAX_ACTIVE_JOBS", 10)
    monkeypatch.setattr(webapp_main, "MAX_GLOBAL_REQUESTS_PER_HOUR", 10)
    monkeypatch.setattr(webapp_main, "MAX_CLIENT_REQUESTS_PER_HOUR", 10)
    jobs["running"] = {"status": "running"}
    jobs["queued"] = {"status": "queued"}
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/generate",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await webapp_main.generate(
            GenerateRequest(text="method", caption="diagram", iterations=1),
            BackgroundTasks(),
            request,
        )

    assert exc_info.value.status_code == 429
    assert len(jobs) == 2


def test_generation_limits_enforce_global_hourly_cap(monkeypatch) -> None:
    """Accepted requests remain globally bounded even when clients rotate."""
    jobs.clear()
    webapp_main.global_request_history.clear()
    webapp_main.client_request_history.clear()
    monkeypatch.setattr(webapp_main, "MAX_ACTIVE_JOBS", 10)
    monkeypatch.setattr(webapp_main, "MAX_GLOBAL_REQUESTS_PER_HOUR", 2)
    monkeypatch.setattr(webapp_main, "MAX_CLIENT_REQUESTS_PER_HOUR", 2)

    webapp_main.enforce_generation_limits("client-1", now=100.0)
    webapp_main.enforce_generation_limits("client-2", now=101.0)
    with pytest.raises(HTTPException) as exc_info:
        webapp_main.enforce_generation_limits("client-3", now=102.0)

    assert exc_info.value.status_code == 429


def test_run_cleanup_enforces_ttl_quota_and_path_safety(monkeypatch, tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    def make_run(name: str, content: bytes, modified_at: float) -> Path:
        run_dir = runs_dir / name
        prompts_dir = run_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        (run_dir / "run_input.json").write_bytes(content)
        (prompts_dir / "planner.txt").write_bytes(content)
        for path in (run_dir / "run_input.json", prompts_dir / "planner.txt", prompts_dir, run_dir):
            os.utime(path, (modified_at, modified_at))
        return run_dir

    expired = make_run("run_expired", b"sensitive", 100.0)
    quota_oldest = make_run("run_quota_oldest", b"a" * 5, 380.0)
    quota_newest = make_run("run_quota_newest", b"b" * 5, 390.0)
    active = make_run("run_active", b"c" * 10, 370.0)
    outside = make_run("not_a_run", b"outside-secret", 50.0)
    escape = runs_dir / "run_escape"
    escape.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(webapp_main, "WEB_RUNS_DIR", runs_dir)
    monkeypatch.setattr(webapp_main, "WEB_RUN_TTL_SECONDS", 50.0)
    monkeypatch.setattr(webapp_main, "WEB_RUN_DISK_QUOTA_BYTES", 30)
    jobs.clear()
    jobs["active"] = {"status": "running", "run_dir": str(active)}

    webapp_main.cleanup_run_directories(now=400.0)

    assert not expired.exists()
    assert not quota_oldest.exists()
    assert quota_newest.exists()
    assert active.exists()
    assert outside.exists()
    assert (outside / "run_input.json").read_bytes() == b"outside-secret"
    assert escape.is_symlink()


async def test_periodic_run_cleanup_does_not_block_event_loop(monkeypatch) -> None:
    dispatched: list[object] = []
    sleeps = 0

    async def fake_sleep(_interval: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise StopAsyncIteration

    async def fake_to_thread(function, *args, **kwargs):
        dispatched.append(function)

    monkeypatch.setattr(webapp_main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(webapp_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(webapp_main, "cleanup_run_directories", lambda: None)

    with pytest.raises(StopAsyncIteration):
        await webapp_main._cleanup_run_directories_periodically()

    assert dispatched == [webapp_main.cleanup_run_directories]


async def test_startup_run_cleanup_does_not_block_event_loop(monkeypatch) -> None:
    dispatched: list[object] = []
    task_sentinel = object()

    async def fake_to_thread(function, *args, **kwargs):
        dispatched.append(function)

    def fake_create_task(coroutine):
        coroutine.close()
        return task_sentinel

    monkeypatch.setattr(webapp_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(webapp_main.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(webapp_main, "cleanup_run_directories", lambda: None)

    await webapp_main._start_run_cleanup()

    assert dispatched == [webapp_main.cleanup_run_directories]
    assert webapp_main._run_cleanup_task is task_sentinel


async def test_queued_job_does_not_retain_source_inputs(monkeypatch) -> None:
    """Long user inputs are passed to the task but not retained in global job state."""
    jobs.clear()
    webapp_main.global_request_history.clear()
    webapp_main.client_request_history.clear()
    monkeypatch.setattr(webapp_main, "MAX_ACTIVE_JOBS", 10)
    monkeypatch.setattr(webapp_main, "MAX_GLOBAL_REQUESTS_PER_HOUR", 10)
    monkeypatch.setattr(webapp_main, "MAX_CLIENT_REQUESTS_PER_HOUR", 10)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/generate",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )
    background_tasks = BackgroundTasks()

    response = await webapp_main.generate(
        GenerateRequest(text="method details", caption="diagram", iterations=1),
        background_tasks,
        request,
    )

    assert "text" not in jobs[response.job_id]
    assert "caption" not in jobs[response.job_id]
    assert len(background_tasks.tasks) == 1


async def test_job_budget_is_set_before_pipeline_initialization(monkeypatch, tmp_path) -> None:
    """The pipeline cost tracker receives the public job budget at construction time."""
    captured: dict[str, object] = {}

    def fake_settings():
        return SimpleNamespace(
            budget_usd=None,
            refinement_iterations=3,
            save_iterations=False,
        )

    class FakePipeline:
        def __init__(self, settings=None):
            captured["settings"] = settings
            self.settings = settings or fake_settings()

        async def generate(self, input_data, progress_callback=None):
            return SimpleNamespace(image_path=tmp_path / "final.png", iterations=[])

    monkeypatch.setattr(webapp_main, "Settings", fake_settings, raising=False)
    monkeypatch.setattr(webapp_main, "PaperBananaPipeline", FakePipeline)
    jobs.clear()
    jobs["budget-job"] = {"status": "queued"}

    await webapp_main.run_generation("budget-job", "source", "caption", 2)

    settings = captured["settings"]
    assert isinstance(settings, SimpleNamespace)
    assert settings.budget_usd == webapp_main.WEB_JOB_BUDGET_USD


@pytest.mark.parametrize("invalid_path", ["empty", "missing", "outside", "not-image"])
async def test_generation_fails_when_final_output_is_not_a_recorded_web_image(
    monkeypatch, tmp_path, invalid_path: str
) -> None:
    runs_dir = tmp_path / "web-runs"
    run_dir = runs_dir / "run_test"
    run_dir.mkdir(parents=True)
    if invalid_path == "empty":
        image_path: str | Path = ""
    elif invalid_path == "missing":
        image_path = run_dir / "missing.png"
    elif invalid_path == "outside":
        image_path = tmp_path / "outside.png"
        Path(image_path).write_bytes(b"outside")
    else:
        image_path = run_dir / "not-an-image.png"
        Path(image_path).write_text("not image data")

    def fake_settings():
        return SimpleNamespace(
            budget_usd=None,
            refinement_iterations=3,
            save_iterations=False,
        )

    class FakePipeline:
        def __init__(self, settings=None):
            self.settings = settings

        async def generate(self, input_data, progress_callback=None):
            return SimpleNamespace(image_path=image_path, iterations=[])

    monkeypatch.setattr(webapp_main, "WEB_RUNS_DIR", runs_dir)
    monkeypatch.setattr(webapp_main, "Settings", fake_settings)
    monkeypatch.setattr(webapp_main, "PaperBananaPipeline", FakePipeline)
    jobs.clear()
    jobs["invalid-output"] = {"status": "queued"}

    await webapp_main.run_generation("invalid-output", "source", "caption", 1)

    assert jobs["invalid-output"]["status"] == "failed"
    assert "final_image" not in jobs["invalid-output"]


async def test_image_endpoint_rejects_disguised_non_image(tmp_path) -> None:
    disguised = tmp_path / "final.png"
    disguised.write_text("<svg onload=alert(1)></svg>")
    jobs.clear()
    jobs["job-disguised"] = {
        "status": "completed",
        "run_dir": str(tmp_path),
        "final_image": str(disguised),
        "iteration_images": [],
    }

    with pytest.raises(HTTPException) as exc_info:
        await webapp_main.get_image("job-disguised", "final.png")

    assert exc_info.value.status_code == 404


async def test_image_endpoint_allows_only_recorded_images_with_correct_mime(tmp_path) -> None:
    """Result serving cannot expose metadata and identifies non-PNG output correctly."""
    final_image = tmp_path / "final.jpg"
    Image.new("RGB", (2, 2), color="white").save(final_image, format="JPEG")
    (tmp_path / "metadata.json").write_text('{"secret": "prompt"}')
    jobs.clear()
    jobs["job-images"] = {
        "status": "completed",
        "run_dir": str(tmp_path),
        "final_image": str(final_image),
        "iteration_images": [],
    }

    response = await webapp_main.get_image("job-images", "final.jpg")
    assert response.media_type == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"

    with pytest.raises(HTTPException) as exc_info:
        await webapp_main.get_image("job-images", "metadata.json")
    assert exc_info.value.status_code == 404


def test_frontend_renders_errors_as_text() -> None:
    """Provider errors cannot inject HTML into the public page."""
    html_path = Path(webapp_main.__file__).parent / "static" / "index.html"
    html = html_path.read_text(encoding="utf-8")
    show_error = html.split("function showError(message)", 1)[1].split(
        "async function downloadFinalImage", 1
    )[0]

    assert ".textContent = message" in show_error
    assert "innerHTML" not in show_error


def test_wheel_configuration_includes_webapp() -> None:
    """Non-editable installs contain the FastAPI application and static frontend."""
    pyproject = (Path(webapp_main.__file__).parents[1] / "pyproject.toml").read_text()
    assert 'packages = ["paperbanana", "mcp_server", "webapp"]' in pyproject
