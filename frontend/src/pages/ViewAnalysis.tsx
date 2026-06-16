// Stub — split-pane citation viewer + entity graph + severity cards land in Phase 4.
export default function ViewAnalysis() {
  return (
    <section>
      <h2 className="text-2xl font-semibold text-ink">View analysis</h2>
      <p className="mt-1 text-sm text-slate">
        Findings with clickable citations, the entity graph, and severity cards
        will render here.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <p className="text-sm font-medium text-ink">Findings &amp; citations</p>
          <p className="mt-1 text-xs text-slate">Report pane placeholder.</p>
        </div>
        <div className="stage p-6">
          <p className="text-sm font-medium text-canvas">Entity graph</p>
          <p className="mt-1 text-xs text-canvas/60">
            Data visualizations render on the dark stage.
          </p>
        </div>
      </div>
    </section>
  );
}
