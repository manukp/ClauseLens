import type { DocSummary, MasterSummary as MasterSummaryT } from "../lib/types";
import CitationChip from "./CitationChip";

// Master summary (Sonnet) + per-document summaries (Haiku), each cited (D9).
export default function MasterSummary({
  master,
  docSummaries,
}: {
  master: MasterSummaryT | null;
  docSummaries: DocSummary[];
}) {
  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate">
          Master summary
        </p>
        {master?.summary ? (
          <p className="mt-2 whitespace-pre-line text-[14px] leading-relaxed text-ink/90">
            {master.summary}
          </p>
        ) : (
          <p className="mt-2 text-sm text-slate">No master summary was produced.</p>
        )}
        {master?.citations?.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {master.citations.map((c, i) => (
              <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
            ))}
          </div>
        ) : null}
      </section>

      {docSummaries.map((d) => (
        <section key={d.doc_id} className="card p-5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate">
            {d.doc_name}.pdf
          </p>
          <p className="mt-2 whitespace-pre-line text-[13px] leading-relaxed text-slate">
            {d.summary}
          </p>
          {d.citations?.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {d.citations.map((c, i) => (
                <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
              ))}
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
