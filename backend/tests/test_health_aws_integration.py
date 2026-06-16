"""Integration test: live S3 + Bedrock connectivity from inside the app.

Skipped automatically when AWS is unreachable (no credentials / offline), so
``make test`` stays green on a machine without the demo account. Set
CLAUSELENS_RUN_AWS_TESTS=1 to force a hard failure instead of a skip.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _aws_available() -> bool:
    try:
        import boto3

        boto3.session.Session().get_credentials()  # type: ignore[union-attr]
        return boto3.session.Session().get_credentials() is not None
    except Exception:
        return False


force = os.environ.get("CLAUSELENS_RUN_AWS_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not force and not _aws_available(),
    reason="No AWS credentials available; set CLAUSELENS_RUN_AWS_TESTS=1 to require.",
)


def test_health_aws_all_checks_pass():
    resp = client.get("/api/health/aws")
    assert resp.status_code == 200
    body = resp.json()
    checks = body["checks"]
    for name in ("bedrock", "embeddings", "s3"):
        assert name in checks, f"missing check: {name}"
        assert checks[name]["ok"], f"{name} failed: {checks[name]['detail']}"
    assert body["status"] == "ok"
