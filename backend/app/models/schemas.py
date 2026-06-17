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


class Chunk(BaseModel):
    """A clause-aware unit of a document (Phase 2, task 3).

    Produced by the chunker from PyMuPDF spans. A chunk may span less than, one,
    or more than a page. ``bboxes`` is one [x0,y0,x1,y1] box per page touched
    (aligned to ``pages``), enabling clickable citation highlights. ``heading``
    is the detected section heading (font/layout heuristic), if any.
    """

    chunk_id: str = Field(default_factory=lambda: _new_id("chunk"))
    doc_id: str
    doc_name: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    pages: list[int] = Field(default_factory=list)
    bboxes: list[list[float]] = Field(default_factory=list)
    heading: str | None = None
    text: str = ""
    # Per-line provenance within the chunk: [{page, bbox:[x0,y0,x1,y1], text}].
    # Lets a citation highlight a specific sub-clause inside a full-clause chunk.
    lines: list[dict] = Field(default_factory=list)

    def to_citation(self) -> "Citation":
        """Deterministic Citation from this chunk's provenance (D18 / task 5).

        We never ask the model to emit citation offsets; we stamp findings with
        the source chunk's stored metadata. ``bbox`` is the first page's box.
        """
        span = self.text.strip().replace("\n", " ")
        if len(span) > 240:
            span = span[:237] + "..."
        return Citation(
            doc_id=self.doc_id,
            doc_name=self.doc_name,
            page=self.page_start,
            bbox=self.bboxes[0] if self.bboxes else None,
            text_span=span,
            chunk_id=self.chunk_id,
        )


class Entity(BaseModel):
    """An organisation or person extracted from the contract set (task 7).

    Deduplicated/merged across chunks; every entity carries the citations of the
    chunks it was found in (D9). ``roles`` / ``responsibilities`` / ``powers``
    accumulate across the merged occurrences.
    """

    entity_id: str = Field(default_factory=lambda: _new_id("ent"))
    name: str
    type: str = "organisation"  # "organisation" | "person"
    roles: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    powers: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class DocSummary(BaseModel):
    """Per-document summary (Haiku tier, task 8). Cites the doc's sections."""

    doc_id: str
    doc_name: str
    summary: str
    citations: list[Citation] = Field(default_factory=list)


class MasterSummary(BaseModel):
    """Contract master summary across all documents (Sonnet tier, task 8)."""

    summary: str
    citations: list[Citation] = Field(default_factory=list)


class StructuredItem(BaseModel):
    """A reasoned, cited Stage-2 extraction (Phase 3 task 2, Sonnet tier / D8).

    One ``category`` per item: deliverable | owner | budget | timeline | plan |
    compliance. ``attributes`` holds category-specific facts (e.g. a deliverable's
    ``acceptance_criteria``, a budget's ``approval_authority``, a timeline's
    ``deadline``). Every item is cited from its source chunk(s) (D9/D18).
    """

    item_id: str = Field(default_factory=lambda: _new_id("item"))
    category: str  # deliverable | owner | budget | timeline | plan | compliance
    title: str
    detail: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)


class GraphNode(BaseModel):
    """A react-flow node for the entity-relationship graph (D12, graph-lite)."""

    id: str
    label: str
    type: str  # organisation | person | deliverable
    data: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A typed react-flow edge (D12). ``relation`` is one of the fixed set:
    engages | owns | responsible_for | depends_on | conflicts_with."""

    id: str = Field(default_factory=lambda: _new_id("edge"))
    source: str
    target: str
    relation: str
    label: str = ""
    citations: list[Citation] = Field(default_factory=list)


class EntityGraph(BaseModel):
    """First-class graph artifact: node/edge JSON for react-flow (D12)."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """LLM-as-judge result attached to a finding (D11). ``score`` is 0..1;
    ``passed`` is False when groundedness/correctness is weak or biased."""

    score: float = 0.0
    passed: bool = False
    note: str = ""


class Finding(BaseModel):
    """A detected Risk/Conflict/Gap/Dependency/Issue (Phase 3 task 4, Sonnet/D8).

    Every finding carries one or more Citations (D9/D18) and, after the judge
    pass, a ``judge`` verdict (D11). ``loop_count`` records the self-reflective
    RAG passes (D10) taken to produce the finding batch.
    """

    finding_id: str = Field(default_factory=lambda: _new_id("find"))
    type: str  # risk | conflict | gap | dependency | issue
    title: str
    description: str = ""
    severity: str = "medium"  # high | medium | low
    mitigation: str = ""
    citations: list[Citation] = Field(default_factory=list)
    judge: JudgeVerdict | None = None
    loop_count: int = 0


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
