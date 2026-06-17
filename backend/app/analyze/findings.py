"""Finding detection + LLM-as-judge (Phase 3 tasks 4 & 6).

``detect`` runs the self-reflective RAG loop (D10) on Sonnet (D8) to identify and
classify Risks, Conflicts, Gaps, Dependencies, and Issues, grounded in the
retrieved clauses plus the already-extracted structure (entities + structured
items). Each finding is cited deterministically from the chunk(s) the model points
at (D9/D18).

``judge`` is a SEPARATE Sonnet call with a DISTINCT role (D11): given each finding
and its cited text, it scores correctness/groundedness and flags bias/unsupported
inference, returning a {score, passed, note} verdict per finding. It never reuses
the generating call.
"""
from __future__ import annotations

from pathlib import Path

from ..aws import bedrock
from ..config import settings
from ..ingest.llm_json import parse_json
from ..models.schemas import (
    Citation,
    Entity,
    Finding,
    JudgeVerdict,
    MasterSummary,
    ModelCallLog,
    StructuredItem,
)
from .rag import hit_to_citation, run_reflective_rag

_TYPES = {"risk", "conflict", "gap", "dependency", "issue"}
_SEVERITIES = {"high", "medium", "low"}
_PASS_THRESHOLD = 0.6

_DETECT_QUERY = (
    "risks conflicts gaps missing clauses unassigned deliverables contradictory "
    "deadlines budget without approval authority missing IP confidentiality data "
    "protection dependencies without responsible party"
)

_DETECT_SYSTEM = (
    "You are a senior contracts risk analyst. Identify and classify problems in the "
    "contract: Risks, Conflicts, Gaps, Dependencies, and Issues. Look for: a "
    "deliverable with no acceptance criteria; an unassigned deliverable / missing "
    "owner; contradictory deadlines across clauses; a budget/payment line with no "
    "named approval authority; a missing IP/confidentiality/data-protection clause; "
    "a dependency with no responsible party. Use the numbered context excerpts and "
    "the provided extracted structure; cite the excerpt number(s) for each finding."
)


def _summarize_structure(entities: list[Entity], items: list[StructuredItem]) -> str:
    ent_line = ", ".join(f"{e.name} ({e.type})" for e in entities[:25]) or "none"
    by_cat: dict[str, list[str]] = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it.title)
    item_lines = "\n".join(f"- {cat}: {', '.join(titles[:12])}" for cat, titles in by_cat.items()) or "- none"
    return f"Entities: {ent_line}\nExtracted items:\n{item_lines}"


def _instruction(structure: str) -> str:
    return (
        "Already-extracted structure (for spotting gaps/conflicts):\n"
        f"{structure}\n\n"
        "Return ONLY a JSON array (no prose). Each element:\n"
        '{"type": "risk"|"conflict"|"gap"|"dependency"|"issue", "title": str, '
        '"description": str, "severity": "high"|"medium"|"low", '
        '"mitigation": str, "sources": [int]}\n'
        'where "sources" are the bracketed excerpt numbers evidencing the finding '
        "(for a gap, cite the closest relevant clause). Return [] if none."
    )


def _citations_for(sources: list, hits: list[dict]) -> list[Citation]:
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
    if not cites and hits:
        cites = [hit_to_citation(hits[0])]
    return cites


def detect(
    *,
    job_id: str | None,
    job_dir: Path,
    chunk_meta: list[dict],
    entities: list[Entity],
    items: list[StructuredItem],
    master: MasterSummary | None,
) -> tuple[list[Finding], list[ModelCallLog]]:
    """Detect & classify findings via the reflective RAG loop (D10), each cited."""
    structure = _summarize_structure(entities, items)
    rag = run_reflective_rag(
        job_id=job_id,
        job_dir=job_dir,
        chunk_meta=chunk_meta,
        query=_DETECT_QUERY,
        system=_DETECT_SYSTEM,
        instruction=_instruction(structure),
        k=8,
        max_tokens=2200,
    )
    raw = parse_json(rag.generation, default=[])
    findings: list[Finding] = []
    if isinstance(raw, list):
        for el in raw:
            if not isinstance(el, dict):
                continue
            ftype = str(el.get("type", "")).strip().lower()
            title = str(el.get("title", "")).strip()
            if ftype not in _TYPES or not title:
                continue
            severity = str(el.get("severity", "medium")).strip().lower()
            if severity not in _SEVERITIES:
                severity = "medium"
            findings.append(
                Finding(
                    type=ftype,
                    title=title,
                    description=str(el.get("description", "")).strip(),
                    severity=severity,
                    mitigation=str(el.get("mitigation", "")).strip(),
                    citations=_citations_for(el.get("sources", []), rag.hits),
                    loop_count=rag.loop_count,
                )
            )
    return findings, rag.logs


# ---- LLM-as-judge (D11) -----------------------------------------------------

_JUDGE_SYSTEM = (
    "You are an INDEPENDENT reviewer auditing another analyst's contract findings. "
    "You did not produce these findings. For each one, judge (a) "
    "correctness/groundedness: is it supported by its cited text? and (b) bias or "
    "unsupported inference: does it overreach beyond the evidence? Be skeptical and "
    "fair. A finding that is unsupported or biased must fail."
)


def judge(findings: list[Finding], *, job_id: str | None = None) -> tuple[list[Finding], list[ModelCallLog]]:
    """Attach an independent {score, passed, note} verdict to each finding (D11).

    One batched Sonnet call with a distinct reviewer role — separate from the
    detect call that generated the findings.
    """
    if not findings:
        return findings, []

    blocks = []
    for i, f in enumerate(findings, 1):
        cited = " | ".join(c.text_span for c in f.citations) or "(no cited text)"
        blocks.append(
            f"[{i}] type={f.type} severity={f.severity}\n"
            f"title: {f.title}\ndescription: {f.description}\ncited text: {cited}"
        )
    payload = "\n\n".join(blocks)

    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet (D8), distinct role (D11)
        messages=[{"role": "user", "content": [{"text": (
            f"FINDINGS TO REVIEW:\n{payload}\n\n"
            'Return ONLY a JSON array, one element per finding, in order:\n'
            '{"index": int, "score": number (0.0-1.0), "passed": true|false, "note": str}\n'
            "score = confidence the finding is correct, grounded, and unbiased."
        )}]}],
        system=_JUDGE_SYSTEM,
        max_tokens=1800,
        job_id=job_id,
        step="judge",
    )

    raw = parse_json(result.text, default=[])
    verdicts: dict[int, dict] = {}
    if isinstance(raw, list):
        for el in raw:
            if isinstance(el, dict) and "index" in el:
                try:
                    verdicts[int(el["index"])] = el
                except (TypeError, ValueError):
                    continue

    for i, f in enumerate(findings, 1):
        v = verdicts.get(i, {})
        try:
            score = max(0.0, min(1.0, float(v.get("score", 0.0))))
        except (TypeError, ValueError):
            score = 0.0
        passed = bool(v.get("passed", score >= _PASS_THRESHOLD)) and score >= _PASS_THRESHOLD
        note = str(v.get("note", "")).strip() or ("No verdict returned." if not v else "")
        f.judge = JudgeVerdict(score=score, passed=passed, note=note)

    return findings, [result.log]
