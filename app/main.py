"""Main FastAPI application for FlowOps.

Provides HTTP routes for triggering pipelines, querying run status,
serving the static dashboard UI, and exporting operational health metrics.
"""

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .schemas import (
    HealthResponse,
    PipelineDetails,
    PipelineRequest,
    PipelineStatus,
    PipelineSummary,
    RunAccepted,
)
from .store import PipelineStore
from .workflow import execute
from .config import settings

# Configure standard application logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("flowops")

# Global instances for pipeline state storage and operational counters
store = PipelineStore()
metrics = {
    "pipelines_started": 0,
    "pipelines_succeeded": 0,
    "pipelines_failed": 0,
}


async def run_pipeline(pid: UUID, request: PipelineRequest) -> None:
    """Asynchronously executes a pipeline run and updates store state.

    This worker is launched in the background upon receiving a run request.
    It transitions the pipeline through running, intermediate stages,
    and records the final outcome (succeeded or failed).
    """
    await store.update(pid, status=PipelineStatus.running)
    try:
        # Callback to update the store as each stage finishes
        async def stage_update(stage: str, _state: dict) -> None:
            stage_progress = {
                "ingestion": 20,
                "transformation": 45,
                "validation": 70,
                "evaluation": 90,
            }.get(stage, 50)

            current_item = await store.get(pid)
            history = current_item.stage_history if current_item else []

            await store.update(
                pid,
                current_stage=stage,
                progress=stage_progress,
                stage_history=history + [stage],
            )

        # Run the workflow graph
        result = await execute(request.source, request.text, stage_update)

        # Record successful completion
        item = await store.get(pid)
        history = item.stage_history if item else []
        await store.update(
            pid,
            status=PipelineStatus.succeeded,
            current_stage="completed",
            progress=100,
            stage_history=history + ["completed"],
            result=result,
        )
        metrics["pipelines_succeeded"] += 1

    except Exception as exc:
        # Record failure and log the traceback
        logger.exception("Pipeline execution failed", extra={"pipeline_id": str(pid)})
        await store.update(
            pid,
            status=PipelineStatus.failed,
            current_stage="failed",
            error=str(exc),
        )
        metrics["pipelines_failed"] += 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown hooks."""
    yield


app = FastAPI(title="FlowOps API", version="0.1.0", lifespan=lifespan)
ROOT = Path(__file__).resolve().parent.parent

# Serve static frontend assets (HTML, CSS, icons)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serves the single-page dashboard HTML."""
    return HTMLResponse((ROOT / "static" / "index.html").read_text())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the website favicon."""
    return FileResponse(ROOT / "static" / "favicon.svg", media_type="image/svg+xml")


@app.post("/pipelines/run", response_model=RunAccepted, status_code=202)
async def start_pipeline(request: PipelineRequest, http_request: Request):
    """Queues a new pipeline run and starts processing in the background.

    Returns HTTP 202 with tracking information so the client can poll
    for status updates without blocking.
    """
    if not request.input_text.strip() and request.source == "inline":
        raise HTTPException(status_code=422, detail="Add CSV data before starting a run.")

    pid = uuid4()
    await store.create(pid, request)
    metrics["pipelines_started"] += 1

    # Fire and forget: the task runs asynchronously in the event loop
    asyncio.create_task(run_pipeline(pid, request))

    return RunAccepted(
        tracking_id=pid,
        pipeline_id=pid,
        status=PipelineStatus.queued,
        status_url=str(http_request.url_for("get_pipeline", pipeline_id=pid)),
    )


@app.get("/pipelines", response_model=list[PipelineSummary])
async def list_pipelines():
    """Returns a list of all recorded pipeline runs."""
    return await store.list()


@app.get("/pipelines/{pipeline_id}", response_model=PipelineDetails, name="get_pipeline")
async def get_pipeline(pipeline_id: UUID):
    """Returns detailed status and results for a specific pipeline ID."""
    item = await store.get(pipeline_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return item


@app.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: UUID):
    """Deletes a pipeline run record from storage and updates metric counters."""
    item = await store.get(pipeline_id)
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    await store.delete(pipeline_id)

    if metrics["pipelines_started"] > 0:
        metrics["pipelines_started"] -= 1
    if item.status == PipelineStatus.succeeded and metrics["pipelines_succeeded"] > 0:
        metrics["pipelines_succeeded"] -= 1
    elif item.status == PipelineStatus.failed and metrics["pipelines_failed"] > 0:
        metrics["pipelines_failed"] -= 1


@app.get("/health", response_model=HealthResponse)
async def health():
    """Liveness probe: verifies the API process is responsive."""
    return {"status": "ok"}


@app.get("/ready", response_model=HealthResponse)
async def ready():
    """Readiness probe: indicates the service is ready to accept traffic."""
    return {"status": "ready"}


@app.get("/metrics")
async def get_metrics():
    """Returns operational run counts and statistics."""
    runs = await store.list()
    return {
        "pipelines_started": len(runs),
        "pipelines_succeeded": sum(1 for r in runs if r.status == PipelineStatus.succeeded),
        "pipelines_failed": sum(1 for r in runs if r.status == PipelineStatus.failed),
    }
