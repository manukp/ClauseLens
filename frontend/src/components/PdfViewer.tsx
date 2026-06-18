import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "../lib/pdf";
import { api } from "../lib/api";
import type { CiteTarget } from "./CitationContext";

// Right pane of the split view. Renders the source PDF and, when a citation is
// clicked, scrolls to the cited clause and paints a marigold highlight over its
// bbox. Coordinates are PDF points (PyMuPDF, top-left origin) mapped to
// percentages of each page's point dimensions, so the overlay tracks the render
// at any width.
//
// Scroll correctness (see IMPLEMENTATION_LOG "render-then-scroll timing"): the
// scroll must run against the POST-render layout, otherwise the target offset is
// computed before react-pdf has painted the page (and before the pages above it
// have their real height) and lands in the wrong place. Two guards make it
// reliable: (1) every page reserves its height from its aspect ratio up-front, so
// pages above the target occupy correct space even before they paint; (2) the
// scroll is gated on the target page's onRenderSuccess and measures the live
// highlight element via getBoundingClientRect, then centres it in the pane.
const DEFAULT_ASPECT = 11 / 8.5; // US-Letter fallback before any page is measured

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
  const highlightRef = useRef<HTMLDivElement>(null);
  const pageEls = useRef<Record<number, HTMLDivElement | null>>({});
  // The target object we have already scrolled to. cite() makes a fresh object
  // on every click, so identity comparison re-scrolls even for the same clause.
  const scrolledTargetRef = useRef<CiteTarget | null>(null);

  const [numPages, setNumPages] = useState(0);
  const [renderWidth, setRenderWidth] = useState(0);
  // Per-page point dimensions (from the PDF page itself), for the overlay maths.
  const [pageDims, setPageDims] = useState<Record<number, { w: number; h: number }>>({});
  // Pages whose canvas has finished painting (layout settled) — the scroll gate.
  const [renderedPages, setRenderedPages] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

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
    setRenderedPages(new Set());
    setError(null);
    scrolledTargetRef.current = null;
    pageEls.current = {};
  }, [docId]);

  // Aspect ratio used to reserve height for pages not yet measured. Contract PDFs
  // have uniform page sizes, so the first measured page generalises accurately.
  const defaultAspect = useMemo(() => {
    const first = Object.values(pageDims)[0];
    return first ? first.h / first.w : DEFAULT_ASPECT;
  }, [pageDims]);

  // Scroll the cited clause into view — only once the target page has rendered, so
  // the measured offset reflects the final layout.
  useEffect(() => {
    if (!target) return;
    if (scrolledTargetRef.current === target) return;
    if (!renderedPages.has(target.page)) return; // wait for the page to paint
    const container = scrollRef.current;
    const el = highlightRef.current ?? pageEls.current[target.page];
    if (!container || !el) return;

    const raf = requestAnimationFrame(() => {
      const cRect = container.getBoundingClientRect();
      const eRect = el.getBoundingClientRect();
      const elTopWithin = eRect.top - cRect.top + container.scrollTop;
      // Centre the clause in the pane (clamped to the scrollable range).
      const top = elTopWithin - container.clientHeight / 2 + eRect.height / 2;
      container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
      scrolledTargetRef.current = target;
    });
    return () => cancelAnimationFrame(raf);
  }, [target, renderedPages, renderWidth]);

  const docUrl = docId ? api.documentUrl(jobId, docId) : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-ink/10 px-4 py-2.5">
        <p className="truncate text-xs font-medium text-slate">
          {docName ? `${docName}.pdf` : "Source document"}
        </p>
        {target && (
          <span className="shrink-0 text-[11px] text-marigold">Cited · page {target.page}</span>
        )}
      </div>

      <div ref={scrollRef} className="relative flex-1 overflow-auto bg-ink/[0.03] p-4">
        {!docUrl && <EmptyHint />}
        {error && (
          <div className="m-4 rounded-md border border-severity-high/30 bg-severity-high/5 p-4 text-sm text-severity-high">
            Could not load the source PDF: {error}
          </div>
        )}
        {docUrl && (
          <Document
            key={docUrl}
            file={docUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={(e) => setError(e.message)}
            loading={<ViewerSpinner label="Loading document…" />}
            error={null}
          >
            {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNo) => {
              const isTarget = target?.page === pageNo;
              const dims = pageDims[pageNo];
              const aspect = dims ? dims.h / dims.w : defaultAspect;
              return (
                <div
                  key={pageNo}
                  ref={(el) => (pageEls.current[pageNo] = el)}
                  className="relative mx-auto mb-4 w-fit shadow-card"
                  // Reserve vertical space from the aspect ratio so the scroll
                  // offset is correct even before this page's canvas paints.
                  style={{ minHeight: renderWidth > 0 ? renderWidth * aspect : undefined }}
                >
                  <Page
                    pageNumber={pageNo}
                    width={renderWidth > 0 ? renderWidth : undefined}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    onLoadSuccess={(p) =>
                      setPageDims((d) =>
                        d[pageNo] ? d : { ...d, [pageNo]: { w: p.originalWidth, h: p.originalHeight } },
                      )
                    }
                    onRenderSuccess={() =>
                      setRenderedPages((s) => (s.has(pageNo) ? s : new Set(s).add(pageNo)))
                    }
                  />
                  {/* page number tab */}
                  <span className="pointer-events-none absolute right-1 top-1 rounded bg-ink/55 px-1.5 py-0.5 text-[10px] font-medium text-canvas">
                    {pageNo}
                  </span>
                  {isTarget && target?.bbox && dims && (
                    <div
                      ref={highlightRef}
                      className="pointer-events-none absolute rounded-[3px] bg-marigold/25 ring-2 ring-marigold animate-[pulse_1.6s_ease-in-out_2]"
                      style={{
                        left: `${(target.bbox[0] / dims.w) * 100}%`,
                        top: `${(target.bbox[1] / dims.h) * 100}%`,
                        width: `${((target.bbox[2] - target.bbox[0]) / dims.w) * 100}%`,
                        height: `${((target.bbox[3] - target.bbox[1]) / dims.h) * 100}%`,
                      }}
                    />
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

function EmptyHint() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-lg bg-marigold/10 text-marigold">§</div>
      <p className="mt-3 text-sm font-medium text-ink">No source loaded</p>
      <p className="mt-1 max-w-xs text-xs text-slate">
        Click a citation chip on any finding, entity, or graph node to jump to its clause in the
        contract.
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
