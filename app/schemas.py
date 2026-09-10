"""Pydantic schemas and data models for the FlowOps API.

These models define the request and response contracts for pipeline creation,
progress tracking, status reporting, and health monitoring.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class PipelineStatus(str, Enum):
    """Lifecycle states of an execution pipeline."""
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class PipelineRequest(BaseModel):
    """Payload sent by clients to trigger a new pipeline run.

    Extra fields are strictly forbidden to catch typos early.
    """
    model_config = ConfigDict(extra="forbid")

    # Raw CSV data passed directly in the request body.
    text: str | None = Field(default=None, max_length=100_000)

    # Human-readable label for this run.
    name: str = Field(default="Untitled run", min_length=1, max_length=120)

    # Data origin: 'demo', 'inline', local path, or s3:// URI.
    source: str = Field(default="inline", min_length=1, max_length=500)

    # Additional execution flags or custom metadata.
    options: dict[str, Any] = Field(default_factory=dict)

    @property
    def input_text(self) -> str:
        """Returns the raw input text, guaranteed to be a string."""
        return self.text or ""


class PipelineSummary(BaseModel):
    """Lightweight overview of a pipeline run, suitable for list views."""
    id: UUID
    tracking_id: UUID
    name: str
    status: PipelineStatus
    created_at: datetime
    updated_at: datetime
    current_stage: str = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    stage_history: list[str] = Field(default_factory=list)


class PipelineDetails(PipelineSummary):
    """Detailed view of a pipeline run, including results and errors."""
    text: str | None = None
    source: str
    options: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class RunAccepted(BaseModel):
    """Immediate acknowledgement returned after a run is queued (HTTP 202)."""
    tracking_id: UUID
    status: PipelineStatus
    status_url: str

    # Kept for backward compatibility with clients expecting pipeline_id.
    pipeline_id: UUID | None = None


class HealthResponse(BaseModel):
    """Simple status wrapper for liveness and readiness probes."""
    status: str
