"""Summaries (Phase 2 task 8).

Per-document summaries on the Haiku tier; a contract master summary on the
Sonnet tier (D8), built from the per-document summaries. Summaries cite the
documents/sections they derive from (D9) — citations are stamped deterministically
from chunk provenance (D18), never emitted by the model.
"""
from __future__ import annotations

from ..aws import bedrock
from ..config import settings
from ..models.schemas import Chunk, Citation, DocSummary, MasterSummary, ModelCallLog

# Bound the context fed to a single call (PoC contracts are small).
_MAX_DOC_CHARS = 12000
_MAX_CITES = 6

_DOC_SYSTEM = (
    "You are a contract analyst. Summarize the document factually and concisely "
    "for a reader who needs the gist: its purpose, the parties, and the principal "
    "obligations, terms, and dates. Use only what the text supports."
)
_MASTER_SYSTEM = (
    "You are a senior contracts lead. Given per-document summaries of a related "
    "contract set, produce one cohesive master summary: the overall arrangement, "
    "the parties and their relationship, and the most consequential terms and "
    "interdependencies across the documents. Be precise and grounded."
)


def _section_citations(chunks: list[Chunk]) -> list[Citation]:
    """Pick representative chunks (prefer headed sections) to cite the summary."""
    headed = [c for c in chunks if c.heading]
    picked = (headed or chunks)[:_MAX_CITES]
    return [c.to_citation() for c in picked]


def summarize_doc(
    doc_id: str, doc_name: str, chunks: list[Chunk], *, job_id: str | None = None
) -> tuple[DocSummary, list[ModelCallLog]]:
    """Per-document summary (Haiku tier, D8), cited to the doc's sections."""
    body_parts: list[str] = []
    used = 0
    for c in chunks:
        piece = (f"## {c.heading}\n" if c.heading else "") + c.text
        if used + len(piece) > _MAX_DOC_CHARS:
            break
        body_parts.append(piece)
        used += len(piece)
    body = "\n\n".join(body_parts)

    result = bedrock.converse(
        model_id=settings.chat_model_id,  # Haiku tier
        messages=[{"role": "user", "content": [{"text": f"Document: {doc_name}\n\n{body}"}]}],
        system=_DOC_SYSTEM,
        max_tokens=600,
        job_id=job_id,
        step="summarize_doc",
    )
    summary = DocSummary(
        doc_id=doc_id,
        doc_name=doc_name,
        summary=result.text.strip(),
        citations=_section_citations(chunks),
    )
    return summary, [result.log]


def master_summary(
    doc_summaries: list[DocSummary], chunks_by_doc: dict[str, list[Chunk]], *, job_id: str | None = None
) -> tuple[MasterSummary, list[ModelCallLog]]:
    """Contract master summary (Sonnet tier, D8) built from the doc summaries."""
    if not doc_summaries:
        return MasterSummary(summary="", citations=[]), []

    joined = "\n\n".join(f"### {d.doc_name}\n{d.summary}" for d in doc_summaries)
    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet tier (D8)
        messages=[{"role": "user", "content": [{"text": f"Per-document summaries:\n\n{joined}"}]}],
        system=_MASTER_SYSTEM,
        max_tokens=900,
        job_id=job_id,
        step="master_summary",
    )
    # Cite one representative (first) chunk per document.
    cites: list[Citation] = []
    for d in doc_summaries:
        doc_chunks = chunks_by_doc.get(d.doc_id, [])
        if doc_chunks:
            cites.append(doc_chunks[0].to_citation())
    summary = MasterSummary(summary=result.text.strip(), citations=cites)
    return summary, [result.log]
