"""Robust JSON extraction from model text.

Because citations are attached deterministically (D18), extraction calls ask the
model for plain structured JSON (no Bedrock tool/citation mode), so we must parse
JSON out of a text response defensively — models sometimes wrap it in prose or a
``` fence. This never raises: on failure it returns the supplied default.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


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
    return default
