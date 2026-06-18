"""Analysis job API (Phase 2, task 1).

    POST /api/analyses              create a Job (name) -> status queued
    POST /api/analyses/{id}/files   upload PDFs -> S3 jobs/{id}/ (+ local copy)
    POST /api/analyses/{id}/run     kick the Stage-1 pipeline (background) -> running
    GET  /api/analyses              list jobs
    GET  /api/analyses/{id}         job status + which artifacts exist
    GET  /api/analyses/{id}/result  the cited Stage-1 outputs for the job

PDFs only (D17): non-PDF uploads are rejected. S3 is the source of truth for the
raw files; a local copy under ``uploads/`` feeds the PyMuPDF parser (D4).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..aws import s3
from ..graph import run_pipeline
from ..models.schemas import Job, JobStatus, _new_id
from ..store import artifacts, get_job_store

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


class CreateAnalysis(BaseModel):
    name: str


def _require_job(job_id: str) -> Job:
    job = get_job_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown analysis: {job_id}")
    return job


def _is_pdf(file: UploadFile, head: bytes) -> bool:
    """Accept only PDFs (D17): by content type, extension, and magic bytes."""
    name_ok = (file.filename or "").lower().endswith(".pdf")
    type_ok = (file.content_type or "").lower() in ("application/pdf", "application/x-pdf")
    magic_ok = head[:5] == b"%PDF-"
    return magic_ok and (name_ok or type_ok)


@router.post("")
def create_analysis(body: CreateAnalysis) -> Job:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    job = Job(name=name, status=JobStatus.queued)
    return get_job_store().create(job)


@router.get("")
def list_analyses() -> list[Job]:
    return get_job_store().list()


@router.post("/{job_id}/files")
async def upload_files(job_id: str, files: list[UploadFile]) -> dict:
    _require_job(job_id)
    if not files:
        raise HTTPException(status_code=422, detail="No files provided")

    added: list[dict] = []
    for file in files:
        data = await file.read()
        if not _is_pdf(file, data):
            raise HTTPException(
                status_code=415,
                detail=f"Only PDF uploads are accepted (D17); rejected: {file.filename!r}",
            )
        filename = os.path.basename(file.filename or f"{_new_id('file')}.pdf")
        # S3 is the source of truth (task 1); local copy feeds the parser (D4).
        key = s3.upload_bytes(job_id, filename, data, content_type="application/pdf")
        (artifacts.uploads_dir(job_id) / filename).write_bytes(data)
        doc = {
            "doc_id": _new_id("doc"),
            "doc_name": os.path.splitext(filename)[0],
            "filename": filename,
            "s3_key": key,
        }
        artifacts.add_document(job_id, doc)
        added.append(doc)

    return {"job_id": job_id, "uploaded": added, "documents": artifacts.list_documents(job_id)}


@router.post("/{job_id}/run")
def run_analysis(job_id: str, background: BackgroundTasks) -> Job:
    _require_job(job_id)
    if not artifacts.list_documents(job_id):
        raise HTTPException(status_code=409, detail="No files uploaded for this analysis")
    store = get_job_store()
    # Set running immediately so the response reflects state; the pipeline also
    # transitions status/stage as it progresses (task 9).
    store.update(job_id, status="running", current_stage="stage-1 ingest", current_substep="queued", error=None)
    background.add_task(run_pipeline, job_id)
    return _require_job(job_id)


@router.get("/{job_id}/status")
def get_status(job_id: str) -> dict:
    """Lightweight polling endpoint (Phase 3 task 8)."""
    job = _require_job(job_id)
    return {
        "job_id": job_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "current_substep": job.current_substep,
        "started_ts": job.started_ts,
        "finished_ts": job.finished_ts,
        "error": job.error,
    }


def _full_result(job_id: str) -> dict:
    """The complete cited result for a job (master + entities + graph + items +
    findings with citations + judge verdicts)."""
    present = {
        "documents": bool(artifacts.list_documents(job_id)),
        "chunks": (artifacts.job_dir(job_id) / artifacts.CHUNKS).exists(),
        "faiss_index": (artifacts.job_dir(job_id) / index_filename()).exists(),
        "entities": (artifacts.job_dir(job_id) / artifacts.ENTITIES).exists(),
        "doc_summaries": (artifacts.job_dir(job_id) / artifacts.DOC_SUMMARIES).exists(),
        "master_summary": (artifacts.job_dir(job_id) / artifacts.MASTER_SUMMARY).exists(),
        "structured_items": (artifacts.job_dir(job_id) / artifacts.STRUCTURED).exists(),
        "entity_graph": (artifacts.job_dir(job_id) / artifacts.ENTITY_GRAPH).exists(),
        "findings": (artifacts.job_dir(job_id) / artifacts.FINDINGS).exists(),
    }
    # Per-step failures isolated during the run (partial completion). The UI uses
    # these to show "graph unavailable" instead of blanking a missing section.
    step_errors = artifacts.read_json(job_id, artifacts.STEP_ERRORS, default=[]) or []
    return {
        "job_id": job_id,
        "job": _require_job(job_id).model_dump(),
        "artifacts": present,
        "documents": artifacts.list_documents(job_id),
        "master_summary": artifacts.read_json(job_id, artifacts.MASTER_SUMMARY, default=None),
        "doc_summaries": artifacts.read_json(job_id, artifacts.DOC_SUMMARIES, default=[]),
        "entities": artifacts.read_json(job_id, artifacts.ENTITIES, default=[]),
        "entity_graph": artifacts.read_json(job_id, artifacts.ENTITY_GRAPH, default={"nodes": [], "edges": []}),
        "structured_items": artifacts.read_json(job_id, artifacts.STRUCTURED, default=[]),
        "findings": artifacts.read_json(job_id, artifacts.FINDINGS, default=[]),
        "chunk_count": len(artifacts.read_json(job_id, artifacts.CHUNKS, default=[]) or []),
        "step_errors": step_errors,
    }


@router.get("/{job_id}")
def get_analysis(job_id: str) -> dict:
    """Full result (Phase 3 task 8): master summary, entities, graph, structured
    items, findings (with citations + judge verdicts)."""
    _require_job(job_id)
    return _full_result(job_id)


@router.get("/{job_id}/result")
def get_result(job_id: str) -> dict:
    """Back-compat alias for the full result (Phase 2 callers)."""
    _require_job(job_id)
    return _full_result(job_id)


@router.get("/{job_id}/source/{chunk_id}")
def get_source(job_id: str, chunk_id: str) -> dict:
    """Resolve a citation's chunk to {doc_name, page, bbox, text} for the viewer."""
    _require_job(job_id)
    chunks = artifacts.read_json(job_id, artifacts.CHUNKS, default=[]) or []
    for c in chunks:
        if c.get("chunk_id") == chunk_id:
            bboxes = c.get("bboxes") or []
            return {
                "chunk_id": chunk_id,
                "doc_id": c.get("doc_id"),
                "doc_name": c.get("doc_name"),
                "page": c.get("page_start"),
                "bbox": bboxes[0] if bboxes else None,
                "text": c.get("text", ""),
                # Per-line provenance: lets the viewer highlight a specific sub-clause
                # (a high-severity finding's citation bbox is one of these lines).
                "lines": c.get("lines", []),
            }
    raise HTTPException(status_code=404, detail=f"Unknown chunk: {chunk_id}")


@router.get("/{job_id}/document/{doc_id}")
def get_document(job_id: str, doc_id: str) -> FileResponse:
    """Serve a job's raw PDF for the react-pdf citation viewer (Phase 4).

    The local ``uploads/`` copy (already downloaded for the parser, D4) is the
    source; no S3 round-trip and no new infra (D7). Inline so the viewer renders
    it rather than triggering a download.
    """
    _require_job(job_id)
    for doc in artifacts.list_documents(job_id):
        if doc.get("doc_id") == doc_id:
            path = artifacts.uploads_dir(job_id) / doc["filename"]
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Source PDF missing on disk")
            return FileResponse(
                str(path),
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{doc["filename"]}"'},
            )
    raise HTTPException(status_code=404, detail=f"Unknown document: {doc_id}")


@router.get("/{job_id}/observability")
def get_observability(job_id: str) -> dict:
    """Aggregated ModelCallLogs for the Admin page (D13): per-step + totals."""
    _require_job(job_id)
    logs = artifacts.read_model_logs(job_id)

    def _acc() -> dict:
        return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}

    by_step: dict[str, dict] = {}
    by_tier: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    totals = _acc()
    for log in logs:
        for bucket, key in ((by_step, log.get("step", "?")), (by_tier, log.get("tier", "?")),
                            (by_model, log.get("model_id", "?"))):
            agg = bucket.setdefault(key, _acc())
            agg["calls"] += 1
            agg["tokens_in"] += log.get("tokens_in", 0)
            agg["tokens_out"] += log.get("tokens_out", 0)
            agg["latency_ms"] += log.get("latency_ms", 0)
            agg["cost_usd"] = round(agg["cost_usd"] + log.get("cost_usd", 0.0), 6)
        totals["calls"] += 1
        totals["tokens_in"] += log.get("tokens_in", 0)
        totals["tokens_out"] += log.get("tokens_out", 0)
        totals["latency_ms"] += log.get("latency_ms", 0)
        totals["cost_usd"] = round(totals["cost_usd"] + log.get("cost_usd", 0.0), 6)

    return {
        "job_id": job_id,
        "totals": totals,
        "by_step": by_step,
        "by_tier": by_tier,
        "by_model": by_model,
        "logs": logs,
    }


def index_filename() -> str:
    from ..ingest.index import INDEX_FILENAME

    return INDEX_FILENAME
