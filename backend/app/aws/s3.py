"""S3 helpers — uploads live under a ``jobs/{job_id}/`` prefix in the configured
bucket. boto3 only; bucket name comes from config (never hardcoded)."""
from __future__ import annotations

from ..config import settings
from . import get_session


def _client():
    return get_session().client("s3")


def _job_key(job_id: str, filename: str) -> str:
    return f"jobs/{job_id}/{filename}"


def upload_bytes(job_id: str, filename: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes under jobs/{job_id}/{filename}. Returns the object key."""
    key = _job_key(job_id, filename)
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def upload_file(job_id: str, filepath: str, filename: str | None = None) -> str:
    """Upload a local file under jobs/{job_id}/. Returns the object key."""
    import os

    name = filename or os.path.basename(filepath)
    key = _job_key(job_id, name)
    _client().upload_file(filepath, settings.s3_bucket, key)
    return key


def list_objects(prefix: str = "") -> list[str]:
    """List object keys in the bucket under an optional prefix."""
    paginator = _client().get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def list_job_objects(job_id: str) -> list[str]:
    return list_objects(prefix=f"jobs/{job_id}/")


def fetch_bytes(key: str) -> bytes:
    """Fetch an object's bytes by key."""
    resp = _client().get_object(Bucket=settings.s3_bucket, Key=key)
    return resp["Body"].read()


def head_ok(max_keys: int = 1) -> int:
    """Cheap connectivity probe: list up to ``max_keys`` keys, return the count.

    Raises on access/credential failure (caller treats an exception as fail).
    """
    resp = _client().list_objects_v2(Bucket=settings.s3_bucket, MaxKeys=max_keys)
    return resp.get("KeyCount", 0)
