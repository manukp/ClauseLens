"""Bedrock Runtime wrappers — boto3 Converse + Titan embeddings (D2).

Every Converse call returns the model text AND a fully-populated ModelCallLog
(D13). LangGraph nodes call these directly; nothing routes through langchain-aws.

Note (D3): citations and structured/tool output are mutually exclusive on
Bedrock — that two-pass split is enforced by callers in later phases, not here.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from ..config import settings
from ..models.schemas import ModelCallLog
from ..pricing import cost_usd
from . import get_session

# Titan Text Embeddings v2 — configured output dimensionality (matches D5/FAISS).
EMBED_DIM = 1024


def infer_tier(model_id: str) -> str:
    """Map a model id to its observability tier label."""
    mid = model_id.lower()
    if "haiku" in mid:
        return "haiku"
    if "sonnet" in mid:
        return "sonnet"
    if "titan" in mid or "embed" in mid:
        return "titan"
    return "unknown"


@dataclass
class ConverseResult:
    """Text output plus the mandatory observability record."""

    text: str
    log: ModelCallLog


def _runtime():
    return get_session().client("bedrock-runtime")


def converse(
    model_id: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
    *,
    job_id: str | None = None,
    step: str = "converse",
) -> ConverseResult:
    """Call the Bedrock Converse API and record a ModelCallLog.

    ``messages`` follow the Converse shape:
        [{"role": "user", "content": [{"text": "..."}]}]
    ``system`` is an optional system prompt string.
    """
    client = _runtime()
    kwargs: dict = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]

    start = time.perf_counter()
    resp = client.converse(**kwargs)
    latency_ms = int((time.perf_counter() - start) * 1000)

    # Extract concatenated text from the assistant message.
    parts = resp.get("output", {}).get("message", {}).get("content", [])
    text = "".join(p.get("text", "") for p in parts)

    usage = resp.get("usage", {})
    tokens_in = int(usage.get("inputTokens", 0))
    tokens_out = int(usage.get("outputTokens", 0))

    log = ModelCallLog(
        job_id=job_id,
        step=step,
        model_id=model_id,
        tier=infer_tier(model_id),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=cost_usd(model_id, tokens_in, tokens_out),
    )
    return ConverseResult(text=text, log=log)


@dataclass
class EmbedResult:
    """Embedding vectors plus per-text observability logs."""

    vectors: list[list[float]]
    logs: list[ModelCallLog] = field(default_factory=list)


def embed(
    texts: list[str],
    *,
    model_id: str | None = None,
    job_id: str | None = None,
    step: str = "embed",
) -> EmbedResult:
    """Embed texts with Titan v2, returning 1024-dim vectors + ModelCallLogs.

    Titan embeds one input per InvokeModel call, so we loop. Each call records
    its own log (token usage from ``inputTextTokenCount``).
    """
    mid = model_id or settings.embed_model_id
    client = _runtime()
    vectors: list[list[float]] = []
    logs: list[ModelCallLog] = []

    for text in texts:
        body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True})
        start = time.perf_counter()
        resp = client.invoke_model(
            modelId=mid,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        payload = json.loads(resp["body"].read())
        vectors.append(payload.get("embedding", []))
        tokens_in = int(payload.get("inputTextTokenCount", 0))
        logs.append(
            ModelCallLog(
                job_id=job_id,
                step=step,
                model_id=mid,
                tier=infer_tier(mid),
                tokens_in=tokens_in,
                tokens_out=0,
                latency_ms=latency_ms,
                cost_usd=cost_usd(mid, tokens_in, 0),
            )
        )

    return EmbedResult(vectors=vectors, logs=logs)
