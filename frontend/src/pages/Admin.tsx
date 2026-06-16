// Stub — cost Sankey + per-call latency table land in Phase 4 (powered by D13 logs).
export default function Admin() {
  return (
    <section>
      <h2 className="text-2xl font-semibold text-ink">Admin</h2>
      <p className="mt-1 text-sm text-slate">
        Observability: per-call token usage, latency, and cost across model
        tiers.
      </p>

      <div className="stage mt-6 p-8">
        <p className="text-sm font-medium text-canvas">Cost Sankey</p>
        <p className="mt-1 text-xs text-canvas/60">
          Model-call flow and spend will render on the stage here.
        </p>
      </div>

      <div className="card mt-6 p-6">
        <p className="text-sm font-medium text-ink">Model-call log</p>
        <p className="mt-1 text-xs text-slate">Latency table placeholder.</p>
      </div>
    </section>
  );
}
