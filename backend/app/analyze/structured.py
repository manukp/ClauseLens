"""Stage-2 structured extraction (Phase 3 task 2, Sonnet tier / D8).

Per category (deliverables, owners, budgets, timelines, plans, compliance), run
the self-reflective RAG loop (D10) to retrieve the relevant clauses and extract a
JSON list of items. The model only points at numbered context lines (``sources``);
we stamp each item's Citation deterministically from the chunk that line came from
(D9/D18) — the model never emits offsets or bboxes.
"""
from __future__ import annotations

from pathlib import Path

from ..models.schemas import Citation, ModelCallLog, StructuredItem
from ..ingest.llm_json import parse_json
from .rag import hit_to_citation, run_reflective_rag

_SYSTEM = (
    "You are a senior contracts analyst extracting structured facts from a contract. "
    "Use ONLY the numbered context excerpts provided. Do not invent facts. For every "
    "item, cite the excerpt number(s) it is supported by."
)

# (category, retrieval query, attribute guidance shown to the model)
_CATEGORIES: list[tuple[str, str, str]] = [
    ("deliverable",
     "deliverables work products services milestones scope of work and acceptance criteria",
     'attributes may include "acceptance_criteria" and "owner" when stated'),
    ("owner",
     "responsible party owner roles responsibilities who performs obligations",
     'attributes may include "responsible_for" (the deliverable/area) and "role"'),
    ("budget",
     "budget fees payment amounts price invoicing approval authority who approves spend",
     'attributes may include "amount" and "approval_authority" (who approves)'),
    ("timeline",
     "timeline deadlines dates schedule term duration milestones completion",
     'attributes may include "deadline" or "date" and the related "milestone"'),
    ("plan",
     "project plan phases stages methodology approach implementation steps",
     'attributes may include "phase" and "scope"'),
    ("compliance",
     "compliance regulatory legal confidentiality data protection IP security requirements",
     'attributes may include "requirement" and "standard"'),
]


def _instruction(category: str, attr_hint: str) -> str:
    return (
        f'Extract every {category.upper()} from the context. {attr_hint}.\n'
        'Return ONLY a JSON array (no prose). Each element:\n'
        '{"title": str, "detail": str, "attributes": {str: str}, "sources": [int]}\n'
        'where "sources" are the bracketed excerpt numbers supporting the item. '
        f'If the context contains no {category}, return [].'
    )


def _citations_for(sources: list, hits: list[dict]) -> list[Citation]:
    """Map model-pointed excerpt numbers to deterministic citations (D18)."""
    cites: list[Citation] = []
    seen: set[str] = set()
    for s in sources or []:
        try:
            idx = int(s) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(hits):
            cite = hit_to_citation(hits[idx])
            if cite.chunk_id not in seen:
                seen.add(cite.chunk_id)
                cites.append(cite)
    if not cites and hits:  # fallback: cite the top retrieval so D9 always holds
        cites = [hit_to_citation(hits[0])]
    return cites


def extract_all(
    *, job_id: str | None, job_dir: Path, chunk_meta: list[dict]
) -> tuple[list[StructuredItem], list[ModelCallLog], dict]:
    """Run reflective RAG per category; return cited items, logs, and loop meta."""
    items: list[StructuredItem] = []
    logs: list[ModelCallLog] = []
    loop_meta: dict[str, int] = {}

    for category, query, attr_hint in _CATEGORIES:
        rag = run_reflective_rag(
            job_id=job_id,
            job_dir=job_dir,
            chunk_meta=chunk_meta,
            query=query,
            system=_SYSTEM,
            instruction=_instruction(category, attr_hint),
            max_tokens=1600,
        )
        logs.extend(rag.logs)
        loop_meta[category] = rag.loop_count
        raw = parse_json(rag.generation, default=[])
        if not isinstance(raw, list):
            continue
        for el in raw:
            if not isinstance(el, dict):
                continue
            title = str(el.get("title", "")).strip()
            if not title:
                continue
            attrs = el.get("attributes", {})
            attrs = {str(k): str(v) for k, v in attrs.items()} if isinstance(attrs, dict) else {}
            items.append(
                StructuredItem(
                    category=category,
                    title=title,
                    detail=str(el.get("detail", "")).strip(),
                    attributes=attrs,
                    citations=_citations_for(el.get("sources", []), rag.hits),
                )
            )

    return items, logs, loop_meta
