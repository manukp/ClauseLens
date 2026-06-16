"""SQLite-backed job store (D6).

Zero-infra, survives restarts, no AWS dependency. The DB file is created lazily
under ``data/``. One table: ``jobs``, mirroring the Job schema.
"""
from __future__ import annotations

import sqlite3
import threading
from functools import lru_cache

from ..config import settings
from ..models.schemas import Job, JobStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    created_ts      REAL NOT NULL,
    status          TEXT NOT NULL,
    current_stage   TEXT NOT NULL DEFAULT '',
    current_substep TEXT NOT NULL DEFAULT '',
    started_ts      REAL,
    finished_ts     REAL,
    error           TEXT
);
"""

_COLUMNS = [
    "job_id",
    "name",
    "created_ts",
    "status",
    "current_stage",
    "current_substep",
    "started_ts",
    "finished_ts",
    "error",
]


class JobStore:
    """Thread-safe CRUD over the jobs table. Connections are short-lived."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        # Ensure parent dir exists (data/ is created lazily).
        from pathlib import Path

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"],
            name=row["name"],
            created_ts=row["created_ts"],
            status=JobStatus(row["status"]),
            current_stage=row["current_stage"] or "",
            current_substep=row["current_substep"] or "",
            started_ts=row["started_ts"],
            finished_ts=row["finished_ts"],
            error=row["error"],
        )

    def create(self, job: Job) -> Job:
        with self._lock, self._connect() as conn:
            conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * len(_COLUMNS))})",
                (
                    job.job_id,
                    job.name,
                    job.created_ts,
                    job.status.value,
                    job.current_stage,
                    job.current_substep,
                    job.started_ts,
                    job.finished_ts,
                    job.error,
                ),
            )
        return job

    def get(self, job_id: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, limit: int = 100) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update(self, job_id: str, **fields) -> Job | None:
        """Update mutable fields on a job. ``status`` accepts str or JobStatus."""
        if not fields:
            return self.get(job_id)
        allowed = {
            "name",
            "status",
            "current_stage",
            "current_substep",
            "started_ts",
            "finished_ts",
            "error",
        }
        sets = {}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Cannot update unknown/immutable field: {key}")
            if key == "status" and isinstance(value, JobStatus):
                value = value.value
            sets[key] = value
        assignments = ", ".join(f"{k} = ?" for k in sets)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                (*sets.values(), job_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get(job_id)


@lru_cache(maxsize=1)
def get_job_store() -> JobStore:
    return JobStore(str(settings.db_path))
