import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { Job, Observability } from "../lib/types";
import CostSankey from "../components/CostSankey";
import { fmtCost, fmtDuration, fmtLatency, fmtTokens, tierMeta } from "../lib/format";

// Admin / observability (task 5): cost Sankey on the navy stage + metric cards +
// per-step latency table, from GET /observability (D13). Sankey ribbon = cost;
// table carries latency.
export default function Admin() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [obs, setObs] = useState<Observability | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .listAnalyses()
      .then((list) => {
        setJobs(list);
        const firstComplete = [...list].sort((a, b) => b.created_ts - a.created_ts).find((j) => j.status === "complete");
        setJobId(firstComplete?.job_id ?? list[0]?.job_id ?? null);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    setLoading(true);
    api
      .getObservability(jobId)
      .then((o) => {
        setObs(o);
        setError(null);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [jobId]);

  const job = jobs?.find((j) => j.job_id === jobId) ?? null;

  const rows = useMemo(() => (obs ? perStepRows(obs) : []), [obs]);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-ink">Admin · observability</h2>
          <p className="mt-1 text-sm text-slate">
            Per-call token usage, latency, and cost across model tiers (D13).
          </p>
        </div>
        {jobs && jobs.length > 0 && (
          <label className="text-xs text-slate">
            <span className="mr-2">Analysis</span>
            <select
              value={jobId ?? ""}
              onChange={(e) => setJobId(e.target.value)}
              className="rounded-md border border-ink/15 bg-white px-2 py-1.5 text-sm text-ink outline-none focus:border-marigold focus:ring-2 focus:ring-marigold/30"
            >
              {[...jobs]
                .sort((a, b) => b.created_ts - a.created_ts)
                .map((j) => (
                  <option key={j.job_id} value={j.job_id}>
                    {j.name} {j.status !== "complete" ? `(${j.status})` : ""}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>

      {error && (
        <div className="card mt-6 border-l-4 border-l-severity-high p-5">
          <p className="text-sm font-semibold text-severity-high">Could not load observability</p>
          <p className="mt-1 text-sm text-slate">{error}</p>
        </div>
      )}

      {jobs && jobs.length === 0 && !error && (
        <div className="card mt-6 p-10 text-center">
          <p className="text-sm font-medium text-ink">No runs to report on</p>
          <p className="mt-1 text-sm text-slate">Start an analysis to populate the cost and latency view.</p>
        </div>
      )}

      {obs && !error && (
        <div className="mt-6 space-y-6">
          <Cards obs={obs} job={job} />

          <div>
            <p className="mb-2.5 text-[12px] font-semibold uppercase tracking-wide text-slate">
              Cost attribution by step and model
            </p>
            <div className="stage relative overflow-x-auto p-4">
              <div className="absolute right-5 top-4 z-10 flex gap-4 text-xs text-canvas/70">
                <Legend color="#6FA8B8" label="Haiku 4.5" />
                <Legend color="#8E84C8" label="Sonnet 4.6" />
                <Legend color="#4D7C6F" label="Titan embed" />
              </div>
              {loading ? (
                <p className="py-12 text-center text-sm text-canvas/60">Loading…</p>
              ) : (
                <CostSankey obs={obs} />
              )}
            </div>
          </div>

          <div>
            <p className="mb-2.5 text-[12px] font-semibold uppercase tracking-wide text-slate">
              Per-step detail
            </p>
            <div className="card overflow-hidden p-0">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-ink/[0.04]">
                    <Th>Pipeline step</Th>
                    <Th>Model</Th>
                    <Th right>Tokens in / out</Th>
                    <Th right>Avg latency</Th>
                    <Th right>Calls</Th>
                    <Th right>Cost</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const tm = tierMeta(r.tier);
                    return (
                      <tr key={r.step} className="border-t border-ink/10">
                        <Td>{r.step}</Td>
                        <Td>
                          <span
                            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium"
                            style={{ background: `${tm.color}28`, color: tm.color }}
                          >
                            <span className="h-1.5 w-1.5 rounded-[2px]" style={{ background: tm.color }} />
                            {tm.label}
                          </span>
                        </Td>
                        <Td right>
                          {fmtTokens(r.tokens_in)} / {fmtTokens(r.tokens_out)}
                        </Td>
                        <Td right>{fmtLatency(r.avg_latency)}</Td>
                        <Td right>{r.calls}</Td>
                        <Td right>{fmtCost(r.cost)}</Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Cards({ obs, job }: { obs: Observability; job: Job | null }) {
  const t = obs.totals;
  const haiku = obs.by_tier["haiku"];
  const sonnet = obs.by_tier["sonnet"];
  const wall =
    job?.started_ts && job?.finished_ts
      ? fmtDuration(job.finished_ts - job.started_ts)
      : fmtDuration(t.latency_ms / 1000);
  const distinctSteps = Object.keys(obs.by_step).length;

  return (
    <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
      <Card label="Total cost" value={fmtCost(t.cost_usd)} sub="this analysis run" />
      <Card
        label="Tokens processed"
        value={fmtTokens(t.tokens_in + t.tokens_out)}
        sub={`${fmtTokens((haiku?.tokens_in ?? 0) + (haiku?.tokens_out ?? 0))} Haiku · ${fmtTokens(
          (sonnet?.tokens_in ?? 0) + (sonnet?.tokens_out ?? 0),
        )} Sonnet`}
      />
      <Card label="Wall-clock time" value={wall} sub="across both stages" />
      <Card label="Prompt runs" value={`${t.calls}`} sub={`${distinctSteps} distinct steps`} />
    </div>
  );
}

function Card({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      <p className="mt-0.5 text-xs text-slate">{sub}</p>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-3.5 rounded-[3px]" style={{ background: color }} />
      {label}
    </span>
  );
}

function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <th
      className={`px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-slate ${
        right ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

function Td({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <td className={`px-4 py-2.5 text-[13px] text-ink ${right ? "text-right tabular-nums" : "text-left"}`}>
      {children}
    </td>
  );
}

interface StepRow {
  step: string;
  tier: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  avg_latency: number;
  calls: number;
  cost: number;
}

function perStepRows(obs: Observability): StepRow[] {
  const map = new Map<string, StepRow>();
  for (const log of obs.logs) {
    const step = log.step || "unknown";
    const r =
      map.get(step) ??
      ({
        step: prettyStep(step),
        tier: log.tier,
        model: log.model_id,
        tokens_in: 0,
        tokens_out: 0,
        avg_latency: 0,
        calls: 0,
        cost: 0,
      } as StepRow);
    r.tokens_in += log.tokens_in || 0;
    r.tokens_out += log.tokens_out || 0;
    r.avg_latency += log.latency_ms || 0; // sum now; averaged below
    r.calls += 1;
    r.cost += log.cost_usd || 0;
    map.set(step, r);
  }
  const rows = [...map.values()].map((r) => ({ ...r, avg_latency: r.calls ? r.avg_latency / r.calls : 0 }));
  return rows.sort((a, b) => b.cost - a.cost);
}

function prettyStep(step: string): string {
  const s = step.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
