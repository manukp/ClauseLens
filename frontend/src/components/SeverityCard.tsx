import type { Finding, Severity } from "../lib/types";
import CitationChip from "./CitationChip";

// Severity treatment per the locked tokens: a colored LEFT BORDER + a static
// chip (never the interactive marigold). The judge verdict is surfaced inline on
// the card itself (D11) — a low/failed verdict gets a distinct "needs review"
// treatment (dashed garnet ring + banner) so the guardrail is visible to the panel.

const SEV: Record<Severity, { label: string; color: string; tint: string; border: string }> = {
  high: { label: "High", color: "text-severity-high", tint: "bg-severity-high/10", border: "border-l-severity-high" },
  medium: { label: "Medium", color: "text-severity-medium", tint: "bg-severity-medium/10", border: "border-l-severity-medium" },
  low: { label: "Low", color: "text-severity-low", tint: "bg-severity-low/10", border: "border-l-severity-low" },
};

export default function SeverityCard({ finding }: { finding: Finding }) {
  const sev = SEV[finding.severity] ?? SEV.medium;
  const judge = finding.judge;
  const flagged = judge != null && !judge.passed;

  return (
    <article
      className={[
        "card border-l-4 p-4",
        sev.border,
        flagged ? "outline outline-2 outline-offset-2 outline-dashed outline-severity-high/60" : "",
      ].join(" ")}
    >
      {flagged && (
        <div className="-mx-4 -mt-4 mb-3 flex items-center gap-2 rounded-t-lg border-b border-severity-high/20 bg-severity-high/[0.06] px-4 py-2 text-xs font-semibold text-severity-high">
          <span className="grid h-4 w-4 place-items-center rounded-full bg-severity-high text-[10px] text-white">
            !
          </span>
          Needs review — judge flagged this finding
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded border-l-[3px] ${sev.border} ${sev.tint} px-2 py-0.5 text-[11px] font-semibold ${sev.color}`}
          >
            {sev.label}
          </span>
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate">
            {finding.type}
          </span>
        </div>
        {judge && <JudgeBadge passed={judge.passed} score={judge.score} />}
      </div>

      <h4 className="mt-2 text-sm font-semibold leading-snug text-ink">{finding.title}</h4>
      {finding.description && (
        <p className="mt-1 text-[13px] leading-relaxed text-slate">{finding.description}</p>
      )}

      {finding.mitigation && (
        <div className="mt-2.5 rounded-md bg-ink/[0.03] px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate/80">
            Mitigation
          </p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-ink/80">{finding.mitigation}</p>
        </div>
      )}

      {judge?.note && (
        <p
          className={`mt-2 text-xs italic leading-relaxed ${
            flagged ? "text-severity-high/90" : "text-slate"
          }`}
        >
          <span className="font-medium not-italic">Judge:</span> {judge.note}
        </p>
      )}

      {finding.citations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {finding.citations.map((c, i) => (
            <CitationChip key={`${c.chunk_id}-${i}`} citation={c} />
          ))}
        </div>
      )}
    </article>
  );
}

function JudgeBadge({ passed, score }: { passed: boolean; score: number }) {
  return (
    <span
      className={[
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold",
        passed
          ? "bg-severity-low/10 text-severity-low"
          : "bg-severity-high/10 text-severity-high",
      ].join(" ")}
      title={passed ? "Passed the LLM-as-judge correctness check" : "Flagged by the LLM-as-judge"}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${passed ? "bg-severity-low" : "bg-severity-high"}`} />
      {passed ? "Judge passed" : "Judge flagged"} · {score.toFixed(2)}
    </span>
  );
}
