"""Live Phase-4 follow-up verification: run the full pipeline on the THREE-document
hero contract (MSA + SOW + Change Order) against real Bedrock, and report whether it
completes plus per-step timing — especially build_graph, which previously hit the
botocore read timeout on the multi-document set. Run from backend/:

    PYTHONPATH=. .venv/Scripts/python.exe scripts/verify_phase4_multidoc.py
"""
from __future__ import annotations

import time
from pathlib import Path

from app.graph import run_pipeline
from app.models.schemas import Job, JobStatus
from app.routes import analyses
from app.store import artifacts, get_job_store

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sample_contracts"
DOCS = [
    "01_master_services_agreement.pdf",
    "02_statement_of_work.pdf",
    "03_change_order.pdf",
]


def main() -> int:
    store = get_job_store()
    job = store.create(Job(name="Acme ⇄ BuildrCo — MSA + SOW + Change Order", status=JobStatus.queued))
    jid = job.job_id
    for i, name in enumerate(DOCS):
        src = SAMPLES / name
        (artifacts.uploads_dir(jid) / name).write_bytes(src.read_bytes())
        artifacts.add_document(jid, {
            "doc_id": f"doc_{i}", "doc_name": src.stem, "filename": name, "s3_key": f"jobs/{jid}/{name}",
        })

    print(f"Running 3-document pipeline for job {jid} ...")
    t0 = time.perf_counter()
    run_pipeline(jid)
    wall = time.perf_counter() - t0

    j = store.get(jid)
    print(f"\nStatus: {j.status}  | wall-clock: {wall:.1f}s")
    step_errors = artifacts.read_json(jid, artifacts.STEP_ERRORS, default=[])
    print(f"Step errors: {step_errors if step_errors else 'none'}")

    eg = artifacts.read_json(jid, artifacts.ENTITY_GRAPH, default={})
    items = artifacts.read_json(jid, artifacts.STRUCTURED, default=[])
    findings = artifacts.read_json(jid, artifacts.FINDINGS, default=[])
    ents = artifacts.read_json(jid, artifacts.ENTITIES, default=[])
    chunks = artifacts.read_json(jid, artifacts.CHUNKS, default=[])
    print(
        f"Artifacts: chunks={len(chunks)} entities={len(ents)} items={len(items)} "
        f"graph={len(eg.get('nodes', []))}n/{len(eg.get('edges', []))}e findings={len(findings)}"
    )

    obs = analyses.get_observability(jid)
    t = obs["totals"]
    print(f"\nObservability: calls={t['calls']} cost=${t['cost_usd']:.4f} total_latency={t['latency_ms']}ms")
    print("Per-step latency (ms) / calls / cost:")
    for step, s in sorted(obs["by_step"].items(), key=lambda kv: -kv[1]["latency_ms"]):
        flag = "  <-- build_graph (the prior timeout)" if step == "build_graph" else ""
        print(f"  {step:24s} {s['latency_ms']:7d}ms  calls={s['calls']:3d}  ${s['cost_usd']:.4f}{flag}")

    bg = obs["by_step"].get("build_graph")
    if bg:
        print(f"\nbuild_graph actual duration: {bg['latency_ms']}ms over {bg['calls']} call(s) "
              f"(read_timeout is 180000ms)")

    print("\nResult:", "COMPLETE" if j.status == JobStatus.complete else j.status.value.upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
