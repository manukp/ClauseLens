"""Configuration loader.

Single source of truth for runtime config: the repo-root ``config.env`` file
(see CLAUDE.md / D-config). Values may be overridden by real environment
variables (env wins), which keeps secrets out of source and lets the demo box
inject overrides without editing the file.

Nothing else in the codebase should hardcode the region, bucket, or model ids —
import ``settings`` from here.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# backend/app/config.py -> parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_config_env() -> Path | None:
    """Locate config.env: explicit override, repo root, or walk upward."""
    override = os.environ.get("CLAUSELENS_CONFIG_ENV")
    if override:
        return Path(override)
    candidate = REPO_ROOT / "config.env"
    if candidate.exists():
        return candidate
    # Fallback: walk up from cwd (useful when launched from odd directories).
    for parent in [Path.cwd(), *Path.cwd().parents]:
        c = parent / "config.env"
        if c.exists():
            return c
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes and inline trailing whitespace.
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


class Settings:
    """Resolved configuration. Real env vars take precedence over config.env."""

    def __init__(self) -> None:
        file_values: dict[str, str] = {}
        path = _find_config_env()
        if path is not None:
            file_values = _parse_env_file(path)
        self.config_env_path = str(path) if path else None

        def get(key: str, default: str = "") -> str:
            # Env override wins; empty string in file falls back to default.
            return os.environ.get(key) or file_values.get(key) or default

        self.aws_region: str = get("AWS_REGION", "us-east-1")
        self.aws_profile: str = get("AWS_PROFILE", "")
        self.s3_bucket: str = get("S3_BUCKET")
        self.chat_model_id: str = get("CHAT_MODEL_ID")
        self.reasoning_model_id: str = get("REASONING_MODEL_ID")
        self.embed_model_id: str = get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")

        # Local filesystem locations (D6: SQLite + local files only).
        self.data_dir: Path = Path(os.environ.get("CLAUSELENS_DATA_DIR", str(REPO_ROOT / "data")))
        self.db_path: Path = self.data_dir / "clauselens.db"

        # Where the built frontend lands (D7: one process serves the dist).
        self.frontend_dist: Path = Path(
            os.environ.get("CLAUSELENS_FRONTEND_DIST", str(REPO_ROOT / "frontend" / "dist"))
        )

    def as_safe_dict(self) -> dict[str, str | None]:
        """Non-secret view for health/diagnostics (never includes credentials)."""
        return {
            "aws_region": self.aws_region,
            "s3_bucket": self.s3_bucket,
            "chat_model_id": self.chat_model_id,
            "reasoning_model_id": self.reasoning_model_id,
            "embed_model_id": self.embed_model_id,
            "config_env_path": self.config_env_path,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenient module-level singleton.
settings = get_settings()
