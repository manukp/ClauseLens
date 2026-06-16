"""Health endpoints.

- ``GET /api/health``      — process liveness (no AWS calls).
- ``GET /api/health/aws``  — proves end-to-end connectivity from inside the app:
  a 1-token Converse on the chat model, a tiny Titan embed, and an S3 list. Each
  check reports pass/fail independently; the route never raises.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..aws import bedrock, s3
from ..config import settings

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health() -> dict:
    """Liveness: the process is up and serving."""
    return {"status": "ok"}


def _check(fn) -> dict:
    """Run a probe, capturing pass/fail + a short detail without raising."""
    try:
        return {"ok": True, "detail": fn()}
    except Exception as exc:  # noqa: BLE001 — health must never raise.
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


@router.get("/aws")
def health_aws() -> dict:
    """End-to-end AWS connectivity probe against the real account."""

    def bedrock_check() -> str:
        result = bedrock.converse(
            model_id=settings.chat_model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with exactly: OK"}]}],
            max_tokens=5,
            step="health.bedrock",
        )
        return (
            f"model={result.log.model_id} reply={result.text.strip()!r} "
            f"tokens_in={result.log.tokens_in} tokens_out={result.log.tokens_out} "
            f"latency_ms={result.log.latency_ms} cost_usd={result.log.cost_usd}"
        )

    def embed_check() -> str:
        result = bedrock.embed(["connectivity check"], step="health.embed")
        dim = len(result.vectors[0]) if result.vectors else 0
        return f"model={settings.embed_model_id} dim={dim}"

    def s3_check() -> str:
        count = s3.head_ok(max_keys=1)
        return f"bucket={settings.s3_bucket} list_ok keys_sampled={count}"

    checks = {
        "bedrock": _check(bedrock_check),
        "embeddings": _check(embed_check),
        "s3": _check(s3_check),
    }
    all_ok = all(c["ok"] for c in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
