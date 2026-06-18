import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Job } from "../lib/types";
import { fmtClock } from "../lib/format";

// Previous + in-progress analyses (task 3). Polls the list every 2.5s while any
// job is running so in-progress jobs show their advancing stage live.
export default function AnalysisList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const load = async () => {
      try {
        const list = await api.listAnalyses();
        if (!active) return;
        setJobs(list);
        setError(null);
        const anyRunning = list.some((j) => j.status === "running" || j.status === "queued");
        if (anyRunning) timer = setTimeout(load, 2500);
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  if (error) {
    return (
      <div className="card border-l-4 border-l-severity-high p-5">
        <p className="text-sm font-semibold text-severity-high">Could not load analyses</p>
        <p className="mt-1 text-sm text-slate">{error}</p>
      </div>
    );
  }

  if (!jobs) {
    return <p className="text-sm text-slate">Loading analyses…</p>;
  }

  if (jobs.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-12 text-center">
        <p className="text-base font-semibold text-ink">No analyses yet</p>
        <p className="mt-1 max-w-sm text-sm text-slate">
          Upload one or more contract PDFs to surface risks, gaps, conflicts, and
          deliverables — each traceable to its source clause.
        </p>
        <Link
          to="/new"
          className="mt-4 rounded-md bg-marigold px-4 py-2 text-sm font-semibold text-white shadow-card transition-colors hover:bg-marigold/90"
        >
          Start a new analysis
        </Link>
      </div>
    );
  }

  const sorted = [...jobs].sort((a, b) => b.created_ts - a.created_ts);

  return (
    <ul className="space-y-2.5">
      {sorted.map((job) => (
        <li key={job.job_id}>
          <Link
            to={`/analysis/${job.job_id}`}
            className="card flex items-center justify-between gap-4 p-4 transition-shadow hover:shadow-lg"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{job.name}</p>
              <p className="mt-0.5 text-xs text-slate">Created {fmtClock(job.created_ts)}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {(job.status === "running" || job.status === "queued") && job.current_substep && (
                <span className="hidden text-xs text-marigold sm:inline">
                  {job.current_substep}
                </span>
              )}
              <StatusBadge job={job} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function StatusBadge({ job }: { job: Job }) {
  const map: Record<Job["status"], { label: string; cls: string; dot: string }> = {
    complete: { label: "Complete", cls: "bg-severity-low/10 text-severity-low", dot: "bg-severity-low" },
    partial: { label: "Partial", cls: "bg-severity-medium/10 text-severity-medium", dot: "bg-severity-medium" },
    running: { label: "Running", cls: "bg-marigold/10 text-marigold", dot: "bg-marigold animate-pulse" },
    queued: { label: "Queued", cls: "bg-ink/[0.06] text-slate", dot: "bg-slate" },
    error: { label: "Error", cls: "bg-severity-high/10 text-severity-high", dot: "bg-severity-high" },
  };
  const m = map[job.status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${m.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}
