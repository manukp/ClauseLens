import { useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

// New analysis: name + multi-file PDF upload (D17), then create -> upload -> run
// and route to the live progress view for the job (task 4).
type Phase = "idle" | "creating" | "uploading" | "starting";

export default function NewAnalysis() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const busy = phase !== "idle";

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const ok: File[] = [];
    const bad: string[] = [];
    Array.from(incoming).forEach((f) => {
      const isPdf =
        f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
      if (isPdf) ok.push(f);
      else bad.push(f.name);
    });
    setRejected(bad);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size));
      return [...prev, ...ok.filter((f) => !seen.has(f.name + f.size))];
    });
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!busy) addFiles(e.dataTransfer.files);
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function submit() {
    setError(null);
    if (!name.trim()) {
      setError("Give the analysis a name.");
      return;
    }
    if (files.length === 0) {
      setError("Add at least one contract PDF.");
      return;
    }
    try {
      setPhase("creating");
      const job = await api.createAnalysis(name.trim());
      setPhase("uploading");
      await api.uploadFiles(job.job_id, files);
      setPhase("starting");
      await api.run(job.job_id);
      navigate(`/analysis/${job.job_id}`);
    } catch (e) {
      setError((e as Error).message);
      setPhase("idle");
    }
  }

  return (
    <section className="max-w-3xl">
      <h2 className="text-2xl font-semibold text-ink">New analysis</h2>
      <p className="mt-1 text-sm text-slate">
        Upload one or more contract PDFs to surface risks, gaps, conflicts,
        deliverables, owners and dependencies — each traceable to its source clause.
      </p>

      <div className="card mt-6 space-y-5 p-6">
        <div>
          <label htmlFor="analysis-name" className="text-sm font-medium text-ink">
            Analysis name
          </label>
          <input
            id="analysis-name"
            type="text"
            value={name}
            disabled={busy}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme ⇄ BuildrCo — MSA + SOW"
            className="mt-1.5 w-full rounded-md border border-ink/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-marigold focus:ring-2 focus:ring-marigold/30 disabled:opacity-60"
          />
        </div>

        <div>
          <span className="text-sm font-medium text-ink">Contract PDFs</span>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !busy && inputRef.current?.click()}
            className={[
              "mt-1.5 flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed py-10 text-center transition-colors",
              dragging ? "border-marigold bg-marigold/5" : "border-ink/20 hover:border-ink/35",
              busy ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-marigold/10 text-marigold">
              ↑
            </div>
            <p className="mt-2 text-sm font-medium text-ink">
              Drop PDFs here, or click to choose
            </p>
            <p className="mt-0.5 text-xs text-slate">PDF files only</p>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              onChange={(e) => addFiles(e.target.files)}
            />
          </div>

          {rejected.length > 0 && (
            <p className="mt-2 text-xs text-severity-high">
              Skipped {rejected.length} non-PDF file{rejected.length > 1 ? "s" : ""}:{" "}
              {rejected.join(", ")}. Only PDFs are accepted.
            </p>
          )}

          {files.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {files.map((f, i) => (
                <li
                  key={f.name + f.size}
                  className="flex items-center justify-between rounded-md border border-ink/10 bg-white/60 px-3 py-2 text-sm"
                >
                  <span className="truncate text-ink">
                    <span className="mr-2 text-marigold">§</span>
                    {f.name}
                  </span>
                  <span className="flex items-center gap-3 text-xs text-slate">
                    {(f.size / 1024).toFixed(0)} KB
                    {!busy && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeFile(i);
                        }}
                        className="rounded px-1 text-slate hover:text-severity-high"
                        aria-label={`Remove ${f.name}`}
                      >
                        ✕
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <div className="rounded-md border border-severity-high/30 bg-severity-high/5 px-3 py-2 text-sm text-severity-high">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-md bg-marigold px-4 py-2 text-sm font-semibold text-white shadow-card transition-colors hover:bg-marigold/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {phaseLabel(phase)}
          </button>
          {busy && (
            <span className="text-xs text-slate">This kicks off the analysis, then opens its progress view.</span>
          )}
        </div>
      </div>
    </section>
  );
}

function phaseLabel(phase: Phase): string {
  switch (phase) {
    case "creating":
      return "Creating analysis…";
    case "uploading":
      return "Uploading PDFs…";
    case "starting":
      return "Starting analysis…";
    default:
      return "Start analysis";
  }
}
