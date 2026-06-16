"""Smoke test for the liveness endpoint (no AWS required)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_root_exposes_safe_config():
    resp = client.get("/api")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "ClauseLens"
    # Reasoning model key must be wired (Phase 1 config addition).
    assert "reasoning_model_id" in body["config"]
