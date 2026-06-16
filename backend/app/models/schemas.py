"""Cross-cutting pydantic schemas.

These mirror the Interface contracts in .claude/IMPLEMENTATION_LOG.md. Do not
change the core meaning of a field without a Known-issues note in the log.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field


def _now_ts() -> float:
    """Unix epoch seconds (float). Single clock source for all timestamps."""
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Citation(BaseModel):
    """Provenance attached to every extracted artifact (D9).

    ``bbox`` is [x0, y0, x1, y1] in PDF points, or None when a span maps to a
    whole page / synthesized content. ``page`` is 1-based.
    """

    doc_id: str
    doc_name: str
    page: int = Field(ge=1)
    bbox: list[float] | None = None
    text_span: str
    chunk_id: str


class ModelCallLog(BaseModel):
    """One record per Bedrock invocation — powers the Admin Sankey + latency
    table (D13). Emitted for every model call, no exceptions."""

    call_id: str = Field(default_factory=lambda: _new_id("call"))
    job_id: str | None = None
    step: str
    model_id: str
    tier: str  # "haiku" | "sonnet" | "titan" | "unknown"
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    ts: float = Field(default_factory=_now_ts)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    error = "error"


class Job(BaseModel):
    """Analysis job — one row in the SQLite job store (D6)."""

    job_id: str = Field(default_factory=lambda: _new_id("job"))
    name: str
    created_ts: float = Field(default_factory=_now_ts)
    status: JobStatus = JobStatus.queued
    current_stage: str = ""
    current_substep: str = ""
    started_ts: float | None = None
    finished_ts: float | None = None
    error: str | None = None
