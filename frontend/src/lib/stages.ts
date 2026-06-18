import type { StatusResponse } from "./types";

// Canonical pipeline progression for the live-progress narration device (task 3).
// The backend reports a free-text current_substep per node; we map it to an index
// in this ordered list so the UI can animate the advance. Keep in step with
// backend/app/graph/pipeline.py substep strings.
export const STAGES: { label: string; stage: "Stage 1 · ingest" | "Stage 2 · analysis" }[] = [
  { label: "Parsing PDFs", stage: "Stage 1 · ingest" },
  { label: "Clause-aware chunking", stage: "Stage 1 · ingest" },
  { label: "Embedding clauses → FAISS", stage: "Stage 1 · ingest" },
  { label: "Extracting entities", stage: "Stage 1 · ingest" },
  { label: "Summarising documents", stage: "Stage 1 · ingest" },
  { label: "Composing master summary", stage: "Stage 1 · ingest" },
  { label: "Extracting structured items", stage: "Stage 2 · analysis" },
  { label: "Building entity graph", stage: "Stage 2 · analysis" },
  { label: "Detecting risks & conflicts", stage: "Stage 2 · analysis" },
  { label: "LLM-as-judge review", stage: "Stage 2 · analysis" },
];

const DONE = STAGES.length; // all stages complete

// Returns the index of the currently-active stage (0..STAGES.length-1), or DONE
// when the run is complete, or -1 when queued / not yet started.
export function stageIndex(status: StatusResponse): number {
  if (status.status === "complete") return DONE;
  if (status.status === "queued") return -1;
  const s = (status.current_substep || "").toLowerCase();
  if (!s || s === "queued") return -1;
  if (s.includes("done")) return DONE;
  if (s.includes("judg")) return 9;
  if (s.includes("detect")) return 8;
  if (s.includes("graph") || s.includes("relationship")) return 7;
  if (s.includes("structured")) return 6;
  if (s.includes("master")) return 5;
  if (s.includes("summar")) return 4;
  if (s.includes("entit")) return 3;
  if (s.includes("embed") || s.includes("faiss")) return 2;
  if (s.includes("chunk")) return 1;
  if (s.includes("pars")) return 0;
  return -1;
}

export const STAGE_DONE = DONE;
