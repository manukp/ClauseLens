"""Offline smoke test for the Stage-1 ingest pipeline (Phase 2).

Builds a small multi-page PDF with PyMuPDF, stubs the two Bedrock wrappers
(converse + embed) so the test runs with no AWS, then drives the LangGraph spine
end-to-end via ``run_pipeline``. Asserts the acceptance criteria: parsed chunks
carry page+bbox, a FAISS index is built, entities are deduplicated and each
cited, per-doc + master summaries exist, model logs are recorded, and the job
status transitions to complete.
"""
from __future__ import annotations

import json

import fitz  # PyMuPDF
import pytest

from app.aws.bedrock import ConverseResult, EmbedResult, EMBED_DIM
from app.config import settings
from app.models.schemas import ModelCallLog


def _make_pdf() -> bytes:
    doc = fitz.open()
    for n, (heading, body) in enumerate(
        [
            ("ARTICLE 1 SCOPE OF SERVICES", "Acme Corporation shall provide consulting services to Beta Industries."),
            ("ARTICLE 2 PAYMENT TERMS", "Beta Industries shall pay Acme Corporation within thirty days of invoice."),
        ]
    ):
        page = doc.new_page()
        page.insert_text((72, 100), heading, fontsize=18)
        page.insert_text((72, 140), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _fake_embed(texts, *, model_id=None, job_id=None, step="embed"):
    vectors = []
    logs = []
    for i, _ in enumerate(texts):
        vec = [0.0] * EMBED_DIM
        vec[i % EMBED_DIM] = 1.0
        vectors.append(vec)
        logs.append(ModelCallLog(job_id=job_id, step=step, model_id="titan-test", tier="titan", tokens_in=5))
    return EmbedResult(vectors=vectors, logs=logs)


def _fake_converse(model_id, messages, system=None, max_tokens=512, temperature=0.0, *, job_id=None, step="converse"):
    if step == "extract_entities":
        # Same entity from every chunk -> exercises dedup/merge across chunks.
        text = json.dumps(
            [{"name": "Acme Corporation", "type": "organisation",
              "roles": ["service provider"], "responsibilities": ["provide consulting"], "powers": []}]
        )
    else:
        text = f"Summary produced by {step}."
    log = ModelCallLog(job_id=job_id, step=step, model_id=model_id, tier="haiku", tokens_in=20, tokens_out=10)
    return ConverseResult(text=text, log=log)


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point data_dir + the SQLite db at a temp dir and stub Bedrock."""
    from app.store import jobs as jobs_mod
    from app.aws import bedrock

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "db_path", tmp_path / "clauselens.db")
    jobs_mod.get_job_store.cache_clear()
    monkeypatch.setattr(bedrock, "embed", _fake_embed)
    monkeypatch.setattr(bedrock, "converse", _fake_converse)
    yield tmp_path
    jobs_mod.get_job_store.cache_clear()


def test_stage1_pipeline_end_to_end(isolated):
    from app.graph import run_pipeline
    from app.models.schemas import Job, JobStatus
    from app.store import artifacts, get_job_store

    store = get_job_store()
    job = store.create(Job(name="Smoke contract", status=JobStatus.queued))
    job_id = job.job_id

    # Stage the upload the way the /files route would (minus S3).
    (artifacts.uploads_dir(job_id) / "contract.pdf").write_bytes(_make_pdf())
    artifacts.add_document(
        job_id,
        {"doc_id": "doc_test", "doc_name": "contract", "filename": "contract.pdf", "s3_key": "jobs/x/contract.pdf"},
    )

    final = run_pipeline(job_id)

    # Status transitioned to complete (task 9).
    assert store.get(job_id).status == JobStatus.complete

    # Chunks carry page + bbox provenance (task 3 / Citation contract).
    chunks = artifacts.read_json(job_id, artifacts.CHUNKS, default=[])
    assert chunks, "expected at least one chunk"
    for c in chunks:
        assert c["page_start"] >= 1 and c["page_end"] >= c["page_start"]
        assert c["bboxes"] and all(len(b) == 4 for b in c["bboxes"])
    assert any(c["heading"] for c in chunks), "heading heuristic should fire on the 18pt lines"

    # FAISS index built and row-aligned to chunks (task 4).
    from app.ingest import index as index_mod
    idx = index_mod.load_index(artifacts.job_dir(job_id))
    assert idx.ntotal == len(chunks)

    # Entities deduplicated and each cited (task 7 / D9).
    entities = artifacts.read_json(job_id, artifacts.ENTITIES, default=[])
    assert len(entities) == 1, "the single repeated entity must merge to one"
    ent = entities[0]
    assert ent["name"] == "Acme Corporation"
    assert ent["citations"], "every entity must carry a citation"
    assert len(ent["citations"]) == len(chunks), "merged entity accumulates one cite per chunk"
    for cite in ent["citations"]:
        assert cite["doc_id"] and cite["page"] >= 1 and cite["chunk_id"]

    # Per-doc + master summaries exist and are cited (task 8 / D9).
    doc_summaries = artifacts.read_json(job_id, artifacts.DOC_SUMMARIES, default=[])
    assert len(doc_summaries) == 1 and doc_summaries[0]["citations"]
    master = artifacts.read_json(job_id, artifacts.MASTER_SUMMARY, default=None)
    assert master and master["summary"] and master["citations"]

    # Model logs recorded for every call (D13): embed + per-chunk extract + doc + master.
    logs = artifacts.read_model_logs(job_id)
    steps = [log["step"] for log in logs]
    assert "embed.chunks" in steps
    assert steps.count("extract_entities") == len(chunks)
    assert "summarize_doc" in steps and "master_summary" in steps
    assert all("cost_usd" in log and "latency_ms" in log for log in logs)

    # The accumulators threaded through graph state (interface contract).
    assert final["citations"] and final["model_logs"]
