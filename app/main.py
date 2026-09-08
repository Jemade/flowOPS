import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .schemas import *
from .store import PipelineStore
from .workflow import execute
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
store = PipelineStore()
metrics = {"pipelines_started": 0, "pipelines_succeeded": 0, "pipelines_failed": 0}


async def run_pipeline(pid: UUID, request: PipelineRequest):
    await store.update(pid, status=PipelineStatus.running)
    try:
        async def stage_update(stage, _state):
            await store.update(pid, current_stage=stage, progress={"ingestion": 20,
                "transformation": 45, "validation": 70, "evaluation": 90}[stage],
                stage_history=(await store.get(pid)).stage_history + [stage])
        result = await execute(request.source, request.text, stage_update)
        item = await store.get(pid)
        await store.update(pid, status=PipelineStatus.succeeded, current_stage="completed",
                           progress=100, stage_history=item.stage_history + ["completed"], result=result)
        metrics["pipelines_succeeded"] += 1
    except Exception as exc:
        logging.getLogger("flowops").exception("pipeline failed", extra={"pipeline_id": str(pid)})
        await store.update(pid, status=PipelineStatus.failed, current_stage="failed", error=str(exc))
        metrics["pipelines_failed"] += 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="FlowOps API", version="0.1.0", lifespan=lifespan)
ROOT = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse((ROOT / "static" / "index.html").read_text())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(ROOT / "static" / "favicon.svg", media_type="image/svg+xml")


@app.post("/pipelines/run", response_model=RunAccepted, status_code=202)
async def start_pipeline(request: PipelineRequest, http_request: Request):
    if not request.input_text.strip() and request.source == "inline":
        raise HTTPException(422, "Add CSV data before starting a run.")
    pid = uuid4()
    await store.create(pid, request)
    metrics["pipelines_started"] += 1
    asyncio.create_task(run_pipeline(pid, request))
    return RunAccepted(tracking_id=pid, pipeline_id=pid, status=PipelineStatus.queued,
                       status_url=str(http_request.url_for("get_pipeline", pipeline_id=pid)))


@app.get("/pipelines", response_model=list[PipelineSummary])
async def list_pipelines():
    return await store.list()


@app.get("/pipelines/{pipeline_id}", response_model=PipelineDetails, name="get_pipeline")
async def get_pipeline(pipeline_id: UUID):
    item = await store.get(pipeline_id)
    if not item:
        raise HTTPException(404, "Pipeline not found")
    return item


@app.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: UUID):
    item = await store.get(pipeline_id)
    if not item:
        raise HTTPException(404, "Pipeline not found")
    await store.delete(pipeline_id)
    if metrics["pipelines_started"] > 0:
        metrics["pipelines_started"] -= 1
    if item.status == PipelineStatus.succeeded and metrics["pipelines_succeeded"] > 0:
        metrics["pipelines_succeeded"] -= 1
    elif item.status == PipelineStatus.failed and metrics["pipelines_failed"] > 0:
        metrics["pipelines_failed"] -= 1


@app.get("/health", response_model=HealthResponse)
async def health(): return {"status": "ok"}


@app.get("/ready", response_model=HealthResponse)
async def ready(): return {"status": "ready"}


@app.get("/metrics")
async def get_metrics():
    runs = await store.list()
    return {
        "pipelines_started": len(runs),
        "pipelines_succeeded": sum(1 for r in runs if r.status == PipelineStatus.succeeded),
        "pipelines_failed": sum(1 for r in runs if r.status == PipelineStatus.failed),
    }
