// Stub — the upload + launch form lands in Phase 4.
export default function NewAnalysis() {
  return (
    <section className="max-w-3xl">
      <h2 className="text-2xl font-semibold text-ink">New analysis</h2>
      <p className="mt-1 text-sm text-slate">
        Upload contract PDFs to extract risks, gaps, conflicts, deliverables,
        owners and dependencies — each traceable to its source clause.
      </p>

      <div className="card mt-6 p-8">
        <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-ink/20 py-14 text-center">
          <p className="text-sm font-medium text-ink">Upload area</p>
          <p className="mt-1 text-xs text-slate">
            PDF ingest and analysis arrive in a later phase.
          </p>
        </div>
      </div>
    </section>
  );
}
