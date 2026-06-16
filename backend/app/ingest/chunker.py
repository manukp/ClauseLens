"""Clause-aware chunking (Phase 2, task 3).

Group a parsed transcript's lines into clause/section chunks using font-size and
layout heuristics to detect headings, plus a clause-number pattern. A chunk may
span less than, exactly, or more than a page. Each chunk records its page range,
a bbox per page touched (union of the lines on that page), the detected heading,
and text — the provenance a Citation is stamped from deterministically (D18).
"""
from __future__ import annotations

import re
import statistics

from ..models.schemas import Chunk

# Soft cap so a very long section still yields retrievable, embeddable chunks.
MAX_CHARS = 1500

# Clause/section markers commonly opening a contract provision.
_CLAUSE_RE = re.compile(
    r"^\s*("
    r"(\d+(\.\d+)*\.?)\s+\S"          # 1.  /  1.2  /  3.4.1
    r"|ARTICLE\s+[IVXLC0-9]+"          # ARTICLE IV
    r"|SECTION\s+\d+"                  # SECTION 7
    r"|SCHEDULE\s+[A-Z0-9]+"           # SCHEDULE B
    r"|EXHIBIT\s+[A-Z0-9]+"           # EXHIBIT A
    r"|APPENDIX\s+[A-Z0-9]+"
    r"|WHEREAS\b"
    r"|NOW,?\s+THEREFORE\b"
    r")",
    re.IGNORECASE,
)


def _body_size(lines: list[dict]) -> float:
    """Median line font size = the document's body text size baseline."""
    sizes = [ln["size"] for ln in lines if ln.get("size")]
    return statistics.median(sizes) if sizes else 0.0


def _is_heading(line: dict, body_size: float) -> bool:
    """Heading heuristic: larger-than-body, or bold-and-short, or clause marker."""
    text = line["text"].strip()
    if not text:
        return False
    size = line.get("size", 0.0)
    if body_size and size >= body_size * 1.15:
        return True
    if _CLAUSE_RE.match(text):
        return True
    # Bold, short, and not sentence-like punctuation-heavy → a heading line.
    if line.get("bold") and len(text) <= 80 and not text.endswith((".", ";", ",")):
        return True
    return False


def _flush(buf_lines: list[dict], doc_id: str, doc_name: str, heading: str | None) -> Chunk | None:
    """Build a Chunk from accumulated lines (with per-page bbox unions)."""
    if not buf_lines:
        return None
    pages_order: list[int] = []
    boxes: dict[int, list[float]] = {}
    for ln in buf_lines:
        p = ln["page"]
        if p not in boxes:
            boxes[p] = list(ln["bbox"])
            pages_order.append(p)
        else:
            b, nb = boxes[p], ln["bbox"]
            boxes[p] = [min(b[0], nb[0]), min(b[1], nb[1]), max(b[2], nb[2]), max(b[3], nb[3])]
    text = "\n".join(ln["text"] for ln in buf_lines).strip()
    if not text:
        return None
    return Chunk(
        doc_id=doc_id,
        doc_name=doc_name,
        page_start=pages_order[0],
        page_end=pages_order[-1],
        pages=pages_order,
        bboxes=[[round(v, 2) for v in boxes[p]] for p in pages_order],
        heading=heading,
        text=text,
    )


def chunk_transcript(transcript: dict) -> list[Chunk]:
    """Turn one parsed transcript into an ordered list of clause-aware chunks."""
    doc_id = transcript["doc_id"]
    doc_name = transcript["doc_name"]

    # Flatten lines across pages in reading order, tagging each with its page.
    flat: list[dict] = []
    for page in transcript.get("pages", []):
        for ln in page.get("lines", []):
            flat.append({**ln, "page": page["page"]})
    if not flat:
        return []

    body_size = _body_size(flat)
    chunks: list[Chunk] = []
    buf: list[dict] = []
    heading: str | None = None
    buf_chars = 0

    for ln in flat:
        starts_section = _is_heading(ln, body_size)
        # Break before a new heading, or when the soft size cap is exceeded.
        if buf and (starts_section or buf_chars >= MAX_CHARS):
            c = _flush(buf, doc_id, doc_name, heading)
            if c:
                chunks.append(c)
            buf, buf_chars = [], 0
            if starts_section:
                heading = ln["text"].strip()
        elif starts_section and not buf:
            heading = ln["text"].strip()
        buf.append(ln)
        buf_chars += len(ln["text"]) + 1

    tail = _flush(buf, doc_id, doc_name, heading)
    if tail:
        chunks.append(tail)
    return chunks
