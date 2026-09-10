"""Integration test suite for the FlowOps API.

Validates the full pipeline execution lifecycle, HTTP contracts,
metrics accounting, and dashboard static file serving.
"""

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app, store
from app import workflow


@pytest.mark.asyncio
async def test_run_and_status():
    """Verify that a pipeline run transitions through all stages to completion."""
    store.items.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/pipelines/run", json={"name": "test", "source": "demo"})
        assert response.status_code == 202

        pid = response.json()["tracking_id"]

        # Poll until the background task completes
        for _ in range(20):
            item = (await c.get(f"/pipelines/{pid}")).json()
            if item["status"] == "succeeded":
                break
            await asyncio.sleep(0.01)

        assert item["status"] == "succeeded"
        assert item["result"]["evaluation"]["score"] == 1.0
        assert item["current_stage"] == "completed"
        assert item["progress"] == 100
        assert item["stage_history"] == [
            "queued",
            "ingestion",
            "transformation",
            "validation",
            "evaluation",
            "completed",
        ]


@pytest.mark.asyncio
async def test_canonical_text_contract():
    """Verify processing with inline CSV text input and type conversion."""
    store.items.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/pipelines/run", json={"text": "id,value\n1,42\n"})
        assert response.status_code == 202

        body = response.json()
        assert body["status"] == "queued"
        assert body["tracking_id"]

        item = (await c.get(f"/pipelines/{body['tracking_id']}")).json()
        for _ in range(30):
            if item["status"] == "succeeded":
                break
            await asyncio.sleep(0.01)
            item = (await c.get(f"/pipelines/{body['tracking_id']}")).json()

        assert item["status"] == "succeeded"
        # Confirm string '42' was converted to integer 42
        assert item["result"]["rows"][0]["value"] == 42


@pytest.mark.asyncio
async def test_health():
    """Verify that the health check endpoint returns an HTTP 200 OK."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/health")).json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_execute_uses_compiled_langgraph(monkeypatch):
    """Verify that execute() calls the LangGraph compilation factory."""
    called = False
    original = workflow.build_workflow

    def wrapped(callback=None):
        nonlocal called
        called = True
        return original(callback)

    monkeypatch.setattr(workflow, "build_workflow", wrapped)
    result = await workflow.execute("demo")
    assert called
    assert result["evaluation"]["score"] == 1.0


@pytest.mark.asyncio
async def test_virgin_state_title_and_favicon():
    """Verify that initial dashboard, favicon, and empty pipeline list behave properly."""
    store.items.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/pipelines")).json() == []

        # Favicon check
        fav_resp = await c.get("/favicon.ico")
        assert fav_resp.status_code == 200
        assert "image/svg+xml" in fav_resp.headers["content-type"]

        # Dashboard HTML check
        dash_resp = await c.get("/")
        assert dash_resp.status_code == 200
        html = dash_resp.text
        assert "<title>FlowOps</title>" in html
        assert "Run intelligence" not in html
        assert "accounts.google.com" not in html


@pytest.mark.asyncio
async def test_delete_pipeline_and_metrics_consistency():
    """Verify that deleting a pipeline run properly decrements operational metrics."""
    store.items.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Check initial metrics
        m0 = (await c.get("/metrics")).json()
        assert m0["pipelines_started"] == 0
        assert m0["pipelines_succeeded"] == 0
        assert m0["pipelines_failed"] == 0

        # Trigger a run
        res = await c.post("/pipelines/run", json={"text": "id,val\n1,10\n"})
        assert res.status_code == 202
        pid = res.json()["tracking_id"]

        # Wait for completion
        for _ in range(30):
            item = (await c.get(f"/pipelines/{pid}")).json()
            if item["status"] == "succeeded":
                break
            await asyncio.sleep(0.01)

        assert item["status"] == "succeeded"

        # Check metrics updated
        m1 = (await c.get("/metrics")).json()
        assert m1["pipelines_started"] == 1
        assert m1["pipelines_succeeded"] == 1

        # Delete the run
        del_res = await c.delete(f"/pipelines/{pid}")
        assert del_res.status_code == 204

        # Confirm run is gone
        assert (await c.get(f"/pipelines/{pid}")).status_code == 404
        assert (await c.get("/pipelines")).json() == []

        # Confirm metrics decremented
        m2 = (await c.get("/metrics")).json()
        assert m2["pipelines_started"] == 0
        assert m2["pipelines_succeeded"] == 0
        assert m2["pipelines_failed"] == 0
