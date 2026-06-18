import type { Entity } from "../lib/types";
import CitationChip from "./CitationChip";

// Extracted parties / people, each cited (D9).
export default function EntitiesList({ entities }: { entities: Entity[] }) {
  if (entities.length === 0) {
    return <p className="text-sm text-slate">No entities were extracted.</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {entities.map((e) => (
        <article key={e.entity_id} className="card p-4">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-ink">{e.name}</h4>
            <span className="shrink-0 rounded-full bg-ink/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate">
              {e.type}
            </span>
          </div>
          {e.roles.length > 0 && (
            <p className="mt-1.5 text-[12.5px] text-slate">
              <span className="font-medium text-ink/70">Roles:</span> {e.roles.join("; ")}
            </p>
          )}
          {e.responsibilities.length > 0 && (
            <p className="mt-1 text-[12.5px] text-slate">
              <span className="font-medium text-ink/70">Responsibilities:</span>{" "}
              {e.responsibilities.join("; ")}
            </p>
          )}
          {e.powers.length > 0 && (
            <p className="mt-1 text-[12.5px] text-slate">
              <span className="font-medium text-ink/70">Powers:</span> {e.powers.join("; ")}
            </p>
          )}
          {e.citations.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {e.citations.slice(0, 4).map((c, i) => (
                <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
