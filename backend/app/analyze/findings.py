"""Finding detection + LLM-as-judge (Phase 3 tasks 4 & 6).

``detect`` reasons over the WHOLE document (all section chunks in reading order)
on Sonnet (D8) — not a top-k window — because conflicts, absences, and
per-deliverable / per-milestone completeness can only be judged against the full
contract. Semantic retrieval is kept solely as a scale fallback for contracts too
large to fit one call. The detector iterates explicitly over each deliverable and
each payment milestone. Each finding is cited deterministically from the chunk(s)
the model points at (D9/D18).

``judge`` is a SEPARATE Sonnet call with a DISTINCT role (D11): given each finding,
its cited text, AND the whole-document context, it scores correctness/groundedness
and flags bias/unsupported inference, returning a {score, passed, note} verdict per
finding. Whole-doc context lets it validate absence/conflict claims (which cannot be
verified from a single cited chunk). It never reuses the generating call.
"""
from __future__ import annotations

from pathlib import Path

from ..aws import bedrock
from ..config import settings
from ..ingest import index
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
from .rag import format_context, hit_to_citation, run_reflective_rag

_TYPES = {"risk", "conflict", "gap", "dependency", "issue"}
_SEVERITIES = {"high", "medium", "low"}
_PASS_THRESHOLD = 0.6

# A contract whose chunk text fits this budget is reasoned over whole; larger ones
# fall back to a wide semantic-retrieval window (retrieval kept only for scale).
_WHOLE_DOC_CHAR_BUDGET = 40000

_DETECT_QUERY = (
    "risks conflicts gaps missing clauses unassigned deliverables contradictory "
    "deadlines budget without approval authority missing IP confidentiality data "
    "protection dependencies without responsible party"
)

_DETECT_SYSTEM = (
    "You are a senior contracts risk analyst reviewing an ENTIRE contract. Identify "
    "and classify problems: Risks, Conflicts, Gaps, Dependencies, and Issues. You can "
    "see the whole document, so absence and conflict claims must be checked against "
    "ALL clauses, not a single excerpt. Cite the excerpt number(s) for each finding."
)


def _entity_line(entities: list[Entity]) -> str:
    return ", ".join(f"{e.name} ({e.type})" for e in entities[:25]) or "none"


def _inventory(entities: list[Entity], items: list[StructuredItem]) -> str:
    """Explicit per-deliverable / per-milestone checklist the detector must walk."""
    delivs = [it for it in items if it.category == "deliverable"]
    milestones = [it for it in items if it.category == "budget"]

    def _fmt(it: StructuredItem) -> str:
        attrs = "; ".join(f"{k}={v}" for k, v in it.attributes.items()) or "no attributes captured"
        return f"  - {it.title} [{attrs}]"

    lines = [f"Parties/entities: {_entity_line(entities)}", "", "DELIVERABLES (each needs an OWNER and ACCEPTANCE CRITERIA):"]
    lines += [_fmt(d) for d in delivs] or ["  (none extracted — check the document directly)"]
    lines += ["", "PAYMENT MILESTONES (each needs a named APPROVAL AUTHORITY):"]
    lines += [_fmt(m) for m in milestones] or ["  (none extracted — check the document directly)"]
    return "\n".join(lines)


def _instruction(inventory: str) -> str:
    return (
        "Review the WHOLE contract in the context. Work this checklist EXPLICITLY and "
        "emit a finding for every problem you confirm:\n"
        "A) For EACH deliverable in the inventory check TWO things: (1) acceptance "
        "criteria stated in its own clause, and (2) a SPECIFIC owner/responsible party "
        "or role named for THAT deliverable. A blanket clause that the Vendor performs "
        "all work does NOT count as a per-deliverable owner when the deliverable's own "
        "clause names no responsible party/role. Missing either → a 'gap' citing that "
        "deliverable's clause.\n"
        "B) For EACH payment milestone in the inventory: is a specific approval authority "
        "named? If not → a 'gap' (note which milestones DO name one, so the gap is precise).\n"
        "C) CONFLICTS: compare dates, sequences and dependencies across ALL clauses; flag "
        "impossible/contradictory ones (e.g. a deadline that falls before a prerequisite's "
        "completion date) → a 'conflict'.\n"
        "D) Whole-document ABSENCES: protective clauses entirely missing from the contract "
        "(e.g. IP ownership/assignment, data protection/privacy) → a 'gap'.\n"
        "E) Dependencies with no responsible party or date → a 'dependency'.\n\n"
        f"INVENTORY:\n{inventory}\n\n"
        "Return ONLY a JSON array (no prose). Each element:\n"
        '{"type": "risk"|"conflict"|"gap"|"dependency"|"issue", "title": str, '
        '"description": str, "severity": "high"|"medium"|"low", '
        '"mitigation": str, "sources": [int]}\n'
        'where "sources" are the bracketed excerpt numbers evidencing the finding '
        "(for an absence, cite the closest related clause). Return [] if none."
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


def _whole_or_retrieved(
    job_id: str | None, job_dir: Path, chunk_meta: list[dict]
) -> tuple[list[dict], list[ModelCallLog]]:
    """Whole document (reading order) when it fits; else a wide retrieval window.

    Retrieval is kept ONLY for scale — small/medium contracts are reasoned over in
    full so conflicts/absences/completeness can be judged against every clause.
    """
    total = sum(len(c.get("text", "")) for c in chunk_meta)
    if total <= _WHOLE_DOC_CHAR_BUDGET:
        return list(chunk_meta), []
    hits, logs = index.search(
        job_dir, chunk_meta, _DETECT_QUERY, k=min(20, len(chunk_meta)), job_id=job_id
    )
    return hits, logs


def detect(
    *,
    job_id: str | None,
    job_dir: Path,
    chunk_meta: list[dict],
    entities: list[Entity],
    items: list[StructuredItem],
    master: MasterSummary | None,
) -> tuple[list[Finding], list[ModelCallLog]]:
    """Detect & classify findings over the whole document (top-k only for scale).

    No reflective re-retrieval loop here: the detector already sees every section, so
    re-retrieval is moot. The structured-extraction nodes still exercise the loop
    (D10); the judge independently re-validates each finding (D11).
    """
    hits, logs = _whole_or_retrieved(job_id, job_dir, chunk_meta)
    context = format_context(hits)
    inventory = _inventory(entities, items)

    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet (D8)
        messages=[{"role": "user", "content": [{"text": (
            f"{_instruction(inventory)}\n\nWHOLE CONTRACT (numbered excerpts):\n{context}"
        )}]}],
        system=_DETECT_SYSTEM,
        max_tokens=4096,
        job_id=job_id,
        step="detect_findings",
    )
    logs = logs + [result.log]

    raw = parse_json(result.text, default=[])
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
                    citations=_citations_for(el.get("sources", []), hits),
                    loop_count=0,
                )
            )
    return findings, logs


# ---- LLM-as-judge (D11) -----------------------------------------------------

_JUDGE_SYSTEM = (
    "You are an INDEPENDENT reviewer auditing another analyst's contract findings. "
    "You did not produce these findings. You are given the WHOLE contract. For each "
    "finding judge (a) correctness/groundedness and (b) bias/unsupported inference. "
    "CRUCIALLY: for 'gap' (absence) findings, confirm the clause is genuinely ABSENT "
    "from the whole contract — do not fail an absence finding merely because its cited "
    "excerpt does not contain the missing item; that is expected. For 'conflict' "
    "findings, verify the contradiction by reading both clauses in the full document. "
    "Be skeptical but fair: a claim contradicted by the document, or one that overreaches "
    "beyond the evidence, must fail."
)


def judge(
    findings: list[Finding], *, chunk_meta: list[dict] | None = None, job_id: str | None = None
) -> tuple[list[Finding], list[ModelCallLog]]:
    """Attach an independent {score, passed, note} verdict to each finding (D11).

    One batched Sonnet call with a distinct reviewer role — separate from the detect
    call — given the WHOLE document so absence/conflict claims can be validated against
    every clause rather than a single cited chunk.
    """
    if not findings:
        return findings, []

    doc_context = format_context(chunk_meta) if chunk_meta else ""
    blocks = []
    for i, f in enumerate(findings, 1):
        cited = " | ".join(c.text_span for c in f.citations) or "(no cited text)"
        blocks.append(
            f"[{i}] type={f.type} severity={f.severity}\n"
            f"title: {f.title}\ndescription: {f.description}\ncited text: {cited}"
        )
    payload = "\n\n".join(blocks)

    doc_block = f"WHOLE CONTRACT (numbered excerpts):\n{doc_context}\n\n" if doc_context else ""
    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet (D8), distinct role (D11)
        messages=[{"role": "user", "content": [{"text": (
            f"{doc_block}FINDINGS TO REVIEW:\n{payload}\n\n"
            'Return ONLY a JSON array, one element per finding, in order:\n'
            '{"index": int, "score": number (0.0-1.0), "passed": true|false, "note": str}\n'
            "score = confidence the finding is correct, grounded, and unbiased "
            "(validate absences/conflicts against the whole contract above)."
        )}]}],
        system=_JUDGE_SYSTEM,
        max_tokens=2000,
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
