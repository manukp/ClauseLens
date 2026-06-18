"""Throwaway live driver: run the 3-document software_dev hero set end-to-end.

Stages the three PDFs into a fresh job and invokes the real pipeline against live
Bedrock (parsing reads local bytes, so no S3 needed). Prints overall status, any
isolated step errors, the findings count, and the detect_findings / build_graph
call durations + token usage — the two steps under scrutiny in the timeout/
truncation fix.

Run from repo root:  backend\.venv\Scripts\python.exe scripts\run_hero_live.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SET_DIR = ROOT / "data" / "sample_contracts" / "software_dev"
DOCS = [
    ("01_master_services_agreement.pdf", "Master Services Agreement"),
    ("02_statement_of_work.pdf", "Statement of Work"),
    ("03_change_order.pdf", "Change Order"),
]


def main() -> int:
    from app.graph import run_pipeline
    from app.models.schemas import Job, JobStatus
    from app.store import artifacts, get_job_store

    store = get_job_store()
    job = store.create(Job(name="Hero 3-doc live", status=JobStatus.queued))
    job_id = job.job_id
    print(f"job_id = {job_id}")

    for i, (filename, doc_name) in enumerate(DOCS):
        (artifacts.uploads_dir(job_id) / filename).write_bytes((SET_DIR / filename).read_bytes())
        artifacts.add_document(
            job_id,
            {"doc_id": f"doc_{i}", "doc_name": doc_name, "filename": filename, "s3_key": f"local/{filename}"},
        )

    t0 = time.perf_counter()
    run_pipeline(job_id)
    wall = time.perf_counter() - t0

    final = store.get(job_id)
    step_errors = artifacts.read_json(job_id, artifacts.STEP_ERRORS, default=[])
    findings = artifacts.read_json(job_id, artifacts.FINDINGS, default=[])
    eg = artifacts.read_json(job_id, artifacts.ENTITY_GRAPH, default={"nodes": [], "edges": []})
    logs = artifacts.read_json(job_id, artifacts.MODEL_LOGS, default=[])

    print(f"\n=== RESULT ({wall:.1f}s wall) ===")
    print(f"status        : {final.status.value}")
    print(f"step_errors   : {[e['step'] for e in step_errors] or 'none'}")
    print(f"findings      : {len(findings)}")
    print(f"graph         : {len(eg.get('nodes', []))} nodes / {len(eg.get('edges', []))} edges")
    print(f"model calls   : {len(logs)}")

    for step in ("detect_findings", "build_graph"):
        for lg in logs:
            if lg.get("step") == step:
                print(
                    f"  {step:16s} latency={lg['latency_ms']}ms "
                    f"tokens_in={lg['tokens_in']} tokens_out={lg['tokens_out']}"
                )

    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    print(f"findings by severity: {by_sev}")
    for f in findings[:30]:
        v = f.get("judge") or {}
        print(f"  [{f['severity']:6s}] {f['type']:10s} {f['title'][:70]}  judge={v.get('score')}")

    return 0 if final.status.value in ("complete", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
