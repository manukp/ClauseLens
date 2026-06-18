import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { StatusResponse } from "../lib/types";
import { STAGES, STAGE_DONE, stageIndex } from "../lib/stages";
import { fmtClock, fmtElapsed } from "../lib/format";

// Live progress for an in-progress job (task 3). Polls /status every 2.5s and
// animates the stage progression — doubles as a demo narration device. Calls
// onComplete once the run finishes so the parent can swap in the result view.
export default function ProgressTracker({
  jobId,
  jobName,
  onComplete,
}: {
  jobId: string;
  jobName: string;
  onComplete: () => void;
}) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const completedRef = useRef(false);
  // Re-render every second so the elapsed timer ticks between polls.
  const [, setTick] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const s = await api.getStatus(jobId);
        if (!active) return;
        setStatus(s);
        if (s.status === "complete" && !completedRef.current) {
          completedRef.current = true;
          onComplete();
          return;
        }
        if (s.status === "error") {
          setError(s.error || "The analysis failed.");
          return;
        }
      } catch (e) {
        if (active) setError((e as Error).message);
        return;
      }
      timer = setTimeout(poll, 2500);
    };
    poll();

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId, onComplete]);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const idx = status ? stageIndex(status) : -1;

  if (error) {
    return (
      <div className="card border-l-4 border-l-severity-high p-6">
        <p className="text-sm font-semibold text-severity-high">Analysis failed</p>
        <p className="mt-1 text-sm text-slate">{error}</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-ink">{jobName}</h2>
          <p className="mt-0.5 text-sm text-slate">
            {status?.status === "queued" ? "Queued — starting shortly" : "Analysis in progress"}
          </p>
        </div>
        <div className="text-right text-xs text-slate">
          <p>Started {fmtClock(status?.started_ts)}</p>
          <p className="mt-0.5 tabular-nums">Elapsed {fmtElapsed(status?.started_ts)}</p>
        </div>
      </div>

      <ol className="mt-5 space-y-1">
        {STAGES.map((stage, i) => {
          const state = idx === STAGE_DONE || i < idx ? "done" : i === idx ? "active" : "pending";
          return (
            <li key={stage.label} className="flex items-center gap-3 py-1.5">
              <Dot state={state} />
              <span
                className={[
                  "text-sm",
                  state === "done" ? "text-ink/70" : state === "active" ? "font-medium text-ink" : "text-slate/50",
                ].join(" ")}
              >
                {stage.label}
              </span>
              {state === "active" && (
                <span className="ml-auto text-[11px] uppercase tracking-wide text-marigold">
                  {status?.current_substep}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Dot({ state }: { state: "done" | "active" | "pending" }) {
  if (state === "done") {
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-severity-low text-[11px] text-white">
        ✓
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="relative grid h-5 w-5 shrink-0 place-items-center">
        <span className="absolute h-5 w-5 animate-ping rounded-full bg-marigold/40" />
        <span className="h-2.5 w-2.5 rounded-full bg-marigold" />
      </span>
    );
  }
  return <span className="ml-1 mr-1 h-3 w-3 shrink-0 rounded-full border border-slate/30" />;
}
