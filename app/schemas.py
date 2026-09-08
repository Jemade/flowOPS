from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class PipelineStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class PipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=100_000)
    name: str = Field(default="Untitled run", min_length=1, max_length=120)
    source: str = Field(default="inline", min_length=1, max_length=500)
    options: dict[str, Any] = Field(default_factory=dict)

    @property
    def input_text(self) -> str:
        return self.text or ""


class PipelineSummary(BaseModel):
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
    text: str | None = None
    source: str
    options: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class RunAccepted(BaseModel):
    tracking_id: UUID
    status: PipelineStatus
    status_url: str
    # Kept for clients of the original MVP contract.
    pipeline_id: UUID | None = None


class HealthResponse(BaseModel):
    status: str
