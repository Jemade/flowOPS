"""Pipeline execution state persistence.

Provides a unified store for pipeline run records. Uses an in-memory dictionary
with asyncio locking for local development, and automatically synchronizes
state to Amazon DynamoDB when configured with AWS credentials or LocalStack.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import boto3
from .config import settings
from .schemas import PipelineDetails, PipelineRequest, PipelineStatus, PipelineSummary


def now() -> datetime:
    """Returns the current timestamp in UTC."""
    return datetime.now(timezone.utc)


class PipelineStore:
    """Stores and retrieves pipeline execution records.

    Maintains a local in-memory cache and optionally syncs mutations
    with a remote DynamoDB table if an AWS endpoint URL is configured.
    """

    def __init__(self, table: str = "flowops-pipelines", resource=None):
        self.table_name = table
        self.items: dict[str, PipelineDetails] = {}
        self.resource = resource

        # Initialize boto3 DynamoDB resource when an endpoint or AWS setup is present
        if self.resource is None and settings.aws_endpoint_url:
            try:
                self.resource = boto3.resource(
                    "dynamodb",
                    region_name=settings.aws_region,
                    endpoint_url=settings.aws_endpoint_url,
                )
            except Exception:
                self.resource = None

        self._lock = asyncio.Lock()

    def _put_remote(self, item: PipelineDetails) -> None:
        """Best-effort write to DynamoDB if a resource connection exists."""
        if not self.resource:
            return
        try:
            self.resource.Table(self.table_name).put_item(
                Item={
                    "id": str(item.id),
                    "name": item.name,
                    "source": item.source,
                    "text": item.text or "",
                    "tracking_id": str(item.tracking_id),
                    "options": item.options,
                    "status": item.status.value,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "current_stage": item.current_stage,
                    "progress": item.progress,
                    "stage_history": item.stage_history,
                    "result": item.result or {},
                    "error": item.error or "",
                }
            )
        except Exception:
            pass

    async def create(
        self,
        pipeline_id: UUID,
        request: PipelineRequest,
        owner_id: str | None = None,
    ) -> PipelineDetails:
        """Creates and stores a newly queued pipeline run record."""
        current_time = now()
        item = PipelineDetails(
            id=pipeline_id,
            name=request.name,
            source=request.source,
            text=request.text,
            tracking_id=pipeline_id,
            options=request.options,
            status=PipelineStatus.queued,
            created_at=current_time,
            updated_at=current_time,
            current_stage="queued",
            progress=0,
            stage_history=["queued"],
        )
        if owner_id:
            item.options = {**item.options, "_owner_id": owner_id}

        async with self._lock:
            self.items[str(pipeline_id)] = item

        self._put_remote(item)
        return item

    async def update(self, pipeline_id: UUID, **changes: Any) -> PipelineDetails | None:
        """Updates specific fields of an existing pipeline record."""
        async with self._lock:
            item = self.items.get(str(pipeline_id))
            if not item:
                return None
            updated = item.model_copy(update={**changes, "updated_at": now()})
            self.items[str(pipeline_id)] = updated

        self._put_remote(updated)
        return updated

    async def delete(self, pipeline_id: UUID) -> bool:
        """Removes a pipeline record from both local cache and DynamoDB."""
        async with self._lock:
            existed = self.items.pop(str(pipeline_id), None) is not None

        if self.resource:
            try:
                self.resource.Table(self.table_name).delete_item(
                    Key={"id": str(pipeline_id)}
                )
            except Exception:
                pass

        return existed

    async def get(
        self, pipeline_id: UUID, owner_id: str | None = None
    ) -> PipelineDetails | None:
        """Retrieves pipeline details by ID, checking local memory then DynamoDB."""
        item = self.items.get(str(pipeline_id))
        if item and owner_id and item.options.get("_owner_id") != owner_id:
            return None
        if item or not self.resource:
            return item

        # Attempt to read from DynamoDB if not found in local memory
        try:
            raw = (
                self.resource.Table(self.table_name)
                .get_item(Key={"id": str(pipeline_id)})
                .get("Item")
            )
            if raw:
                if owner_id and raw.get("options", {}).get("_owner_id") != owner_id:
                    return None
                item = PipelineDetails(
                    id=pipeline_id,
                    name=raw["name"],
                    source=raw["source"],
                    text=raw.get("text") or None,
                    tracking_id=pipeline_id,
                    options=raw.get("options", {}),
                    status=PipelineStatus(raw["status"]),
                    created_at=datetime.fromisoformat(raw["created_at"]),
                    updated_at=datetime.fromisoformat(raw["updated_at"]),
                    current_stage=raw.get("current_stage", "queued"),
                    progress=int(raw.get("progress", 0)),
                    stage_history=raw.get("stage_history", ["queued"]),
                    result=raw.get("result") or None,
                    error=raw.get("error") or None,
                )
                self.items[str(pipeline_id)] = item
                return item
        except Exception:
            pass

        return None

    async def list(self, owner_id: str | None = None) -> list[PipelineSummary]:
        """Lists all known pipeline runs as summary records."""
        cached = [
            PipelineSummary(**i.model_dump())
            for i in self.items.values()
            if owner_id is None or i.options.get("_owner_id") == owner_id
        ]
        if cached or not self.resource:
            return cached

        # Attempt to fetch all records from DynamoDB if memory is empty
        try:
            response = self.resource.Table(self.table_name).scan()
            summaries = []
            for raw in response.get("Items", []):
                if owner_id and raw.get("options", {}).get("_owner_id") != owner_id:
                    continue
                summaries.append(
                    PipelineSummary(
                        id=UUID(raw["id"]),
                        tracking_id=UUID(raw["tracking_id"]),
                        name=raw["name"],
                        status=PipelineStatus(raw["status"]),
                        created_at=datetime.fromisoformat(raw["created_at"]),
                        updated_at=datetime.fromisoformat(raw["updated_at"]),
                        current_stage=raw.get("current_stage", "queued"),
                        progress=int(raw.get("progress", 0)),
                        stage_history=raw.get("stage_history", ["queued"]),
                    )
                )
            return summaries
        except Exception:
            return []
