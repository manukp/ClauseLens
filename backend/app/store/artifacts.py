"""Per-job artifact persistence on the local filesystem (D6 — Phase 2 task 10).

All Stage-1 outputs for a job live under ``data/jobs/{job_id}/``:

    uploads/                 the source PDFs (downloaded from S3 for parsing)
    documents.json           registry: [{doc_id, doc_name, s3_key, filename}]
    transcripts.json         per-doc parsed transcript (page + bbox)
    chunks.json              clause-aware chunks (row-aligned to the FAISS index)
    faiss.index              the vector index (written by ingest.index)
    entities.json            deduplicated, cited entities
    doc_summaries.json       per-document summaries
    master_summary.json      contract master summary
    structured_items.json    Stage-2 deliverables/owners/budgets/timelines/...
    entity_graph.json        node/edge JSON for react-flow (D12)
    findings.json            risks/conflicts/gaps/deps + judge verdicts (D11)
    rag_meta.json            self-reflective RAG loop counts per stage (D10)
    model_logs.json          every Bedrock ModelCallLog for the job (D13)

JSON only; no DB rows for these (the job *status* lives in SQLite). Reads return
a default when an artifact is absent so callers stay simple.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import settings
from ..models.schemas import ModelCallLog

DOCUMENTS = "documents.json"
TRANSCRIPTS = "transcripts.json"
CHUNKS = "chunks.json"
ENTITIES = "entities.json"
DOC_SUMMARIES = "doc_summaries.json"
MASTER_SUMMARY = "master_summary.json"
STRUCTURED = "structured_items.json"
ENTITY_GRAPH = "entity_graph.json"
FINDINGS = "findings.json"
RAG_META = "rag_meta.json"
MODEL_LOGS = "model_logs.json"
STEP_ERRORS = "step_errors.json"  # per-step failures that did not abort the run


def jobs_root() -> Path:
    return settings.data_dir / "jobs"


def job_dir(job_id: str) -> Path:
    path = jobs_root() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir(job_id: str) -> Path:
    path = job_dir(job_id) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(job_id: str, name: str, obj: Any) -> Path:
    path = job_dir(job_id) / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_json(job_id: str, name: str, default: Any = None) -> Any:
    path = job_dir(job_id) / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# ---- Documents registry (updated as files are uploaded) ---------------------

def add_document(job_id: str, doc: dict) -> list[dict]:
    docs = read_json(job_id, DOCUMENTS, default=[]) or []
    docs.append(doc)
    write_json(job_id, DOCUMENTS, docs)
    return docs


def list_documents(job_id: str) -> list[dict]:
    return read_json(job_id, DOCUMENTS, default=[]) or []


# ---- Model logs (append-only across the run; powers Admin later, D13) -------

def append_model_logs(job_id: str, logs: list[ModelCallLog]) -> None:
    if not logs:
        return
    existing = read_json(job_id, MODEL_LOGS, default=[]) or []
    existing.extend(log.model_dump() if isinstance(log, ModelCallLog) else log for log in logs)
    write_json(job_id, MODEL_LOGS, existing)


def read_model_logs(job_id: str) -> list[dict]:
    return read_json(job_id, MODEL_LOGS, default=[]) or []
