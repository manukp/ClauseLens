"""Entity/role extraction (Haiku tier, D8 — Phase 2 task 7).

Run per-chunk so each extracted entity is stamped with that chunk's deterministic
Citation (D18 / task 5): we never ask the model to emit citations. The model
returns plain JSON entities; we attach provenance and merge duplicates across
chunks by normalized name.
"""
from __future__ import annotations

from ..aws import bedrock
from ..config import settings
from ..models.schemas import Chunk, Entity, ModelCallLog
from .llm_json import parse_json

_SYSTEM = (
    "You are a contract analyst. From the clause text, extract the named entities "
    "that are parties or actors: organisations and people. For each, capture the "
    "roles they hold, the responsibilities/obligations assigned to them, and the "
    "powers/rights granted to them — strictly as supported by THIS text. Do not "
    "invent entities not present in the text."
)

_INSTRUCTION = (
    "Return ONLY a JSON array (no prose). Each element:\n"
    '{"name": str, "type": "organisation"|"person", "roles": [str], '
    '"responsibilities": [str], "powers": [str]}\n'
    "If the text names no entities, return []."
)


def _norm(name: str) -> str:
    return " ".join(name.lower().split()).strip(" .,:;")


def _dedup(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for v in values:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen[v.lower()] = v
    return list(seen.values())


def extract_from_chunk(chunk: Chunk, *, job_id: str | None = None) -> tuple[list[Entity], list[ModelCallLog]]:
    """Extract entities from one chunk; stamp each with the chunk's Citation."""
    result = bedrock.converse(
        model_id=settings.chat_model_id,  # Haiku tier (D8)
        messages=[{"role": "user", "content": [{"text": f"{_INSTRUCTION}\n\nCLAUSE TEXT:\n{chunk.text}"}]}],
        system=_SYSTEM,
        max_tokens=900,
        job_id=job_id,
        step="extract_entities",
    )
    raw = parse_json(result.text, default=[])
    citation = chunk.to_citation()
    entities: list[Entity] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            etype = str(item.get("type", "organisation")).strip().lower()
            if etype not in ("organisation", "organization", "person"):
                etype = "organisation"
            etype = "organisation" if etype.startswith("organi") else etype
            entities.append(
                Entity(
                    name=name,
                    type=etype,
                    roles=_dedup([str(x) for x in item.get("roles", []) if x]),
                    responsibilities=_dedup([str(x) for x in item.get("responsibilities", []) if x]),
                    powers=_dedup([str(x) for x in item.get("powers", []) if x]),
                    citations=[citation],
                )
            )
    return entities, [result.log]


def merge_entities(entities: list[Entity]) -> list[Entity]:
    """Deduplicate/merge entities across chunks by normalized name (task 7)."""
    merged: dict[str, Entity] = {}
    for ent in entities:
        key = _norm(ent.name)
        if not key:
            continue
        if key not in merged:
            merged[key] = ent.model_copy(deep=True)
            continue
        cur = merged[key]
        cur.roles = _dedup(cur.roles + ent.roles)
        cur.responsibilities = _dedup(cur.responsibilities + ent.responsibilities)
        cur.powers = _dedup(cur.powers + ent.powers)
        cur.citations = cur.citations + ent.citations
        if cur.type == "organisation" and ent.type == "person":
            cur.type = "person"  # a person mention is more specific than a default
    return list(merged.values())
