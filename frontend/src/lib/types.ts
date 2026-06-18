// Shapes mirror backend/app/models/schemas.py + the Result API (see
// .claude/IMPLEMENTATION_LOG.md → Interface contracts). Keep in sync.

export type Bbox = [number, number, number, number];

export interface Citation {
  doc_id: string;
  doc_name: string;
  page: number; // 1-based
  bbox: Bbox | null;
  text_span: string;
  chunk_id: string;
}

export type JobStatusValue = "queued" | "running" | "complete" | "error";

export interface Job {
  job_id: string;
  name: string;
  created_ts: number;
  status: JobStatusValue;
  current_stage: string;
  current_substep: string;
  started_ts: number | null;
  finished_ts: number | null;
  error: string | null;
}

export interface StatusResponse {
  job_id: string;
  status: JobStatusValue;
  current_stage: string;
  current_substep: string;
  started_ts: number | null;
  finished_ts: number | null;
  error: string | null;
}

export interface Entity {
  entity_id: string;
  name: string;
  type: string; // organisation | person
  roles: string[];
  responsibilities: string[];
  powers: string[];
  citations: Citation[];
}

export interface DocSummary {
  doc_id: string;
  doc_name: string;
  summary: string;
  citations: Citation[];
}

export interface MasterSummary {
  summary: string;
  citations: Citation[];
}

export interface StructuredItem {
  item_id: string;
  category: string; // deliverable | owner | budget | timeline | plan | compliance
  title: string;
  detail: string;
  attributes: Record<string, string>;
  citations: Citation[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string; // organisation | person | deliverable
  data: Record<string, unknown>;
}

export type Relation =
  | "engages"
  | "owns"
  | "responsible_for"
  | "depends_on"
  | "conflicts_with";

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: Relation | string;
  label: string;
  citations: Citation[];
}

export interface EntityGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface JudgeVerdict {
  score: number; // 0..1
  passed: boolean;
  note: string;
}

export type Severity = "high" | "medium" | "low";

export interface Finding {
  finding_id: string;
  type: string; // risk | conflict | gap | dependency | issue
  title: string;
  description: string;
  severity: Severity;
  mitigation: string;
  citations: Citation[];
  judge: JudgeVerdict | null;
  loop_count: number;
}

export interface DocumentRef {
  doc_id: string;
  doc_name: string;
  filename: string;
  s3_key: string;
}

export interface AnalysisResult {
  job_id: string;
  job: Job;
  artifacts: Record<string, boolean>;
  documents: DocumentRef[];
  master_summary: MasterSummary | null;
  doc_summaries: DocSummary[];
  entities: Entity[];
  entity_graph: EntityGraph;
  structured_items: StructuredItem[];
  findings: Finding[];
  chunk_count: number;
}

export interface SourceResponse {
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  page: number;
  bbox: Bbox | null;
  text: string;
  lines: { page: number; bbox: Bbox; text: string }[];
}

export interface ObsAgg {
  calls: number;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost_usd: number;
}

export interface Observability {
  job_id: string;
  totals: ObsAgg;
  by_step: Record<string, ObsAgg>;
  by_tier: Record<string, ObsAgg>;
  by_model: Record<string, ObsAgg>;
  logs: {
    call_id: string;
    job_id: string | null;
    step: string;
    model_id: string;
    tier: string;
    tokens_in: number;
    tokens_out: number;
    latency_ms: number;
    cost_usd: number;
    ts: number;
  }[];
}
