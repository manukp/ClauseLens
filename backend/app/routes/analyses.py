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


@router.get("/{job_id}")
def get_analysis(job_id: str) -> dict:
    job = _require_job(job_id)
    present = {
        "documents": bool(artifacts.list_documents(job_id)),
        "chunks": (artifacts.job_dir(job_id) / artifacts.CHUNKS).exists(),
        "faiss_index": (artifacts.job_dir(job_id) / index_filename()).exists(),
        "entities": (artifacts.job_dir(job_id) / artifacts.ENTITIES).exists(),
        "doc_summaries": (artifacts.job_dir(job_id) / artifacts.DOC_SUMMARIES).exists(),
        "master_summary": (artifacts.job_dir(job_id) / artifacts.MASTER_SUMMARY).exists(),
    }
    return {"job": job.model_dump(), "artifacts": present}


@router.get("/{job_id}/result")
def get_result(job_id: str) -> dict:
    _require_job(job_id)
    return {
        "job_id": job_id,
        "documents": artifacts.list_documents(job_id),
        "entities": artifacts.read_json(job_id, artifacts.ENTITIES, default=[]),
        "doc_summaries": artifacts.read_json(job_id, artifacts.DOC_SUMMARIES, default=[]),
        "master_summary": artifacts.read_json(job_id, artifacts.MASTER_SUMMARY, default=None),
        "model_logs": artifacts.read_model_logs(job_id),
        "chunk_count": len(artifacts.read_json(job_id, artifacts.CHUNKS, default=[]) or []),
    }


def index_filename() -> str:
    from ..ingest.index import INDEX_FILENAME

    return INDEX_FILENAME
