"""Self-reflective RAG loop as a compiled LangGraph sub-cycle (D10, D1).

This is a genuine LangGraph cycle (not a Python while-loop): the analysis nodes
(``structured`` and ``findings``) call :func:`run_reflective_rag`, which invokes
this compiled subgraph. The cycle is:

    retrieve -> grade_relevance -> [reformulate -> retrieve]?  (relevance weak)
             -> generate -> grade_groundedness -> [generate]?  (claim ungrounded)
             -> END

Both back-edges are bounded by ``max_iters`` (default 3) so the cycle always
terminates (D10). Generation is Sonnet (reasoning, D8); the grade/reformulate
steps are Haiku (cheap, high-volume classification). Every call is logged (D13).

Citations are NOT requested from the model here (D3/D18): generation returns plain
text/JSON over numbered context, and callers stamp provenance from the source
chunk that each numbered context line came from (see :func:`hit_to_citation`).
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from ..aws import bedrock
from ..config import settings
from ..ingest import index
from ..ingest.llm_json import parse_json
from ..models.schemas import Chunk, Citation, ModelCallLog

DEFAULT_K = 6
DEFAULT_MAX_ITERS = 3


# ---- helpers ----------------------------------------------------------------

def hit_to_citation(hit: dict) -> Citation:
    """Deterministic Citation from a persisted chunk dict (D18).

    ``hit`` is a chunk row (from ``chunks.json``) optionally carrying a ``score``.
    We rebuild the Chunk and reuse its single citation source.
    """
    data = {k: hit[k] for k in Chunk.model_fields if k in hit}
    return Chunk.model_validate(data).to_citation()


def format_context(hits: list[dict]) -> str:
    """Number the retrieved chunks [1..n] so the model can point at them."""
    lines: list[str] = []
    for i, h in enumerate(hits, 1):
        head = (h.get("heading") or "").strip()
        loc = f"doc: {h.get('doc_name')}, p.{h.get('page_start')}"
        prefix = f"[{i}] ({loc})" + (f" {head}" if head else "")
        lines.append(f"{prefix}\n{h.get('text', '')}")
    return "\n\n".join(lines)


# ---- subgraph state ---------------------------------------------------------

class RagState(TypedDict, total=False):
    job_id: str | None
    job_dir: Path
    chunk_meta: list[dict]
    k: int
    max_iters: int
    system: str
    instruction: str
    max_tokens: int
    # evolving
    query: str
    original_query: str
    hits: list[dict]
    context: str
    relevance_ok: bool
    generation: str
    grounded_ok: bool
    iterations: int  # number of retrievals
    regen_count: int  # number of generations
    logs: Annotated[list[ModelCallLog], operator.add]


# ---- nodes ------------------------------------------------------------------

def _retrieve(state: RagState) -> dict:
    hits, logs = index.search(
        state["job_dir"],
        state.get("chunk_meta", []),
        state.get("query", ""),
        k=state.get("k", DEFAULT_K),
        job_id=state.get("job_id"),
    )
    return {
        "hits": hits,
        "context": format_context(hits),
        "iterations": state.get("iterations", 0) + 1,
        "logs": logs,
    }


_RELEVANCE_SYSTEM = (
    "You grade whether retrieved contract excerpts are RELEVANT and SUFFICIENT to "
    "answer a query. Be strict: empty or off-topic context is not relevant."
)


def _grade_relevance(state: RagState) -> dict:
    context = state.get("context", "")
    if not context.strip():
        return {"relevance_ok": False}
    result = bedrock.converse(
        model_id=settings.chat_model_id,  # Haiku (D8)
        messages=[{"role": "user", "content": [{"text": (
            f'Query: {state.get("query", "")}\n\nRetrieved context:\n{context}\n\n'
            'Return ONLY JSON: {"relevant": true|false, "reason": str}.'
        )}]}],
        system=_RELEVANCE_SYSTEM,
        max_tokens=150,
        job_id=state.get("job_id"),
        step="rag.grade_relevance",
    )
    verdict = parse_json(result.text, default={"relevant": True})
    ok = bool(verdict.get("relevant", True)) if isinstance(verdict, dict) else True
    return {"relevance_ok": ok, "logs": [result.log]}


_REFORMULATE_SYSTEM = (
    "You rewrite a weak retrieval query into a better one for a contract vector "
    "search: add synonyms and concrete clause/term vocabulary. Return ONLY the "
    "rewritten query text, no quotes, no prose."
)


def _reformulate(state: RagState) -> dict:
    result = bedrock.converse(
        model_id=settings.chat_model_id,  # Haiku (D8)
        messages=[{"role": "user", "content": [{"text": (
            f'Original query: {state.get("original_query", state.get("query", ""))}\n'
            "The retrieved context was insufficient. Provide a better search query."
        )}]}],
        system=_REFORMULATE_SYSTEM,
        max_tokens=80,
        job_id=state.get("job_id"),
        step="rag.reformulate",
    )
    new_query = result.text.strip().strip('"') or state.get("query", "")
    return {"query": new_query, "logs": [result.log]}


def _generate(state: RagState) -> dict:
    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet (D8)
        messages=[{"role": "user", "content": [{"text": (
            f'{state.get("instruction", "")}\n\nCONTEXT (numbered excerpts):\n'
            f'{state.get("context", "")}'
        )}]}],
        system=state.get("system", ""),
        max_tokens=state.get("max_tokens", 1500),
        job_id=state.get("job_id"),
        step="rag.generate",
    )
    return {
        "generation": result.text,
        "regen_count": state.get("regen_count", 0) + 1,
        "logs": [result.log],
    }


_GROUNDED_SYSTEM = (
    "You verify GROUNDEDNESS: does every claim in the answer follow from the "
    "provided context, with no unsupported additions? Be strict."
)


def _grade_groundedness(state: RagState) -> dict:
    result = bedrock.converse(
        model_id=settings.chat_model_id,  # Haiku (D8)
        messages=[{"role": "user", "content": [{"text": (
            f'CONTEXT:\n{state.get("context", "")}\n\nANSWER:\n{state.get("generation", "")}\n\n'
            'Return ONLY JSON: {"grounded": true|false, "reason": str}.'
        )}]}],
        system=_GROUNDED_SYSTEM,
        max_tokens=150,
        job_id=state.get("job_id"),
        step="rag.grade_groundedness",
    )
    verdict = parse_json(result.text, default={"grounded": True})
    ok = bool(verdict.get("grounded", True)) if isinstance(verdict, dict) else True
    return {"grounded_ok": ok, "logs": [result.log]}


# ---- conditional routing (bounded cycle) ------------------------------------

def _after_relevance(state: RagState) -> str:
    if state.get("relevance_ok"):
        return "generate"
    if state.get("iterations", 0) >= state.get("max_iters", DEFAULT_MAX_ITERS):
        return "generate"  # cap reached: proceed with best-effort context
    return "reformulate"


def _after_groundedness(state: RagState) -> str:
    if state.get("grounded_ok"):
        return END
    if state.get("regen_count", 0) >= state.get("max_iters", DEFAULT_MAX_ITERS):
        return END  # cap reached: keep last generation
    return "generate"


def _build_subgraph():
    g = StateGraph(RagState)
    g.add_node("retrieve", _retrieve)
    g.add_node("grade_relevance", _grade_relevance)
    g.add_node("reformulate", _reformulate)
    g.add_node("generate", _generate)
    g.add_node("grade_groundedness", _grade_groundedness)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade_relevance")
    g.add_conditional_edges(
        "grade_relevance", _after_relevance,
        {"reformulate": "reformulate", "generate": "generate"},
    )
    g.add_edge("reformulate", "retrieve")
    g.add_edge("generate", "grade_groundedness")
    g.add_conditional_edges(
        "grade_groundedness", _after_groundedness,
        {"generate": "generate", END: END},
    )
    return g.compile()


_SUBGRAPH = None


def _subgraph():
    global _SUBGRAPH
    if _SUBGRAPH is None:
        _SUBGRAPH = _build_subgraph()
    return _SUBGRAPH


# ---- public entry point -----------------------------------------------------

@dataclass
class RagResult:
    """Output of one reflective-RAG invocation."""

    generation: str
    hits: list[dict]
    iterations: int  # retrievals (>=1)
    regen_count: int  # generations (>=1)
    logs: list[ModelCallLog] = field(default_factory=list)

    @property
    def loop_count(self) -> int:
        """Extra passes beyond the single happy-path (re-retrieve + regenerate)."""
        return max(0, self.iterations - 1) + max(0, self.regen_count - 1)


def run_reflective_rag(
    *,
    job_id: str | None,
    job_dir: Path,
    chunk_meta: list[dict],
    query: str,
    system: str,
    instruction: str,
    k: int = DEFAULT_K,
    max_iters: int = DEFAULT_MAX_ITERS,
    max_tokens: int = 1500,
) -> RagResult:
    """Invoke the compiled reflective-RAG sub-cycle and return its result (D10)."""
    final = _subgraph().invoke(
        {
            "job_id": job_id,
            "job_dir": job_dir,
            "chunk_meta": chunk_meta,
            "k": k,
            "max_iters": max_iters,
            "system": system,
            "instruction": instruction,
            "max_tokens": max_tokens,
            "query": query,
            "original_query": query,
            "iterations": 0,
            "regen_count": 0,
        },
        {"recursion_limit": 50},
    )
    return RagResult(
        generation=final.get("generation", ""),
        hits=final.get("hits", []),
        iterations=final.get("iterations", 1),
        regen_count=final.get("regen_count", 1),
        logs=final.get("logs", []),
    )
