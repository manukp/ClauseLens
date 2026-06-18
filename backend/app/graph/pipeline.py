"""Stage-1 LangGraph pipeline (Phase 2, task 6).

Spine: parse -> chunk -> embed -> extract_entities -> summarize_docs ->
master_summary. Each node is plain Python that calls the boto3 Converse/embed
wrappers (D2) where it needs a model; LangGraph only sequences them (D1). Nodes
persist their artifact as they finish (so the frontend can poll partial state)
and push onto the ``citations`` / ``model_logs`` accumulators (D9, D13).

The self-reflective RAG loop (D10) is intentionally NOT here — it arrives in
Phase 3 and will extend this same graph/state.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from langgraph.graph import END, START, StateGraph

from ..analyze import findings as findings_mod
from ..analyze import graph_build, structured
from ..ingest import chunker, entities, index, parser, summaries
from ..models.schemas import Chunk
from ..store import artifacts
from ..store import get_job_store
from .state import GraphState

logger = logging.getLogger(__name__)

STAGE_1 = "stage-1 ingest"
STAGE_2 = "stage-2 analysis"
STAGE = STAGE_1  # back-compat alias (Phase 2 callers / run_pipeline default)


def _progress(job_id: str, substep: str, stage: str = STAGE_1) -> None:
    """Reflect node progress on the SQLite Job so the frontend can poll it."""
    get_job_store().update(job_id, current_stage=stage, current_substep=substep)


def _resilient(step_name: str, fn: Callable[[GraphState], dict]) -> Callable[[GraphState], dict]:
    """Wrap a node so a failure (after the client's own retries) is isolated.

    On error the step is recorded in the ``step_errors`` accumulator and the node
    returns ONLY that slice — it contributes no other state, so every artifact a
    previous node already computed (summaries, structured items, findings, …) is
    preserved and downstream nodes run on whatever is present (they all read state
    with defaults). The run then finishes as a "partial" analysis rather than
    hard-failing. Critical upstream failures simply cascade into more recorded
    step errors; the overall status still reflects partial completion (Phase 4).
    """

    def wrapped(state: GraphState) -> dict:
        try:
            return fn(state)
        except Exception as exc:  # noqa: BLE001 — deliberately isolate the step
            err = {"step": step_name, "error": f"{type(exc).__name__}: {exc}", "ts": time.time()}
            logger.exception("Pipeline step %s failed (isolated, run continues)", step_name)
            try:
                get_job_store().update(
                    state["job_id"], current_substep=f"{step_name} failed: {type(exc).__name__}"
                )
            except Exception:  # noqa: BLE001 — never let bookkeeping mask the original
                pass
            return {"step_errors": [err]}

    return wrapped


# ---- Nodes ------------------------------------------------------------------

def parse_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    _progress(job_id, "parsing PDFs")
    transcripts: list[dict] = []
    for doc in state.get("documents", []):
        data = (artifacts.uploads_dir(job_id) / doc["filename"]).read_bytes()
        transcripts.append(parser.parse_pdf(data, doc["doc_id"], doc["doc_name"]))
    artifacts.write_json(job_id, artifacts.TRANSCRIPTS, transcripts)
    return {"transcripts": transcripts}


def chunk_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    _progress(job_id, "clause-aware chunking")
    chunks: list[Chunk] = []
    for transcript in state.get("transcripts", []):
        chunks.extend(chunker.chunk_transcript(transcript))
    artifacts.write_json(job_id, artifacts.CHUNKS, [c.model_dump() for c in chunks])
    return {"chunks": chunks}


def embed_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    chunks = state.get("chunks", [])
    _progress(job_id, f"embedding {len(chunks)} chunks -> FAISS")
    result = index.build_index(chunks, job_id=job_id)
    index.save_index(result.index, artifacts.job_dir(job_id))
    return {"model_logs": result.logs}


def extract_entities_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    chunks = state.get("chunks", [])
    found = []
    logs = []
    for i, chunk in enumerate(chunks):
        _progress(job_id, f"extracting entities ({i + 1}/{len(chunks)})")
        ents, call_logs = entities.extract_from_chunk(chunk, job_id=job_id)
        found.extend(ents)
        logs.extend(call_logs)
    merged = entities.merge_entities(found)
    artifacts.write_json(job_id, artifacts.ENTITIES, [e.model_dump() for e in merged])
    citations = [c.model_dump() for e in merged for c in e.citations]
    return {"entities": merged, "model_logs": logs, "citations": citations}


def summarize_docs_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    chunks = state.get("chunks", [])
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)

    doc_summaries = []
    logs = []
    citations = []
    docs = state.get("documents", [])
    for i, doc in enumerate(docs):
        _progress(job_id, f"summarizing documents ({i + 1}/{len(docs)})")
        summary, call_logs = summaries.summarize_doc(
            doc["doc_id"], doc["doc_name"], by_doc.get(doc["doc_id"], []), job_id=job_id
        )
        doc_summaries.append(summary)
        logs.extend(call_logs)
        citations.extend(c.model_dump() for c in summary.citations)
    artifacts.write_json(job_id, artifacts.DOC_SUMMARIES, [d.model_dump() for d in doc_summaries])
    return {"doc_summaries": doc_summaries, "model_logs": logs, "citations": citations}


def master_summary_node(state: GraphState) -> dict:
    job_id = state["job_id"]
    _progress(job_id, "composing master summary (Sonnet)")
    chunks = state.get("chunks", [])
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    master, logs = summaries.master_summary(state.get("doc_summaries", []), by_doc, job_id=job_id)
    artifacts.write_json(job_id, artifacts.MASTER_SUMMARY, master.model_dump())
    citations = [c.model_dump() for c in master.citations]
    return {"master": master, "model_logs": logs, "citations": citations}


# ---- Stage-2 nodes (Phase 3) ------------------------------------------------

def _chunk_meta(state: GraphState) -> list[dict]:
    """Chunk rows as plain dicts (row-aligned to FAISS), the RAG loop's corpus."""
    return [c.model_dump() if isinstance(c, Chunk) else c for c in state.get("chunks", [])]


def extract_structured_node(state: GraphState) -> dict:
    """Stage-2 task 2: deliverables/owners/budgets/timelines/plans/compliance."""
    job_id = state["job_id"]
    _progress(job_id, "extracting structured items (reflective RAG)", STAGE_2)
    items, logs, loop_meta = structured.extract_all(
        job_id=job_id, job_dir=artifacts.job_dir(job_id), chunk_meta=_chunk_meta(state)
    )
    artifacts.write_json(job_id, artifacts.STRUCTURED, [i.model_dump() for i in items])
    artifacts.write_json(job_id, artifacts.RAG_META, {"structured": loop_meta})
    citations = [c.model_dump() for i in items for c in i.citations]
    return {"structured_items": items, "model_logs": logs, "citations": citations}


def build_graph_node(state: GraphState) -> dict:
    """Stage-2 task 3: node/edge JSON for react-flow (D12, graph-lite)."""
    job_id = state["job_id"]
    _progress(job_id, "building entity-relationship graph", STAGE_2)
    eg, logs = graph_build.build(
        entities=state.get("entities", []),
        items=state.get("structured_items", []),
        master=state.get("master"),
        job_id=job_id,
    )
    artifacts.write_json(job_id, artifacts.ENTITY_GRAPH, eg.model_dump())
    citations = [c.model_dump() for e in eg.edges for c in e.citations]
    return {"entity_graph": eg, "model_logs": logs, "citations": citations}


def detect_findings_node(state: GraphState) -> dict:
    """Stage-2 task 4: detect & classify findings via reflective RAG (D10)."""
    job_id = state["job_id"]
    _progress(job_id, "detecting risks/conflicts/gaps/dependencies", STAGE_2)
    found, logs = findings_mod.detect(
        job_id=job_id,
        job_dir=artifacts.job_dir(job_id),
        chunk_meta=_chunk_meta(state),
        entities=state.get("entities", []),
        items=state.get("structured_items", []),
        master=state.get("master"),
    )
    artifacts.write_json(job_id, artifacts.FINDINGS, [f.model_dump() for f in found])
    citations = [c.model_dump() for f in found for c in f.citations]
    return {"findings": found, "model_logs": logs, "citations": citations}


def judge_node(state: GraphState) -> dict:
    """Stage-2 task 6: independent LLM-as-judge verdict per finding (D11)."""
    job_id = state["job_id"]
    found = state.get("findings", [])
    _progress(job_id, f"judging {len(found)} findings", STAGE_2)
    judged, logs = findings_mod.judge(found, chunk_meta=_chunk_meta(state), job_id=job_id)
    artifacts.write_json(job_id, artifacts.FINDINGS, [f.model_dump() for f in judged])
    return {"findings": judged, "model_logs": logs}


# ---- Graph ------------------------------------------------------------------

def build_graph():
    """Compile the full pipeline: Stage-1 spine + Stage-2 analysis (Phase 3).

    Stage-2 appends extract_structured -> build_graph -> detect_findings -> judge.
    The self-reflective RAG cycle (D10) lives inside the analyze.rag subgraph,
    invoked by the structured/findings nodes.
    """
    g = StateGraph(GraphState)
    # Every node is wrapped so a single step failing (after the bedrock client's
    # own adaptive retries) is recorded and isolated rather than aborting the run.
    g.add_node("parse", _resilient("parse", parse_node))
    g.add_node("chunk", _resilient("chunk", chunk_node))
    g.add_node("embed", _resilient("embed", embed_node))
    g.add_node("extract_entities", _resilient("extract_entities", extract_entities_node))
    g.add_node("summarize_docs", _resilient("summarize_docs", summarize_docs_node))
    g.add_node("master_summary", _resilient("master_summary", master_summary_node))
    g.add_node("extract_structured", _resilient("extract_structured", extract_structured_node))
    g.add_node("build_graph", _resilient("build_graph", build_graph_node))
    g.add_node("detect_findings", _resilient("detect_findings", detect_findings_node))
    g.add_node("judge", _resilient("judge", judge_node))

    g.add_edge(START, "parse")
    g.add_edge("parse", "chunk")
    g.add_edge("chunk", "embed")
    g.add_edge("embed", "extract_entities")
    g.add_edge("extract_entities", "summarize_docs")
    g.add_edge("summarize_docs", "master_summary")
    g.add_edge("master_summary", "extract_structured")
    g.add_edge("extract_structured", "build_graph")
    g.add_edge("build_graph", "detect_findings")
    g.add_edge("detect_findings", "judge")
    g.add_edge("judge", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_pipeline(job_id: str) -> GraphState:
    """Invoke the compiled Stage-1 graph for a job and persist its model logs.

    Plain-Python orchestration (NOT in the graph, per D1): set running, run the
    spine, persist the accumulated ModelCallLogs + any step errors, then mark the
    job complete / partial / error.
    """
    store = get_job_store()
    store.update(job_id, status="running", started_ts=time.time(), error=None)
    documents = artifacts.list_documents(job_id)
    try:
        final = _graph().invoke({"job_id": job_id, "documents": documents})
        logs = final.get("model_logs", [])
        artifacts.write_json(
            job_id,
            artifacts.MODEL_LOGS,
            [log.model_dump() for log in logs],
        )
        # Per-step failures that were isolated (not aborted). Persist them so the
        # result API can surface "graph unavailable" etc., and reflect partial
        # completion in the job status rather than reporting a clean "complete".
        step_errors = final.get("step_errors", [])
        artifacts.write_json(job_id, artifacts.STEP_ERRORS, step_errors)
        if step_errors:
            failed = ", ".join(e["step"] for e in step_errors)
            store.update(
                job_id,
                status="partial",
                current_stage=STAGE_2,
                current_substep=f"done — {len(step_errors)} step(s) failed: {failed}",
                error=f"Partial: failed step(s): {failed}",
                finished_ts=time.time(),
            )
        else:
            store.update(
                job_id,
                status="complete",
                current_stage=STAGE_2,
                current_substep="done",
                finished_ts=time.time(),
            )
        return final
    except Exception as exc:  # noqa: BLE001 — catastrophic failure (graph infra, not a node).
        store.update(job_id, status="error", error=f"{type(exc).__name__}: {exc}", finished_ts=time.time())
        raise
