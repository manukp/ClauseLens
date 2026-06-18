"""Robust JSON extraction from model text.

Because citations are attached deterministically (D18), extraction calls ask the
model for plain structured JSON (no Bedrock tool/citation mode), so we must parse
JSON out of a text response defensively — models sometimes wrap it in prose or a
``` fence. This never raises: on failure it returns the supplied default.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _salvage_array(text: str) -> list | None:
    """Recover the complete leading elements of a TRUNCATED JSON array.

    When a model hits its ``max_tokens`` cap mid-array the trailing element is cut
    off and ``json.loads`` fails on the whole string — which would otherwise parse
    to the empty default and silently drop EVERY item (e.g. zero findings, a broken
    demo). We instead decode element-by-element from the first ``[`` and keep every
    object that parsed fully before the truncation point. Returns None if nothing
    parsed (so callers fall through to their default).
    """
    start = text.find("[")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    items: list = []
    i = start + 1
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except (json.JSONDecodeError, ValueError):
            break  # truncated / malformed element — stop, keep what we have
        items.append(obj)
        i = end
    return items or None


def parse_json(text: str, default: Any) -> Any:
    """Best-effort parse of a JSON value from ``text``; ``default`` on failure."""
    if not text:
        return default
    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text.strip())
    # Last resort: slice from the first bracket to its matching last bracket.
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = text.find(opener), text.rfind(closer)
        if 0 <= start < end:
            candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    # Nothing parsed cleanly. If this looks like a truncated array (model hit its
    # token cap mid-output), salvage the complete leading elements rather than
    # collapsing to the default — a partial list beats silently losing everything.
    salvaged = _salvage_array(text)
    if salvaged is not None:
        logger.warning(
            "parse_json: recovered %d element(s) from a truncated/invalid JSON array",
            len(salvaged),
        )
        return salvaged
    return default
