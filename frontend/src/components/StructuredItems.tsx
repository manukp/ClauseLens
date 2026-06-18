import type { StructuredItem } from "../lib/types";
import CitationChip from "./CitationChip";

// Stage-2 structured extractions grouped by category, each cited (D9).
const CATEGORY_ORDER = ["deliverable", "owner", "budget", "timeline", "plan", "compliance"];
const CATEGORY_LABEL: Record<string, string> = {
  deliverable: "Deliverables",
  owner: "Owners",
  budget: "Budgets",
  timeline: "Timelines",
  plan: "Plans",
  compliance: "Compliance",
};

export default function StructuredItems({ items }: { items: StructuredItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-slate">No structured items were extracted.</p>;
  }
  const byCat = new Map<string, StructuredItem[]>();
  items.forEach((it) => {
    const arr = byCat.get(it.category) ?? [];
    arr.push(it);
    byCat.set(it.category, arr);
  });
  const cats = [
    ...CATEGORY_ORDER.filter((c) => byCat.has(c)),
    ...[...byCat.keys()].filter((c) => !CATEGORY_ORDER.includes(c)),
  ];

  return (
    <div className="space-y-5">
      {cats.map((cat) => (
        <section key={cat}>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate">
            {CATEGORY_LABEL[cat] ?? cat} · {byCat.get(cat)!.length}
          </p>
          <div className="space-y-2.5">
            {byCat.get(cat)!.map((it) => (
              <article key={it.item_id} className="card p-4">
                <h4 className="text-sm font-semibold text-ink">{it.title}</h4>
                {it.detail && (
                  <p className="mt-1 text-[13px] leading-relaxed text-slate">{it.detail}</p>
                )}
                {Object.keys(it.attributes).length > 0 && (
                  <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                    {Object.entries(it.attributes).map(([k, v]) => (
                      <div key={k} className="flex gap-1.5 text-[12.5px]">
                        <dt className="font-medium capitalize text-ink/70">
                          {k.replace(/_/g, " ")}:
                        </dt>
                        <dd className="text-slate">{v}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {it.citations.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {it.citations.map((c, i) => (
                      <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
