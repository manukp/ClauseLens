import type { Citation } from "../lib/types";
import { useCitation } from "./CitationContext";

// The citation chip — marigold is reserved for exactly this (interactive / AI /
// citation accent). Clicking it drives the split-pane PDF viewer to the source
// clause. This is the product's centerpiece interaction (D9).
export default function CitationChip({
  citation,
  className = "",
}: {
  citation: Citation;
  className?: string;
}) {
  const { cite, activeChunkId, loading } = useCitation();
  const active = activeChunkId === citation.chunk_id;

  return (
    <button
      type="button"
      onClick={() => cite(citation)}
      title={citation.text_span}
      className={[
        "group inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-left text-xs font-medium transition-colors",
        active
          ? "border-marigold bg-marigold/15 text-marigold"
          : "border-marigold/30 bg-marigold/[0.07] text-marigold hover:bg-marigold/15",
        className,
      ].join(" ")}
    >
      <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-marigold text-[10px] font-semibold text-white">
        §
      </span>
      <span className="truncate">
        {citation.doc_name} · p.{citation.page}
      </span>
      {active && loading && (
        <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-marigold/30 border-t-marigold" />
      )}
    </button>
  );
}
