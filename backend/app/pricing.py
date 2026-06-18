"""Per-model token pricing for observability cost accounting (D13).

Prices are USD per 1,000 tokens, split into input/output. Keyed by the exact
Bedrock model id used in config.env, with a couple of base-id aliases so the
lookup survives inference-profile prefixes (``us.`` / ``global.``).

VERIFIED against AWS Bedrock on-demand pricing (Phase 5, 2026-06-19), clearing
the Phase 1 Known-issue. Bedrock on-demand rates match Anthropic's first-party
per-1M prices: Claude Haiku 4.5 $1/$5 per 1M (= $0.001/$0.005 per 1K); Claude
Sonnet 4.6 $3/$15 per 1M (= $0.003/$0.015 per 1K). Titan Text Embeddings **V2**
is $0.02 per 1M input (= $0.00002 per 1K) — note this is the V2 rate, 5x cheaper
than the legacy V1/G1 ($0.0001/1K), which is a common point of confusion.
Re-check these against https://aws.amazon.com/bedrock/pricing/ if the demo
machine's region or model tier changes. Wrong prices only skew the Admin cost
Sankey; they do not affect analysis correctness.
"""
from __future__ import annotations

# USD per 1K tokens: (input, output). Embedding models have no output price.
PRICES: dict[str, dict[str, float]] = {
    # Claude Haiku 4.5 — high-volume / structural tier. $1/$5 per 1M (verified).
    "global.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
    # Claude Sonnet 4.6 — reasoning / judgement tier. $3/$15 per 1M (verified).
    "us.anthropic.claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    # Titan Text Embeddings V2 — input only. $0.02 per 1M (verified; V2, not V1).
    "amazon.titan-embed-text-v2:0": {"input": 0.00002, "output": 0.0},
}

# Base-id aliases (strip region/global inference-profile prefixes).
_ALIASES: dict[str, str] = {
    "anthropic.claude-haiku-4-5-20251001-v1:0": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
}


def _resolve(model_id: str) -> dict[str, float] | None:
    if model_id in PRICES:
        return PRICES[model_id]
    # Try alias table.
    if model_id in _ALIASES:
        return PRICES[_ALIASES[model_id]]
    # Try stripping a leading inference-profile region prefix (e.g. "us.", "global.").
    if "." in model_id:
        stripped = model_id.split(".", 1)[1]
        if stripped in _ALIASES:
            return PRICES[_ALIASES[stripped]]
        if stripped in PRICES:
            return PRICES[stripped]
    return None


def cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """Compute USD cost for a single model call. Unknown models cost 0.0."""
    price = _resolve(model_id)
    if price is None:
        return 0.0
    return round(
        (tokens_in / 1000.0) * price["input"] + (tokens_out / 1000.0) * price["output"],
        6,
    )
