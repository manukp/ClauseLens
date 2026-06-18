import type { Citation, Finding, GraphNode } from "../lib/types";
import CitationChip from "./CitationChip";

const TYPE_LABEL: Record<string, string> = {
  organisation: "Organisation",
  person: "Role / person",
  deliverable: "Deliverable",
};

// The detail aside (mockup `.detail`) — a light oatmeal card sitting off the navy
// stage. Shows the selected node's facts and its cited source clause(s) (D9). If a
// high-severity finding shares the node's provenance, the flag is surfaced here too.
export default function NodeDetailPanel({
  node,
  citations,
  finding,
}: {
  node: GraphNode | null;
  citations: Citation[];
  finding: Finding | null;
}) {
  if (!node) {
    return (
      <aside className="card self-start p-5">
        <p className="text-sm font-medium text-ink">Node detail</p>
        <p className="mt-1 text-xs text-slate">
          Select a node in the graph to see its roles, relationships, and the source
          clause it was drawn from.
        </p>
      </aside>
    );
  }

  const rows = factRows(node);

  return (
    <aside className="card self-start p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-severity-low">
        {TYPE_LABEL[node.type] ?? node.type}
      </p>
      <h3 className="mt-1 text-lg font-semibold leading-tight text-ink">{node.label}</h3>

      <div className="mt-3">
        {rows.length === 0 && (
          <p className="py-2 text-[13px] text-slate">No additional facts extracted.</p>
        )}
        {rows.map((r) => (
          <div
            key={r.k}
            className="flex items-start justify-between gap-3 border-t border-ink/10 py-2 text-[13px]"
          >
            <span className="shrink-0 text-slate">{r.k}</span>
            <span className={`text-right font-medium ${r.muted ? "text-severity-high" : "text-ink"}`}>
              {r.v}
            </span>
          </div>
        ))}
      </div>

      {finding && (
        <div className="mt-3 border-t border-ink/10 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate">
              Severity
            </span>
            <span className="inline-flex items-center gap-1.5 rounded border-l-[3px] border-l-severity-high bg-severity-high/10 px-2 py-0.5 text-[11px] font-semibold capitalize text-severity-high">
              {finding.severity}
            </span>
          </div>
          <p className="cite-h mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate">
            Why this was flagged
          </p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-slate">{finding.description}</p>
        </div>
      )}

      {citations.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate">
            Cited in
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {citations.map((c, i) => (
              <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

function factRows(node: GraphNode): { k: string; v: string; muted?: boolean }[] {
  const d = node.data as Record<string, unknown>;
  const rows: { k: string; v: string; muted?: boolean }[] = [];
  const joinList = (val: unknown): string =>
    Array.isArray(val) ? val.filter(Boolean).join("; ") : "";

  if (node.type === "deliverable") {
    const detail = typeof d.detail === "string" ? d.detail : "";
    if (detail) rows.push({ k: "Detail", v: detail });
  } else {
    const roles = joinList(d.roles);
    const resp = joinList(d.responsibilities);
    const powers = joinList(d.powers);
    if (roles) rows.push({ k: "Roles", v: roles });
    if (resp) rows.push({ k: "Responsibilities", v: resp });
    if (powers) rows.push({ k: "Powers", v: powers });
  }
  return rows;
}
