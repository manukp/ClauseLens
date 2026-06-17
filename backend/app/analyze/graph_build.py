"""Entity-relationship graph assembly (Phase 3 task 3, D12 — graph-lite).

Nodes come deterministically from the merged entities (organisations / people) and
the extracted deliverables. Edges (typed relations) are inferred by a single Sonnet
reasoning call (D8) over the numbered node list; we validate every edge against the
fixed relation set and the known node ids, then stamp each edge with a Citation
from its source node's provenance (D9/D18). This is node/edge JSON for react-flow —
NOT GraphRAG (D12).
"""
from __future__ import annotations

from ..aws import bedrock
from ..config import settings
from ..ingest.llm_json import parse_json
from ..models.schemas import (
    Citation,
    Entity,
    EntityGraph,
    GraphEdge,
    GraphNode,
    MasterSummary,
    ModelCallLog,
    StructuredItem,
)

RELATIONS = {"engages", "owns", "responsible_for", "depends_on", "conflicts_with"}

_SYSTEM = (
    "You are a contracts analyst building a relationship graph. Given a numbered "
    "list of graph nodes (organisations, people, deliverables), infer the typed "
    "relationships between them. Use ONLY these relations: engages (party engages "
    "party), owns (party owns deliverable), responsible_for (party responsible for "
    "deliverable), depends_on (deliverable depends on deliverable), conflicts_with "
    "(any conflict). Only assert relationships supported by the node descriptions."
)


def _node_citation(node: GraphNode, by_id: dict[str, list[Citation]]) -> list[Citation]:
    cites = by_id.get(node.id, [])
    return [cites[0]] if cites else []


def build(
    *,
    entities: list[Entity],
    items: list[StructuredItem],
    master: MasterSummary | None,
    job_id: str | None = None,
) -> tuple[EntityGraph, list[ModelCallLog]]:
    """Assemble nodes deterministically and infer typed edges via one Sonnet call."""
    nodes: list[GraphNode] = []
    cites_by_id: dict[str, list[Citation]] = {}

    for ent in entities:
        nodes.append(
            GraphNode(
                id=ent.entity_id,
                label=ent.name,
                type="person" if ent.type == "person" else "organisation",
                data={"roles": ent.roles, "responsibilities": ent.responsibilities, "powers": ent.powers},
            )
        )
        cites_by_id[ent.entity_id] = list(ent.citations)

    for item in items:
        if item.category != "deliverable":
            continue
        nodes.append(
            GraphNode(id=item.item_id, label=item.title, type="deliverable", data={"detail": item.detail})
        )
        cites_by_id[item.item_id] = list(item.citations)

    if len(nodes) < 2:
        return EntityGraph(nodes=nodes, edges=[]), []

    # Number nodes for the model; map index -> node.id on the way back.
    listing_lines = []
    for i, n in enumerate(nodes, 1):
        desc = n.data.get("detail") or "; ".join(n.data.get("roles", []) + n.data.get("responsibilities", []))
        listing_lines.append(f"[{i}] ({n.type}) {n.label}" + (f" — {desc}" if desc else ""))
    listing = "\n".join(listing_lines)
    ctx = f"\n\nContract overview:\n{master.summary}" if master and master.summary else ""

    result = bedrock.converse(
        model_id=settings.reasoning_model_id,  # Sonnet (D8)
        messages=[{"role": "user", "content": [{"text": (
            f"NODES:\n{listing}{ctx}\n\n"
            'Return ONLY a JSON array of edges (no prose). Each element:\n'
            '{"source": int, "target": int, "relation": str}\n'
            "using the bracketed node numbers and an allowed relation."
        )}]}],
        system=_SYSTEM,
        max_tokens=1200,
        job_id=job_id,
        step="build_graph",
    )

    raw = parse_json(result.text, default=[])
    edges: list[GraphEdge] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(raw, list):
        for el in raw:
            if not isinstance(el, dict):
                continue
            relation = str(el.get("relation", "")).strip().lower()
            if relation not in RELATIONS:
                continue
            try:
                si, ti = int(el["source"]) - 1, int(el["target"]) - 1
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= si < len(nodes) and 0 <= ti < len(nodes)) or si == ti:
                continue
            src, tgt = nodes[si], nodes[ti]
            key = (src.id, tgt.id, relation)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                GraphEdge(
                    source=src.id,
                    target=tgt.id,
                    relation=relation,
                    label=relation.replace("_", " "),
                    citations=_node_citation(src, cites_by_id),
                )
            )

    return EntityGraph(nodes=nodes, edges=edges), [result.log]
