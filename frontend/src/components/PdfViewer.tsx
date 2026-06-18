import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Document, Page } from "../lib/pdf";
import { api } from "../lib/api";
import type { CiteTarget } from "./CitationContext";

// Right pane of the split view. Renders the source PDF and, when a citation is
// clicked, scrolls to the page and paints a marigold highlight over the cited
// clause's bbox. Coordinates are PDF points (PyMuPDF, top-left origin) mapped to
// percentages of each page's point dimensions, so the overlay tracks the render
// at any width.
export default function PdfViewer({
  jobId,
  target,
  fallbackDoc,
}: {
  jobId: string;
  target: CiteTarget | null;
  fallbackDoc: { docId: string; docName: string } | null;
}) {
  const docId = target?.docId ?? fallbackDoc?.docId ?? null;
  const docName = target?.docName ?? fallbackDoc?.docName ?? "";

  const scrollRef = useRef<HTMLDivElement>(null);
  const pageEls = useRef<Record<number, HTMLDivElement | null>>({});
  const [numPages, setNumPages] = useState(0);
  const [renderWidth, setRenderWidth] = useState(0);
  // Per-page point dimensions (from the PDF page itself), for the overlay maths.
  const [pageDims, setPageDims] = useState<Record<number, { w: number; h: number }>>({});
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Track the render width so pages fill the pane and the overlay stays aligned.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setRenderWidth(el.clientWidth - 32); // minus padding
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Reset when the document changes.
  useEffect(() => {
    setNumPages(0);
    setPageDims({});
    setError(null);
    setLoaded(false);
    pageEls.current = {};
  }, [docId]);

  const onDocLoad = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    setLoaded(true);
  }, []);

  // Scroll the targeted page into view once it (and its dimensions) exist.
  useEffect(() => {
    if (!target || !loaded) return;
    const el = pageEls.current[target.page];
    const container = scrollRef.current;
    if (!el || !container) return;
    const top = el.offsetTop - 12;
    container.scrollTo({ top, behavior: "smooth" });
  }, [target, loaded, pageDims]);

  const docUrl = docId ? api.documentUrl(jobId, docId) : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-ink/10 px-4 py-2.5">
        <p className="truncate text-xs font-medium text-slate">
          {docName ? `${docName}.pdf` : "Source document"}
        </p>
        {target && (
          <span className="shrink-0 text-[11px] text-marigold">
            Cited · page {target.page}
          </span>
        )}
      </div>

      <div ref={scrollRef} className="relative flex-1 overflow-auto bg-ink/[0.03] p-4">
        {!docUrl && (
          <EmptyHint />
        )}
        {error && (
          <div className="m-4 rounded-md border border-severity-high/30 bg-severity-high/5 p-4 text-sm text-severity-high">
            Could not load the source PDF: {error}
          </div>
        )}
        {docUrl && (
          <Document
            key={docUrl}
            file={docUrl}
            onLoadSuccess={onDocLoad}
            onLoadError={(e) => setError(e.message)}
            loading={<ViewerSpinner label="Loading document…" />}
            error={null}
          >
            {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNo) => {
              const isTarget = target?.page === pageNo;
              const dims = pageDims[pageNo];
              return (
                <div
                  key={pageNo}
                  ref={(el) => (pageEls.current[pageNo] = el)}
                  className="relative mx-auto mb-4 w-fit shadow-card"
                >
                  <Page
                    pageNumber={pageNo}
                    width={renderWidth > 0 ? renderWidth : undefined}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    onLoadSuccess={(p) =>
                      setPageDims((d) =>
                        d[pageNo]
                          ? d
                          : { ...d, [pageNo]: { w: p.originalWidth, h: p.originalHeight } },
                      )
                    }
                  />
                  {/* page number tab */}
                  <span className="pointer-events-none absolute right-1 top-1 rounded bg-ink/55 px-1.5 py-0.5 text-[10px] font-medium text-canvas">
                    {pageNo}
                  </span>
                  {isTarget && target?.bbox && dims && (
                    <Highlight bbox={target.bbox} dims={dims} />
                  )}
                </div>
              );
            })}
          </Document>
        )}
      </div>
    </div>
  );
}

function Highlight({
  bbox,
  dims,
}: {
  bbox: [number, number, number, number];
  dims: { w: number; h: number };
}) {
  const [x0, y0, x1, y1] = bbox;
  const style = {
    left: `${(x0 / dims.w) * 100}%`,
    top: `${(y0 / dims.h) * 100}%`,
    width: `${((x1 - x0) / dims.w) * 100}%`,
    height: `${((y1 - y0) / dims.h) * 100}%`,
  };
  return (
    <div
      className="pointer-events-none absolute rounded-[3px] bg-marigold/25 ring-2 ring-marigold animate-[pulse_1.6s_ease-in-out_2]"
      style={style}
    />
  );
}

function EmptyHint() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-lg bg-marigold/10 text-marigold">
        §
      </div>
      <p className="mt-3 text-sm font-medium text-ink">No source loaded</p>
      <p className="mt-1 max-w-xs text-xs text-slate">
        Click a citation chip on any finding, entity, or graph node to jump to its
        clause in the contract.
      </p>
    </div>
  );
}

function ViewerSpinner({ label }: { label: string }) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-3 text-slate">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-marigold/30 border-t-marigold" />
      <span className="text-xs">{label}</span>
    </div>
  );
}
