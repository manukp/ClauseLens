// Thin typed client over the FastAPI result surface. Same-origin: the API and
// the built SPA are served by one process (D7), so relative /api paths work in
// dev (Vite proxy) and in the demo build alike.
import type {
  AnalysisResult,
  Job,
  Observability,
  SourceResponse,
  StatusResponse,
} from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listAnalyses: () => getJSON<Job[]>("/api/analyses"),

  getStatus: (jobId: string) =>
    getJSON<StatusResponse>(`/api/analyses/${jobId}/status`),

  getResult: (jobId: string) =>
    getJSON<AnalysisResult>(`/api/analyses/${jobId}`),

  getSource: (jobId: string, chunkId: string) =>
    getJSON<SourceResponse>(`/api/analyses/${jobId}/source/${chunkId}`),

  getObservability: (jobId: string) =>
    getJSON<Observability>(`/api/analyses/${jobId}/observability`),

  documentUrl: (jobId: string, docId: string) =>
    `/api/analyses/${jobId}/document/${docId}`,

  async createAnalysis(name: string): Promise<Job> {
    const res = await fetch("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error((await safeDetail(res)) || "Could not create analysis");
    return res.json();
  },

  async uploadFiles(jobId: string, files: File[]): Promise<void> {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`/api/analyses/${jobId}/files`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error((await safeDetail(res)) || "Upload failed");
  },

  async run(jobId: string): Promise<Job> {
    const res = await fetch(`/api/analyses/${jobId}/run`, { method: "POST" });
    if (!res.ok) throw new Error((await safeDetail(res)) || "Could not start analysis");
    return res.json();
  },
};

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json();
    return body?.detail ?? null;
  } catch {
    return null;
  }
}
