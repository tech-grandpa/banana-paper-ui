"""FastAPI web UI for PaperBanana text-to-diagram generation."""

import asyncio
import contextlib
import os
import shutil
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Optional

import structlog
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from paperbanana import PaperBananaPipeline
from paperbanana.core.config import Settings
from paperbanana.core.types import GenerationInput, PipelineProgressEvent

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

MAX_TEXT_CHARS = int(os.getenv("WEB_MAX_TEXT_CHARS", "40000"))
MAX_CAPTION_CHARS = int(os.getenv("WEB_MAX_CAPTION_CHARS", "2000"))
MAX_REQUEST_BYTES = int(os.getenv("WEB_MAX_REQUEST_BYTES", "262144"))
MAX_ACTIVE_JOBS = int(os.getenv("WEB_MAX_ACTIVE_JOBS", "1"))
MAX_GLOBAL_REQUESTS_PER_HOUR = int(os.getenv("WEB_MAX_GLOBAL_REQUESTS_PER_HOUR", "4"))
MAX_CLIENT_REQUESTS_PER_HOUR = int(os.getenv("WEB_MAX_CLIENT_REQUESTS_PER_HOUR", "2"))
MAX_STORED_JOBS = int(os.getenv("WEB_MAX_STORED_JOBS", "100"))
WEB_JOB_BUDGET_USD = float(os.getenv("WEB_JOB_BUDGET_USD", "1.00"))
WEB_RUNS_DIR = Path(os.getenv("WEB_RUNS_DIR", "outputs/web")).expanduser().resolve()
WEB_RUN_TTL_SECONDS = float(os.getenv("WEB_RUN_TTL_SECONDS", "86400"))
WEB_RUN_DISK_QUOTA_BYTES = int(os.getenv("WEB_RUN_DISK_QUOTA_BYTES", "1073741824"))
WEB_RUN_CLEANUP_INTERVAL_SECONDS = float(os.getenv("WEB_RUN_CLEANUP_INTERVAL_SECONDS", "300"))
TRUST_PROXY_HEADERS = os.getenv("WEB_TRUST_PROXY_HEADERS", "false").lower() in {
    "1",
    "true",
    "yes",
}
RATE_WINDOW_SECONDS = 3600.0


class RequestBodyLimitMiddleware:
    """Reject oversized generation bodies before FastAPI buffers or parses JSON."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/api/generate"
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received_bytes = 0
        buffered_messages: deque[Message] = deque()
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message["type"] != "http.request":
                break
            received_bytes += len(message.get("body", b""))
            if received_bytes > MAX_REQUEST_BYTES:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if buffered_messages:
                return buffered_messages.popleft()
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"detail": "Request body too large"},
            status_code=413,
        )
        await response(scope, receive, send)


app = FastAPI(title="PaperBanana Web UI")
app.add_middleware(RequestBodyLimitMiddleware)

# Bounded in-memory job and rate-limit state.
jobs: Dict[str, dict] = {}
global_request_history: deque[float] = deque()
client_request_history: dict[str, deque[float]] = defaultdict(deque)
_run_cleanup_task: asyncio.Task[None] | None = None


class GenerateRequest(BaseModel):
    """Request model for diagram generation."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_CHARS,
        description="Source context / methodology description",
    )
    caption: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CAPTION_CHARS,
        description="Communicative intent / caption",
    )
    iterations: int = Field(3, ge=1, le=5, description="Number of refinement iterations")


class GenerateResponse(BaseModel):
    """Response model for generation request."""

    job_id: str
    status: str = "queued"


class StatusResponse(BaseModel):
    """Response model for job status."""

    job_id: str
    status: str  # queued, running, completed, failed
    phase: Optional[str] = None  # planning, refinement
    agent: Optional[str] = None  # retriever, planner, stylist, visualizer, critic
    iteration: Optional[int] = None  # current iteration number
    total_iterations: Optional[int] = None
    progress: Optional[str] = None  # human-readable progress message
    error: Optional[str] = None


class ResultResponse(BaseModel):
    """Response model for completed job result."""

    job_id: str
    status: str
    final_image: Optional[str] = None  # URL to final image
    iteration_images: list[str] = Field(default_factory=list)  # URLs to all iteration images
    error: Optional[str] = None


def _safe_run_directories(root: Path) -> list[Path]:
    """Return direct, real run directories without following symlinks."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dirs: list[Path] = []
    for candidate in root.iterdir():
        if not candidate.name.startswith("run_") or candidate.is_symlink():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.parent == root and resolved.is_dir():
            run_dirs.append(resolved)
    return run_dirs


def _run_disk_usage(run_dir: Path) -> tuple[int, float]:
    """Return file bytes and newest mtime without traversing symlinks."""
    size = 0
    newest_mtime = run_dir.stat().st_mtime
    for directory, dirnames, filenames in os.walk(run_dir, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = [name for name in dirnames if not (directory_path / name).is_symlink()]
        for filename in filenames:
            path = directory_path / filename
            try:
                stat = path.stat(follow_symlinks=False)
            except OSError:
                continue
            if path.is_symlink():
                continue
            size += stat.st_size
            newest_mtime = max(newest_mtime, stat.st_mtime)
    return size, newest_mtime


def _protected_run_directories(root: Path) -> tuple[set[Path], float | None]:
    protected: set[Path] = set()
    active_started_at: list[float] = []
    for job in jobs.values():
        if job.get("status") not in {"queued", "running"}:
            continue
        started_at = job.get("started_at_wall")
        if isinstance(started_at, (int, float)):
            active_started_at.append(float(started_at))
        run_dir = job.get("run_dir")
        if not run_dir:
            continue
        try:
            resolved = Path(run_dir).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.parent == root and resolved.is_dir():
            protected.add(resolved)
    return protected, min(active_started_at, default=None)


def _forget_deleted_run(run_dir: Path) -> None:
    for job_id, job in list(jobs.items()):
        recorded_run_dir = job.get("run_dir")
        if not recorded_run_dir:
            continue
        try:
            if Path(recorded_run_dir).resolve() == run_dir:
                jobs.pop(job_id, None)
        except (OSError, RuntimeError):
            continue


def _delete_run_directory(run_dir: Path, root: Path) -> bool:
    """Delete one contained run directory, defending against path escapes."""
    try:
        resolved = run_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if run_dir.is_symlink() or resolved.parent != root or not resolved.is_dir():
        logger.warning("Skipping unsafe run cleanup path", path=str(run_dir))
        return False
    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        logger.warning("Failed to delete expired run", path=str(resolved), error=str(exc))
        return False
    _forget_deleted_run(resolved)
    return True


def cleanup_run_directories(now: float | None = None) -> None:
    """Delete expired runs, then oldest runs until the disk quota is met."""
    now = time.time() if now is None else now
    root = WEB_RUNS_DIR.expanduser().resolve()
    run_stats = {run_dir: _run_disk_usage(run_dir) for run_dir in _safe_run_directories(root)}
    protected, active_started_at = _protected_run_directories(root)

    def is_protected(run_dir: Path, newest_mtime: float) -> bool:
        return run_dir in protected or (
            active_started_at is not None and newest_mtime >= active_started_at
        )

    for run_dir, (_, newest_mtime) in sorted(run_stats.items(), key=lambda item: item[1][1]):
        if now - newest_mtime < WEB_RUN_TTL_SECONDS or is_protected(run_dir, newest_mtime):
            continue
        if _delete_run_directory(run_dir, root):
            run_stats.pop(run_dir)

    total_bytes = sum(size for size, _ in run_stats.values())
    for run_dir, (size, newest_mtime) in sorted(run_stats.items(), key=lambda item: item[1][1]):
        if total_bytes <= WEB_RUN_DISK_QUOTA_BYTES:
            break
        if is_protected(run_dir, newest_mtime):
            continue
        if _delete_run_directory(run_dir, root):
            total_bytes -= size

    if total_bytes > WEB_RUN_DISK_QUOTA_BYTES:
        logger.warning(
            "Web run disk quota exceeded by protected runs",
            used_bytes=total_bytes,
            quota_bytes=WEB_RUN_DISK_QUOTA_BYTES,
        )


async def _cleanup_run_directories_periodically() -> None:
    while True:
        await asyncio.sleep(WEB_RUN_CLEANUP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(cleanup_run_directories)
        except Exception:
            logger.exception("Periodic web run cleanup failed")


async def _start_run_cleanup() -> None:
    global _run_cleanup_task
    await asyncio.to_thread(cleanup_run_directories)
    _run_cleanup_task = asyncio.create_task(_cleanup_run_directories_periodically())


async def _stop_run_cleanup() -> None:
    global _run_cleanup_task
    if _run_cleanup_task is None:
        return
    _run_cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _run_cleanup_task
    _run_cleanup_task = None


app.router.add_event_handler("startup", _start_run_cleanup)
app.router.add_event_handler("shutdown", _stop_run_cleanup)


def _trim_request_history(history: deque[float], now: float) -> None:
    cutoff = now - RATE_WINDOW_SECONDS
    while history and history[0] <= cutoff:
        history.popleft()


def prune_jobs(reserved_slots: int = 0) -> None:
    """Keep in-memory state bounded while reserving room for newly accepted jobs."""
    target_size = max(MAX_STORED_JOBS - reserved_slots, 0)
    overflow = len(jobs) - target_size
    if overflow <= 0:
        return
    terminal = sorted(
        (
            (job.get("finished_at", job.get("created_at", 0.0)), job_id)
            for job_id, job in jobs.items()
            if job.get("status") in {"completed", "failed"}
        ),
        key=lambda item: item[0],
    )
    for _, job_id in terminal[:overflow]:
        jobs.pop(job_id, None)


def _client_id(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
            "x-forwarded-for"
        )
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_generation_limits(client_id: str, now: float | None = None) -> None:
    """Apply global capacity and hourly rate limits before accepting a job."""
    now = time.monotonic() if now is None else now
    prune_jobs(reserved_slots=1)
    if len(jobs) >= MAX_STORED_JOBS:
        raise HTTPException(
            status_code=429,
            detail="Job storage capacity reached. Please try again later.",
        )

    active_jobs = sum(job.get("status") in {"queued", "running"} for job in jobs.values())
    if active_jobs >= MAX_ACTIVE_JOBS:
        raise HTTPException(status_code=429, detail="Generator is busy; please try again later")

    _trim_request_history(global_request_history, now)
    for known_client, history in list(client_request_history.items()):
        _trim_request_history(history, now)
        if not history:
            client_request_history.pop(known_client, None)
    client_history = client_request_history[client_id]

    if len(global_request_history) >= MAX_GLOBAL_REQUESTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Hourly generation limit reached")
    if len(client_history) >= MAX_CLIENT_REQUESTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Client hourly generation limit reached")

    global_request_history.append(now)
    client_history.append(now)


_PROGRESS_AGENTS = {
    "optimizer": ("planning", "optimizer"),
    "retriever": ("planning", "retriever"),
    "planner": ("planning", "planner"),
    "stylist": ("planning", "stylist"),
    "structurer": ("planning", "structurer"),
    "visualizer": ("refinement", "visualizer"),
    "critic": ("refinement", "critic"),
    "caption": ("finalizing", "caption"),
    "tikz_exporter": ("finalizing", "tikz_exporter"),
}


def update_job_progress(job_id: str, event: PipelineProgressEvent) -> None:
    """Translate structured pipeline progress into the web API job state."""
    job = jobs.get(job_id)
    if job is None:
        return

    stage_name = event.stage.value
    agent_name = stage_name.removesuffix("_start").removesuffix("_end")
    phase, agent = _PROGRESS_AGENTS.get(agent_name, (job.get("phase"), agent_name))
    job["phase"] = phase
    job["agent"] = agent
    job["progress"] = event.message
    if event.iteration is not None:
        job["iteration"] = event.iteration


def _verified_image_media_type(image_path: Path) -> str:
    """Validate an allowed raster image and return its explicit media type."""
    image_type = {
        ".png": ("image/png", "PNG"),
        ".jpg": ("image/jpeg", "JPEG"),
        ".jpeg": ("image/jpeg", "JPEG"),
        ".webp": ("image/webp", "WEBP"),
    }.get(image_path.suffix.lower())
    if image_type is None:
        raise ValueError("Unsupported image type")
    media_type, expected_format = image_type
    try:
        with Image.open(image_path) as image:
            actual_format = image.format
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Invalid image data") from exc
    if actual_format != expected_format:
        raise ValueError("Image content does not match its extension")
    return media_type


def _validated_web_output(image_path: object) -> tuple[Path, Path]:
    """Return a real final image and its direct, contained web run directory."""
    if not isinstance(image_path, (str, os.PathLike)) or not image_path:
        raise ValueError("Pipeline returned no final image")

    root = WEB_RUNS_DIR.expanduser().resolve()
    resolved_image = Path(image_path).expanduser().resolve(strict=True)
    if not resolved_image.is_file():
        raise ValueError("Pipeline final image is not a file")
    try:
        relative_image = resolved_image.relative_to(root)
    except ValueError as exc:
        raise ValueError("Pipeline final image is outside the web runs directory") from exc
    if len(relative_image.parts) < 2 or not relative_image.parts[0].startswith("run_"):
        raise ValueError("Pipeline final image is not inside a dedicated run directory")

    run_dir = (root / relative_image.parts[0]).resolve(strict=True)
    if run_dir.parent != root or not run_dir.is_dir() or not run_dir.name.startswith("run_"):
        raise ValueError("Pipeline run directory is invalid")
    _verified_image_media_type(resolved_image)
    return resolved_image, run_dir


async def run_generation(job_id: str, text: str, caption: str, iterations: int):
    """Background task to run the PaperBanana generation pipeline."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at_wall"] = time.time()
        jobs[job_id]["phase"] = "initialization"
        jobs[job_id]["progress"] = "Initializing pipeline..."

        logger.info("Starting generation", job_id=job_id)

        settings = Settings()
        settings.refinement_iterations = iterations
        settings.save_iterations = True
        settings.output_dir = str(WEB_RUNS_DIR)
        settings.budget_usd = (
            WEB_JOB_BUDGET_USD
            if settings.budget_usd is None
            else min(settings.budget_usd, WEB_JOB_BUDGET_USD)
        )
        pipeline = PaperBananaPipeline(settings=settings)

        input_data = GenerationInput(
            source_context=text,
            communicative_intent=caption,
        )

        jobs[job_id]["total_iterations"] = iterations
        output = await pipeline.generate(
            input_data,
            progress_callback=lambda event: update_job_progress(job_id, event),
        )

        final_image, run_dir = _validated_web_output(output.image_path)

        # Store results only after validating the pipeline's final artifact.
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["phase"] = "completed"
        jobs[job_id]["progress"] = "Generation completed!"
        jobs[job_id]["final_image"] = str(final_image)
        jobs[job_id]["iteration_images"] = [str(it.image_path) for it in output.iterations]
        jobs[job_id]["run_dir"] = str(run_dir)
        jobs[job_id]["finished_at"] = time.monotonic()
        prune_jobs()

        logger.info("Generation completed", job_id=job_id)

    except Exception as exc:
        logger.error("Generation failed", job_id=job_id, error=str(exc))
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["phase"] = "failed"
        jobs[job_id]["error"] = "Generation failed. Please try again later."
        jobs[job_id]["finished_at"] = time.monotonic()
        prune_jobs()


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
):
    """Start a new diagram generation job within configured safety limits."""
    enforce_generation_limits(_client_id(http_request))
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "iterations": request.iterations,
        "created_at": time.monotonic(),
        "phase": None,
        "agent": None,
        "iteration": None,
        "total_iterations": request.iterations,
        "progress": "Job queued...",
        "final_image": None,
        "iteration_images": [],
        "error": None,
    }

    # Schedule background task
    background_tasks.add_task(
        run_generation, job_id, request.text, request.caption, request.iterations
    )

    return GenerateResponse(job_id=job_id, status="queued")


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Get the status of a generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return StatusResponse(
        job_id=job_id,
        status=job["status"],
        phase=job.get("phase"),
        agent=job.get("agent"),
        iteration=job.get("iteration"),
        total_iterations=job.get("total_iterations"),
        progress=job.get("progress"),
        error=job.get("error"),
    )


@app.get("/api/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """Get the result of a completed generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job["status"] not in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Job not yet completed")

    # Convert file paths to URLs
    final_image_url = None
    iteration_image_urls = []

    if job["status"] == "completed":
        if job.get("final_image"):
            filename = Path(job["final_image"]).name
            final_image_url = f"/api/result/{job_id}/image/{filename}"

        for img_path in job.get("iteration_images", []):
            filename = Path(img_path).name
            iteration_image_urls.append(f"/api/result/{job_id}/image/{filename}")

    return ResultResponse(
        job_id=job_id,
        status=job["status"],
        final_image=final_image_url,
        iteration_images=iteration_image_urls,
        error=job.get("error"),
    )


@app.get("/api/result/{job_id}/image/{filename}")
async def get_image(job_id: str, filename: str):
    """Serve an individual image file from a job's output directory."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if "run_dir" not in job:
        raise HTTPException(status_code=404, detail="Job output directory not found")

    run_dir = Path(job["run_dir"]).resolve()
    recorded_images = [job.get("final_image"), *job.get("iteration_images", [])]
    image_path = next(
        (Path(path).resolve() for path in recorded_images if path and Path(path).name == filename),
        None,
    )

    if image_path is None or not image_path.is_relative_to(run_dir) or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        media_type = _verified_image_media_type(image_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc

    return FileResponse(
        image_path,
        media_type=media_type,
        filename=image_path.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend HTML."""
    html_path = Path(__file__).parent / "static" / "index.html"

    if not html_path.exists():
        return HTMLResponse(
            content=(
                "<h1>PaperBanana Web UI</h1>"
                "<p>Frontend not found. Please create webapp/static/index.html</p>"
            ),
            status_code=404,
        )

    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read())


# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
