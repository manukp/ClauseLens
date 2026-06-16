"""AWS clients (boto3 only — D2). Shared session, lazily constructed."""
from __future__ import annotations

import threading

import boto3

from ..config import settings

_lock = threading.Lock()
_session: boto3.session.Session | None = None


def get_session() -> boto3.session.Session:
    """Process-wide boto3 session honoring AWS_PROFILE / AWS_REGION from config."""
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                kwargs: dict[str, str] = {"region_name": settings.aws_region}
                if settings.aws_profile:
                    kwargs["profile_name"] = settings.aws_profile
                _session = boto3.session.Session(**kwargs)
    return _session
