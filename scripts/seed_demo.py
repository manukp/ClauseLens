"""Seed the pre-baked demo analysis into the local job store (Phase 5, task 4).

The committed seed under ``data/seed/`` holds one finished software-development
analysis (the 3-document hero set) — every artifact already computed and cited.
This script copies it into the runtime job store (``data/jobs/<id>/``) and
registers the job row in SQLite, so a cold clone can open a completed, fully
cited analysis instantly without a live Bedrock run (live-demo insurance).

It is idempotent: re-running refreshes the artifacts and the job row in place.
``make demo`` runs it automatically; you can also run it by hand:

    backend/.venv/Scripts/python scripts/seed_demo.py     # Windows
    backend/.venv/bin/python    scripts/seed_demo.py       # POSIX

To RE-BAKE from scratch (e.g. after changing the pipeline) run a live analysis
of data/sample_contracts/software_dev/ (see scripts/run_hero_live.py), then copy
the resulting data/jobs/<id>/ over data/seed/prebaked/ and update
data/seed/manifest.json with the new job_id/name.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SEED_DIR = ROOT / "data" / "seed"
PREBAKED = SEED_DIR / "prebaked"
MANIFEST = SEED_DIR / "manifest.json"


def main() -> int:
    if not MANIFEST.exists() or not PREBAKED.is_dir():
        print(f"No seed found at {SEED_DIR} — nothing to seed (skipping).")
        return 0

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    job_id = manifest["job_id"]
    name = manifest.get("name", "Pre-baked analysis (sample)")
    status = manifest.get("status", "complete")

    # Import after sys.path is set; settings reads data_dir without needing AWS.
    from app.store import artifacts
    from app.store import get_job_store
    from app.models.schemas import Job, JobStatus

    # 1) Copy artifacts into the runtime job dir (refresh in place if present).
    dest = artifacts.jobs_root() / job_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(PREBAKED, dest)

    # 2) Register / refresh the job row in SQLite.
    store = get_job_store()
    js = JobStatus(status)
    existing = store.get(job_id)
    if existing is None:
        store.create(
            Job(
                job_id=job_id,
                name=name,
                status=js,
                current_stage="stage-2 analysis",
                current_substep="done",
            )
        )
    else:
        store.update(
            job_id,
            name=name,
            status=js,
            current_stage="stage-2 analysis",
            current_substep="done",
            error=None,
        )

    n_findings = len(artifacts.read_json(job_id, artifacts.FINDINGS, default=[]) or [])
    n_docs = len(artifacts.list_documents(job_id))
    print(
        f"Seeded pre-baked analysis {job_id!r} "
        f"({name!r}: {n_docs} docs, {n_findings} findings) -> {dest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
