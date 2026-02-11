"""FastAPI web UI for PaperBanana text-to-diagram generation."""

import asyncio
import uuid
from pathlib import Path
from typing import Dict, Optional

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from paperbanana import PaperBananaPipeline
from paperbanana.core.types import DiagramType, GenerationInput

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

app = FastAPI(title="PaperBanana Web UI")

# Job storage (in-memory)
jobs: Dict[str, dict] = {}


class GenerateRequest(BaseModel):
    """Request model for diagram generation."""
    text: str = Field(..., description="Source context / methodology description")
    caption: str = Field(..., description="Communicative intent / caption")
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
    iteration_images: list[str] = []  # URLs to all iteration images
    error: Optional[str] = None


async def run_generation(job_id: str, text: str, caption: str, iterations: int):
    """Background task to run the PaperBanana generation pipeline."""
    try:
        # Update job status
        jobs[job_id]["status"] = "running"
        jobs[job_id]["phase"] = "initialization"
        jobs[job_id]["progress"] = "Initializing pipeline..."
        
        logger.info("Starting generation", job_id=job_id)
        
        # Initialize pipeline
        pipeline = PaperBananaPipeline()
        
        # Create input
        input_data = GenerationInput(
            source_context=text,
            communicative_intent=caption,
        )
        
        # Update settings for iterations
        pipeline.settings.refinement_iterations = iterations
        pipeline.settings.save_iterations = True
        
        # Track progress by monkey-patching the pipeline methods
        original_retriever_run = pipeline.retriever.run
        original_planner_run = pipeline.planner.run
        original_stylist_run = pipeline.stylist.run
        original_visualizer_run = pipeline.visualizer.run
        original_critic_run = pipeline.critic.run
        
        async def tracked_retriever_run(*args, **kwargs):
            jobs[job_id]["phase"] = "planning"
            jobs[job_id]["agent"] = "retriever"
            jobs[job_id]["progress"] = "Retrieving relevant examples..."
            return await original_retriever_run(*args, **kwargs)
        
        async def tracked_planner_run(*args, **kwargs):
            jobs[job_id]["agent"] = "planner"
            jobs[job_id]["progress"] = "Generating textual description..."
            return await original_planner_run(*args, **kwargs)
        
        async def tracked_stylist_run(*args, **kwargs):
            jobs[job_id]["agent"] = "stylist"
            jobs[job_id]["progress"] = "Optimizing description aesthetics..."
            return await original_stylist_run(*args, **kwargs)
        
        async def tracked_visualizer_run(*args, **kwargs):
            iteration = kwargs.get("iteration", 1)
            jobs[job_id]["phase"] = "refinement"
            jobs[job_id]["agent"] = "visualizer"
            jobs[job_id]["iteration"] = iteration
            jobs[job_id]["progress"] = f"Generating image (iteration {iteration}/{iterations})..."
            return await original_visualizer_run(*args, **kwargs)
        
        async def tracked_critic_run(*args, **kwargs):
            iteration = jobs[job_id].get("iteration", 1)
            jobs[job_id]["agent"] = "critic"
            jobs[job_id]["progress"] = f"Evaluating image (iteration {iteration}/{iterations})..."
            return await original_critic_run(*args, **kwargs)
        
        # Apply tracking wrappers
        pipeline.retriever.run = tracked_retriever_run
        pipeline.planner.run = tracked_planner_run
        pipeline.stylist.run = tracked_stylist_run
        pipeline.visualizer.run = tracked_visualizer_run
        pipeline.critic.run = tracked_critic_run
        
        # Run generation
        jobs[job_id]["total_iterations"] = iterations
        output = await pipeline.generate(input_data)
        
        # Store results
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["phase"] = "completed"
        jobs[job_id]["progress"] = "Generation completed!"
        jobs[job_id]["final_image"] = str(output.image_path)
        jobs[job_id]["iteration_images"] = [str(it.image_path) for it in output.iterations]
        jobs[job_id]["run_dir"] = str(getattr(pipeline, '_run_dir', output.metadata.get('run_dir', '')))
        
        logger.info("Generation completed", job_id=job_id)
        
    except Exception as e:
        logger.error("Generation failed", job_id=job_id, error=str(e))
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Start a new diagram generation job."""
    job_id = str(uuid.uuid4())
    
    # Initialize job entry
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "text": request.text,
        "caption": request.caption,
        "iterations": request.iterations,
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
        run_generation,
        job_id,
        request.text,
        request.caption,
        request.iterations
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
    
    image_path = Path(job["run_dir"]) / filename
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(image_path, media_type="image/png")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend HTML."""
    html_path = Path(__file__).parent / "static" / "index.html"
    
    if not html_path.exists():
        return HTMLResponse(
            content="<h1>PaperBanana Web UI</h1><p>Frontend not found. Please create webapp/static/index.html</p>",
            status_code=404
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
