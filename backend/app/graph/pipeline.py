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

from langgraph.graph import END, START, StateGraph

from ..ingest import chunker, entities, index, parser, summaries
from ..models.schemas import Chunk
from ..store import artifacts
from ..store import get_job_store
from .state import GraphState

STAGE = "stage-1 ingest"


def _progress(job_id: str, substep: str) -> None:
    """Reflect node progress on the SQLite Job so the frontend can poll it."""
    get_job_store().update(job_id, current_stage=STAGE, current_substep=substep)


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


# ---- Graph ------------------------------------------------------------------

def build_graph():
    """Compile the Stage-1 spine. Phase 3 extends this graph with the RAG loop."""
    g = StateGraph(GraphState)
    g.add_node("parse", parse_node)
    g.add_node("chunk", chunk_node)
    g.add_node("embed", embed_node)
    g.add_node("extract_entities", extract_entities_node)
    g.add_node("summarize_docs", summarize_docs_node)
    g.add_node("master_summary", master_summary_node)

    g.add_edge(START, "parse")
    g.add_edge("parse", "chunk")
    g.add_edge("chunk", "embed")
    g.add_edge("embed", "extract_entities")
    g.add_edge("extract_entities", "summarize_docs")
    g.add_edge("summarize_docs", "master_summary")
    g.add_edge("master_summary", END)
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
    spine, persist the accumulated ModelCallLogs, then mark complete/error.
    """
    import time

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
        store.update(
            job_id,
            status="complete",
            current_stage=STAGE,
            current_substep="done",
            finished_ts=time.time(),
        )
        return final
    except Exception as exc:  # noqa: BLE001 — capture failure on the Job (task 9).
        store.update(job_id, status="error", error=f"{type(exc).__name__}: {exc}", finished_ts=time.time())
        raise
