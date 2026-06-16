"""Local persistence (D6: SQLite + local files only)."""
from .jobs import JobStore, get_job_store

__all__ = ["JobStore", "get_job_store"]
