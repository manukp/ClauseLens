import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import type {
  AnalysisResult,
  Citation,
  Finding,
  GraphNode,
  Severity,
} from "../lib/types";
import { CitationProvider, type CiteTarget } from "../components/CitationContext";
import AnalysisList from "../components/AnalysisList";
import ProgressTracker from "../components/ProgressTracker";
import PdfViewer from "../components/PdfViewer";
import SeverityCard from "../components/SeverityCard";
import EntityGraph from "../components/EntityGraph";
import NodeDetailPanel from "../components/NodeDetailPanel";
import MasterSummary from "../components/MasterSummary";
import EntitiesList from "../components/EntitiesList";
import StructuredItems from "../components/StructuredItems";

export default function ViewAnalysis() {
  const { jobId } = useParams<{ jobId?: string }>();

  if (!jobId) {
    return (
      <section>
        <h2 className="text-2xl font-semibold text-ink">Analyses</h2>
        <p className="mt-1 text-sm text-slate">
          Open a completed analysis to explore its findings, entity graph, and cited
          clauses — or watch an in-progress run advance through the pipeline.
        </p>
        <div className="mt-6">
          <AnalysisList />
        </div>
      </section>
    );
  }

  return <AnalysisDetail jobId={jobId} />;
}

function AnalysisDetail({ jobId }: { jobId: string }) {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getResult(jobId);
      setResult(r);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !result) {
    return <CenterNote>Loading analysis…</CenterNote>;
  }
  if (error) {
    return (
      <div className="card border-l-4 border-l-severity-high p-6">
        <p className="text-sm font-semibold text-severity-high">Could not load this analysis</p>
        <p className="mt-1 text-sm text-slate">{error}</p>
      </div>
    );
  }
  if (!result) return null;

  const status = result.job.status;
  if (status === "queued" || status === "running") {
    return (
      <ProgressTracker jobId={jobId} jobName={result.job.name} onComplete={load} />
    );
  }
  if (status === "error") {
    return (
      <div className="card border-l-4 border-l-severity-high p-6">
        <p className="text-sm font-semibold text-severity-high">Analysis failed</p>
        <p className="mt-1 text-sm text-slate">
          {result.job.error || "The pipeline did not finish. Try starting a new analysis."}
        </p>
      </div>
    );
  }

  return <ResultView jobId={jobId} result={result} />;
}

type Tab = "findings" | "graph" | "summary" | "entities";

const SEV_RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

function ResultView({ jobId, result }: { jobId: string; result: AnalysisResult }) {
  const [tab, setTab] = useState<Tab>("findings");
  const [target, setTarget] = useState<CiteTarget | null>(null);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);
  const [citeLoading, setCiteLoading] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Clicking any citation chip drives the right-hand PDF viewer. We call the
  // source endpoint (task 2a) but prefer the citation's own narrowed bbox/page
  // (high-severity findings carry a sub-clause-precise box) and fall back to the
  // chunk-level source if the citation lacks geometry.
  const cite = useCallback(
    async (c: Citation) => {
      setActiveChunkId(c.chunk_id);
      setCiteLoading(true);
      try {
        const src = await api.getSource(jobId, c.chunk_id);
        setTarget({
          docId: c.doc_id || src.doc_id,
          docName: c.doc_name || src.doc_name,
          page: c.page || src.page,
          bbox: c.bbox ?? src.bbox,
          text: c.text_span || src.text,
          chunkId: c.chunk_id,
        });
      } catch {
        setTarget({
          docId: c.doc_id,
          docName: c.doc_name,
          page: c.page,
          bbox: c.bbox,
          text: c.text_span,
          chunkId: c.chunk_id,
        });
      } finally {
        setCiteLoading(false);
      }
    },
    [jobId],
  );

  const citationApi = useMemo(
    () => ({ cite, activeChunkId, loading: citeLoading }),
    [cite, activeChunkId, citeLoading],
  );

  // Per-node citations (join graph node ids to entities / structured items) and
  // risk flags (a node sharing a chunk with a high-severity finding).
  const { nodeCitations, flaggedIds, nodeFinding } = useMemo(
    () => deriveGraphMeta(result),
    [result],
  );

  const findings = useMemo(
    () =>
      [...result.findings].sort((a, b) => {
        const s = SEV_RANK[a.severity] - SEV_RANK[b.severity];
        if (s !== 0) return s;
        const fa = a.judge && !a.judge.passed ? 0 : 1;
        const fb = b.judge && !b.judge.passed ? 0 : 1;
        return fa - fb;
      }),
    [result.findings],
  );

  const flaggedCount = findings.filter((f) => f.judge && !f.judge.passed).length;
  const sevCounts = useMemo(() => countBy(findings), [findings]);

  const fallbackDoc =
    result.documents.length > 0
      ? { docId: result.documents[0].doc_id, docName: result.documents[0].doc_name }
      : null;

  const selectedNode = selectedNodeId
    ? result.entity_graph.nodes.find((n) => n.id === selectedNodeId) ?? null
    : null;

  const stepErrors = result.step_errors ?? [];
  const partial = result.job.status === "partial" || stepErrors.length > 0;
  const graphFailed = stepErrors.some((e) => e.step === "build_graph");

  return (
    <CitationProvider value={citationApi}>
      <div className="flex h-[calc(100vh-8.5rem)] flex-col">
        {/* result header */}
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="text-xl font-semibold text-ink">{result.job.name}</h2>
          {partial ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-severity-medium/10 px-2.5 py-1 text-xs font-semibold text-severity-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-severity-medium" />
              Partial analysis
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-severity-low/10 px-2.5 py-1 text-xs font-semibold text-severity-low">
              <span className="h-1.5 w-1.5 rounded-full bg-severity-low" />
              Analysis complete
            </span>
          )}
          <span className="text-xs text-slate">
            {result.documents.map((d) => `${d.doc_name}.pdf`).join(" · ")} · {result.chunk_count} clauses
          </span>
        </div>

        {partial && (
          <div className="mb-3 rounded-md border border-severity-medium/30 bg-severity-medium/[0.06] px-4 py-2.5 text-xs text-severity-medium">
            <span className="font-semibold">Partial results.</span> Some steps did not complete, so
            the analysis below may be incomplete. Failed:{" "}
            {stepErrors.map((e) => e.step).join(", ") || "unknown"}. Everything else was computed and
            remains fully cited.
          </div>
        )}

        {/* split pane */}
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
          {/* left: tabbed report */}
          <div className="flex min-h-0 flex-col">
            <div className="mb-3 flex shrink-0 gap-1 rounded-lg border border-ink/10 bg-white/40 p-1">
              <TabButton id="findings" tab={tab} set={setTab}>
                Findings {findings.length > 0 && <Count>{findings.length}</Count>}
              </TabButton>
              <TabButton id="graph" tab={tab} set={setTab}>
                Graph
              </TabButton>
              <TabButton id="summary" tab={tab} set={setTab}>
                Summary
              </TabButton>
              <TabButton id="entities" tab={tab} set={setTab}>
                Entities {result.entities.length > 0 && <Count>{result.entities.length}</Count>}
              </TabButton>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              {tab === "findings" && (
                <FindingsTab findings={findings} sevCounts={sevCounts} flaggedCount={flaggedCount} />
              )}
              {tab === "graph" && (
                <GraphTab
                  result={result}
                  flaggedIds={flaggedIds}
                  selectedNode={selectedNode}
                  nodeCitations={nodeCitations}
                  nodeFinding={nodeFinding}
                  onSelect={setSelectedNodeId}
                  graphFailed={graphFailed}
                />
              )}
              {tab === "summary" && (
                <div className="space-y-6">
                  <MasterSummary master={result.master_summary} docSummaries={result.doc_summaries} />
                  <div>
                    <h3 className="mb-3 text-sm font-semibold text-ink">Structured items</h3>
                    <StructuredItems items={result.structured_items} />
                  </div>
                </div>
              )}
              {tab === "entities" && <EntitiesList entities={result.entities} />}
            </div>
          </div>

          {/* right: source PDF viewer */}
          <div className="hidden min-h-0 overflow-hidden rounded-lg border border-ink/10 bg-white/60 shadow-card lg:block">
            <PdfViewer jobId={jobId} target={target} fallbackDoc={fallbackDoc} />
          </div>
        </div>
      </div>
    </CitationProvider>
  );
}

function FindingsTab({
  findings,
  sevCounts,
  flaggedCount,
}: {
  findings: Finding[];
  sevCounts: Record<Severity, number>;
  flaggedCount: number;
}) {
  if (findings.length === 0) {
    return (
      <div className="card p-8 text-center">
        <p className="text-sm font-medium text-ink">No findings</p>
        <p className="mt-1 text-sm text-slate">
          The analysis surfaced no risks, gaps, conflicts, or dependencies for this contract.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Tally label="High" n={sevCounts.high} cls="text-severity-high bg-severity-high/10" />
        <Tally label="Medium" n={sevCounts.medium} cls="text-severity-medium bg-severity-medium/10" />
        <Tally label="Low" n={sevCounts.low} cls="text-severity-low bg-severity-low/10" />
        {flaggedCount > 0 && (
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-severity-high/10 px-2.5 py-1 font-semibold text-severity-high">
            {flaggedCount} flagged for review
          </span>
        )}
      </div>
      <GuardrailLegend />
      {findings.map((f) => (
        <SeverityCard key={f.finding_id} finding={f} />
      ))}
    </div>
  );
}

// The three-stage assurance story, made legible for a non-technical panel: every
// finding is grounded (cited), self-checked (reflective loop), then independently
// verified (a separate AI judge). Maps each stage to what the panel sees on a card.
function GuardrailLegend() {
  const steps = [
    { n: "1", label: "Grounded", cls: "text-marigold", desc: "every claim links to its source clause — click a citation" },
    { n: "2", label: "Self-checked", cls: "text-ink", desc: "a reflective loop re-retrieves and regenerates weak answers" },
    { n: "3", label: "Independently verified", cls: "text-severity-low", desc: "a separate AI judge scores correctness and bias" },
  ];
  return (
    <div className="card border border-ink/10 bg-white/50 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate/80">
        How every finding is safeguarded
      </p>
      <ol className="mt-1.5 flex flex-col gap-1.5 text-[12px] leading-snug text-slate sm:flex-row sm:flex-wrap sm:gap-x-5">
        {steps.map((s) => (
          <li key={s.n} className="flex items-baseline gap-1.5">
            <span className={`font-semibold ${s.cls}`}>
              {s.n} · {s.label}
            </span>
            <span className="text-slate/80">— {s.desc}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function GraphTab({
  result,
  flaggedIds,
  selectedNode,
  nodeCitations,
  nodeFinding,
  onSelect,
  graphFailed,
}: {
  result: AnalysisResult;
  flaggedIds: Set<string>;
  selectedNode: GraphNode | null;
  nodeCitations: Record<string, Citation[]>;
  nodeFinding: Record<string, Finding>;
  onSelect: (id: string | null) => void;
  graphFailed: boolean;
}) {
  const node = selectedNode;
  if (graphFailed && result.entity_graph.nodes.length === 0) {
    return (
      <div className="card border-l-4 border-l-severity-medium p-8 text-center">
        <p className="text-sm font-medium text-ink">Graph unavailable</p>
        <p className="mt-1 text-sm text-slate">
          The entity-graph step did not complete for this run. The rest of the analysis —
          summary, entities, structured items, and findings — is unaffected and remains cited.
        </p>
      </div>
    );
  }
  if (result.entity_graph.nodes.length === 0) {
    return (
      <div className="card p-8 text-center">
        <p className="text-sm font-medium text-ink">No graph</p>
        <p className="mt-1 text-sm text-slate">
          Not enough related entities and deliverables were found to build a graph.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="stage h-[440px] overflow-hidden">
        <EntityGraph graph={result.entity_graph} flaggedIds={flaggedIds} onSelect={onSelect} />
      </div>
      <Legend />
      <NodeDetailPanel
        node={node}
        citations={node ? nodeCitations[node.id] ?? [] : []}
        finding={node ? nodeFinding[node.id] ?? null : null}
      />
    </div>
  );
}

function Legend() {
  const items = [
    { c: "#475569", t: "Organisation" },
    { c: "#D97706", t: "Role / person" },
    { c: "#4D7C6F", t: "Deliverable" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-4 px-1 text-xs text-slate">
      {items.map((i) => (
        <span key={i.t} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: i.c }} />
          {i.t}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded" style={{ background: "#5E6B7C" }} />
        Relationship
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded" style={{ background: "#9B2C2C" }} />
        Conflict
      </span>
    </div>
  );
}

function TabButton({
  id,
  tab,
  set,
  children,
}: {
  id: Tab;
  tab: Tab;
  set: (t: Tab) => void;
  children: ReactNode;
}) {
  const active = tab === id;
  return (
    <button
      type="button"
      onClick={() => set(id)}
      className={[
        "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        active ? "bg-ink text-canvas shadow-sm" : "text-slate hover:bg-ink/5",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function Count({ children }: { children: ReactNode }) {
  return <span className="ml-1 text-[11px] tabular-nums opacity-60">({children})</span>;
}

function Tally({ label, n, cls }: { label: string; n: number; cls: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold ${cls}`}>
      {n} {label}
    </span>
  );
}

function CenterNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-64 items-center justify-center text-sm text-slate">{children}</div>
  );
}

function countBy(findings: Finding[]): Record<Severity, number> {
  const c: Record<Severity, number> = { high: 0, medium: 0, low: 0 };
  findings.forEach((f) => {
    if (f.severity in c) c[f.severity] += 1;
  });
  return c;
}

function deriveGraphMeta(result: AnalysisResult): {
  nodeCitations: Record<string, Citation[]>;
  flaggedIds: Set<string>;
  nodeFinding: Record<string, Finding>;
} {
  const nodeCitations: Record<string, Citation[]> = {};
  result.entities.forEach((e) => (nodeCitations[e.entity_id] = e.citations));
  result.structured_items.forEach((it) => (nodeCitations[it.item_id] = it.citations));

  // chunk_id -> a high-severity finding that cites it.
  const chunkToFinding: Record<string, Finding> = {};
  result.findings
    .filter((f) => f.severity === "high")
    .forEach((f) => {
      f.citations.forEach((c) => {
        if (!chunkToFinding[c.chunk_id]) chunkToFinding[c.chunk_id] = f;
      });
    });

  const flaggedIds = new Set<string>();
  const nodeFinding: Record<string, Finding> = {};
  result.entity_graph.nodes.forEach((n) => {
    const cites = nodeCitations[n.id] ?? [];
    for (const c of cites) {
      const f = chunkToFinding[c.chunk_id];
      if (f) {
        flaggedIds.add(n.id);
        nodeFinding[n.id] = f;
        break;
      }
    }
  });

  return { nodeCitations, flaggedIds, nodeFinding };
}
