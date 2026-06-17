"""Typed LangGraph state for the Stage-1 spine (interface contract, Phase 2).

Threads the ``job_id``, the document set, the chunk list, retrieval results
(reserved for Phase 3's RAG loop), and two accumulators that grow as nodes run:
``citations`` (every cited artifact's provenance) and ``model_logs`` (one per
Bedrock call, D13). Both use an additive reducer so each node contributes its
slice without clobbering earlier nodes.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..models.schemas import (
    Chunk,
    DocSummary,
    Entity,
    EntityGraph,
    Finding,
    MasterSummary,
    ModelCallLog,
    StructuredItem,
)


class GraphState(TypedDict, total=False):
    job_id: str
    # Document registry: [{doc_id, doc_name, filename, s3_key, local_path}].
    documents: list[dict]
    # Parsed transcripts (page + bbox), one per document.
    transcripts: list[dict]
    # Clause-aware chunks, row-aligned to the FAISS index.
    chunks: list[Chunk]
    # Retrieval hits — populated by Phase 3's self-reflective loop (D10).
    retrieval: list[dict]
    # Stage-1 outputs.
    entities: list[Entity]
    doc_summaries: list[DocSummary]
    master: MasterSummary | None
    # Stage-2 outputs (Phase 3).
    structured_items: list[StructuredItem]
    entity_graph: EntityGraph | None
    findings: list[Finding]
    # Accumulators (additive reducers).
    citations: Annotated[list[dict], operator.add]
    model_logs: Annotated[list[ModelCallLog], operator.add]
