"""Unit tests for the best-effort LLM JSON parser (`app.ingest.llm_json`).

The critical case is a model hitting its `max_tokens` cap mid-array: the whole
string fails `json.loads`, and without salvage it would collapse to the empty
default — silently dropping EVERY finding and demoing zero results. `_salvage_array`
must recover the complete leading elements instead.
"""
from __future__ import annotations

import json

from app.ingest.llm_json import parse_json


def test_parses_clean_array():
    assert parse_json('[{"a": 1}, {"b": 2}]', default=[]) == [{"a": 1}, {"b": 2}]


def test_parses_fenced_json():
    text = "Here you go:\n```json\n[{\"a\": 1}]\n```"
    assert parse_json(text, default=[]) == [{"a": 1}]


def test_salvages_truncated_array():
    """Three complete objects + a fourth cut off at the token cap → keep the three."""
    good = [{"type": "gap", "title": f"Finding {i}", "severity": "high"} for i in range(3)]
    full = json.dumps(good)
    # Drop the closing ']' and append a half-written 4th element, as a cap would.
    truncated = full[:-1] + ', {"type": "conflict", "title": "Incomp'
    result = parse_json(truncated, default=[])
    assert result == good, "must recover the complete leading elements"


def test_truncated_with_no_complete_element_falls_back_to_default():
    truncated = '[{"type": "gap", "title": "Incompl'
    assert parse_json(truncated, default=[]) == []


def test_empty_text_returns_default():
    assert parse_json("", default=[]) == []
    assert parse_json("no json here at all", default=[]) == []
