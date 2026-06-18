"""Offline smoke test for the Stage-2 analysis pipeline (Phase 3).

Stubs the two Bedrock wrappers so the full LangGraph pipeline (Stage-1 spine +
Stage-2 analysis) runs with no AWS, then asserts the Phase-3 acceptance criteria:
structured items with citations, a coherent graph JSON, findings each with a
severity + citation + judge verdict, a self-reflective RAG loop that demonstrably
re-retrieves/regenerates at least once and terminates within the cap, and result
endpoints (status / source / observability) returning well-formed, reconciling data.
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
    for heading, body in [
        ("ARTICLE 1 SCOPE OF SERVICES", "Acme Corporation shall provide consulting services to Beta Industries."),
        ("ARTICLE 2 PAYMENT TERMS", "Beta Industries shall pay Acme Corporation within thirty days of invoice."),
    ]:
        page = doc.new_page()
        page.insert_text((72, 100), heading, fontsize=18)
        page.insert_text((72, 140), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _fake_embed(texts, *, model_id=None, job_id=None, step="embed"):
    vectors, logs = [], []
    for i, _ in enumerate(texts):
        vec = [0.0] * EMBED_DIM
        vec[i % EMBED_DIM] = 1.0
        vectors.append(vec)
        logs.append(ModelCallLog(job_id=job_id, step=step, model_id="titan-test", tier="titan", tokens_in=5))
    return EmbedResult(vectors=vectors, logs=logs)


def _make_converse():
    """Stub Converse covering every Stage-1 + Stage-2 step.

    The first relevance grade and first groundedness grade return WEAK, forcing
    the reflective loop (D10) to re-retrieve once and regenerate once on the first
    RAG invocation (the 'deliverable' category), then pass thereafter.
    """
    counters = {"relevance": 0, "ground": 0}

    def fake(model_id, messages, system=None, max_tokens=512, temperature=0.0, *, job_id=None, step="converse"):
        user = messages[0]["content"][0]["text"]
        if step == "extract_entities":
            text = json.dumps([
                {"name": "Acme Corporation", "type": "organisation",
                 "roles": ["service provider"], "responsibilities": ["provide consulting"], "powers": []},
                {"name": "Beta Industries", "type": "organisation",
                 "roles": ["client"], "responsibilities": ["pay fees"], "powers": ["approve invoices"]},
            ])
        elif step == "rag.grade_relevance":
            counters["relevance"] += 1
            text = json.dumps({"relevant": counters["relevance"] != 1, "reason": "x"})
        elif step == "rag.grade_groundedness":
            counters["ground"] += 1
            text = json.dumps({"grounded": counters["ground"] != 1, "reason": "x"})
        elif step == "rag.reformulate":
            text = "deliverables owners acceptance criteria responsibilities"
        elif step == "detect_findings":  # whole-document detection (Sonnet)
            text = json.dumps([
                {"type": "gap", "title": "Deliverable lacks acceptance criteria",
                 "description": "The consulting deliverable states no acceptance criteria.",
                 "severity": "high", "mitigation": "Define measurable acceptance criteria.",
                 "sources": [1]},
            ])
        elif step == "rag.generate":
            if "DELIVERABLE" in user:
                text = json.dumps([
                    {"title": "Consulting services", "detail": "Acme provides consulting to Beta",
                     "attributes": {"acceptance_criteria": "per SOW"}, "sources": [1]},
                ])
            elif "OWNER" in user:
                text = json.dumps([
                    {"title": "Acme Corporation", "detail": "service provider",
                     "attributes": {"role": "provider"}, "sources": [1]},
                ])
            else:  # budget / timeline / plan / compliance -> none in this tiny doc
                text = "[]"
        elif step == "build_graph":
            text = json.dumps([
                {"source": 1, "target": 2, "relation": "engages"},
                {"source": 1, "target": 3, "relation": "owns"},
                {"source": 9, "target": 9, "relation": "bogus"},  # must be filtered out
            ])
        elif step == "judge":
            text = json.dumps([{"index": 1, "score": 0.9, "passed": True, "note": "grounded in cited clause"}])
        else:  # summarize_doc, master_summary
            text = f"Summary produced by {step}."

        tier = "sonnet" if step in ("rag.generate", "build_graph", "judge", "master_summary", "detect_findings") else "haiku"
        log = ModelCallLog(job_id=job_id, step=step, model_id=model_id, tier=tier,
                           tokens_in=20, tokens_out=10, latency_ms=5, cost_usd=0.001)
        return ConverseResult(text=text, log=log)

    return fake


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    from app.store import jobs as jobs_mod
    from app.aws import bedrock

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "db_path", tmp_path / "clauselens.db")
    jobs_mod.get_job_store.cache_clear()
    monkeypatch.setattr(bedrock, "embed", _fake_embed)
    monkeypatch.setattr(bedrock, "converse", _make_converse())
    yield tmp_path
    jobs_mod.get_job_store.cache_clear()


def test_stage2_pipeline_end_to_end(isolated):
    from app.graph import run_pipeline
    from app.models.schemas import Job, JobStatus
    from app.store import artifacts, get_job_store
    from app.routes import analyses

    store = get_job_store()
    job = store.create(Job(name="Stage-2 contract", status=JobStatus.queued))
    job_id = job.job_id

    (artifacts.uploads_dir(job_id) / "contract.pdf").write_bytes(_make_pdf())
    artifacts.add_document(
        job_id,
        {"doc_id": "doc_test", "doc_name": "contract", "filename": "contract.pdf", "s3_key": "jobs/x/contract.pdf"},
    )

    run_pipeline(job_id)
    assert store.get(job_id).status == JobStatus.complete

    # --- Structured items: deliverables/owners present and each cited (task 2) ---
    items = artifacts.read_json(job_id, artifacts.STRUCTURED, default=[])
    cats = {i["category"] for i in items}
    assert "deliverable" in cats and "owner" in cats
    for it in items:
        assert it["citations"], "every structured item must be cited (D9)"
        for c in it["citations"]:
            assert c["chunk_id"] and c["page"] >= 1

    # --- Self-reflective RAG loop re-ran at least once and stayed within cap ---
    rag_meta = artifacts.read_json(job_id, artifacts.RAG_META, default={})
    deliverable_loops = rag_meta.get("structured", {}).get("deliverable", 0)
    assert deliverable_loops >= 1, "weak first case should force a re-retrieve/regenerate"
    assert deliverable_loops <= 4, "loop must terminate within the cap (D10)"

    # --- Graph JSON: nodes + typed edges, edges cited (task 3 / D12) ---
    eg = artifacts.read_json(job_id, artifacts.ENTITY_GRAPH, default={})
    assert len(eg["nodes"]) >= 3
    types = {n["type"] for n in eg["nodes"]}
    assert "organisation" in types and "deliverable" in types
    assert len(eg["edges"]) >= 2
    allowed = {"engages", "owns", "responsible_for", "depends_on", "conflicts_with"}
    for e in eg["edges"]:
        assert e["relation"] in allowed
        assert e["source"] != e["target"]
        assert e["citations"], "graph edges must be cited (D9)"

    # --- Findings: severity + citation + judge verdict each (tasks 4 & 6) ---
    findings = artifacts.read_json(job_id, artifacts.FINDINGS, default=[])
    assert findings, "expected at least one finding"
    for f in findings:
        assert f["type"] in {"risk", "conflict", "gap", "dependency", "issue"}
        assert f["severity"] in {"high", "medium", "low"}
        assert f["citations"], "every finding must be cited (D9/D18)"
        assert f["judge"] is not None, "every finding gets a judge verdict (D11)"
        assert 0.0 <= f["judge"]["score"] <= 1.0
        assert isinstance(f["judge"]["passed"], bool)

    # --- Observability totals reconcile with per-step sums (task 8 / D13) ---
    obs = analyses.get_observability(job_id)
    step_calls = sum(s["calls"] for s in obs["by_step"].values())
    step_cost = round(sum(s["cost_usd"] for s in obs["by_step"].values()), 6)
    assert step_calls == obs["totals"]["calls"]
    assert abs(step_cost - obs["totals"]["cost_usd"]) < 1e-6
    # Judge + reflective-loop calls are logged (D13).
    assert "judge" in obs["by_step"]
    assert "rag.generate" in obs["by_step"] and "rag.grade_relevance" in obs["by_step"]

    # --- source/{chunk_id} resolves to page + bbox for the citation viewer ---
    chunks = artifacts.read_json(job_id, artifacts.CHUNKS, default=[])
    src = analyses.get_source(job_id, chunks[0]["chunk_id"])
    assert src["doc_name"] == "contract" and src["page"] >= 1
    assert src["bbox"] and len(src["bbox"]) == 4 and src["text"]

    # --- status endpoint exposes polling fields (task 8) ---
    status = analyses.get_status(job_id)
    assert status["status"] == JobStatus.complete
    assert status["current_stage"] == "stage-2 analysis"


def test_partial_failure_isolates_step_and_continues(isolated, monkeypatch):
    """A step failing after retries must not abort the run or discard prior work
    (Phase 4 follow-up). Force build_graph to raise; the run should finish
    'partial', keep the already-computed structured items, STILL produce findings
    (a downstream step), omit the graph, and surface the error in the result."""
    from app.analyze import graph_build
    from app.graph import run_pipeline
    from app.models.schemas import Job, JobStatus
    from app.routes import analyses
    from app.store import artifacts, get_job_store

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated Bedrock ReadTimeoutError")

    monkeypatch.setattr(graph_build, "build", _boom)

    store = get_job_store()
    job = store.create(Job(name="Partial run", status=JobStatus.queued))
    job_id = job.job_id
    (artifacts.uploads_dir(job_id) / "contract.pdf").write_bytes(_make_pdf())
    artifacts.add_document(
        job_id,
        {"doc_id": "doc_test", "doc_name": "contract", "filename": "contract.pdf", "s3_key": "x"},
    )

    run_pipeline(job_id)

    # Overall status reflects partial completion, not a hard error.
    assert store.get(job_id).status == JobStatus.partial

    # The failed step is recorded; everything else was preserved / still ran.
    step_errors = artifacts.read_json(job_id, artifacts.STEP_ERRORS, default=[])
    assert any(e["step"] == "build_graph" for e in step_errors)

    items = artifacts.read_json(job_id, artifacts.STRUCTURED, default=[])
    assert items, "structured items computed before the failure must be preserved"

    findings = artifacts.read_json(job_id, artifacts.FINDINGS, default=[])
    assert findings, "detect_findings (downstream of build_graph) must still run"

    # The graph artifact is absent/empty, and the result surfaces the failure.
    eg = artifacts.read_json(job_id, artifacts.ENTITY_GRAPH, default={"nodes": [], "edges": []})
    assert not eg.get("nodes")
    result = analyses.get_analysis(job_id)
    assert result["step_errors"] and result["step_errors"][0]["step"] == "build_graph"
