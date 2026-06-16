"""Embeddings + FAISS index (D5, Phase 2 task 4).

Embed each chunk with Titan v2 (1024-dim, normalized) via the boto3 wrapper (D2),
build a per-job FAISS index, and persist it next to the chunk metadata under
``data/jobs/{id}/``. Vectors are L2-normalized, so an inner-product index gives
cosine similarity. ``search`` powers later retrieval (Phase 3's RAG loop).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np

from ..aws import bedrock
from ..aws.bedrock import EMBED_DIM
from ..models.schemas import Chunk, ModelCallLog

INDEX_FILENAME = "faiss.index"


@dataclass
class IndexResult:
    """A built FAISS index plus the embedding ModelCallLogs (D13)."""

    index: faiss.Index
    logs: list[ModelCallLog] = field(default_factory=list)


def _to_matrix(vectors: list[list[float]]) -> np.ndarray:
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr


def build_index(chunks: list[Chunk], *, job_id: str | None = None) -> IndexResult:
    """Embed chunk texts and build an inner-product FAISS index over them."""
    index = faiss.IndexFlatIP(EMBED_DIM)
    if not chunks:
        return IndexResult(index=index, logs=[])
    embed = bedrock.embed([c.text for c in chunks], job_id=job_id, step="embed.chunks")
    index.add(_to_matrix(embed.vectors))
    return IndexResult(index=index, logs=embed.logs)


def save_index(index: faiss.Index, job_dir: Path) -> Path:
    """Persist the FAISS index under the job directory; return its path."""
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / INDEX_FILENAME
    faiss.write_index(index, str(path))
    return path


def load_index(job_dir: Path) -> faiss.Index:
    return faiss.read_index(str(job_dir / INDEX_FILENAME))


def search(
    job_dir: Path,
    chunk_meta: list[dict],
    query: str,
    k: int = 5,
    *,
    job_id: str | None = None,
) -> tuple[list[dict], list[ModelCallLog]]:
    """Embed ``query`` and return the top-k chunk metadata dicts with scores.

    ``chunk_meta`` is the persisted, row-aligned chunk list. Returns the hits and
    the query-embedding logs so callers honor D13. (Used by Phase 3 retrieval.)
    """
    index = load_index(job_dir)
    embed = bedrock.embed([query], job_id=job_id, step="embed.query")
    if not chunk_meta or index.ntotal == 0:
        return [], embed.logs
    scores, ids = index.search(_to_matrix(embed.vectors), min(k, index.ntotal))
    hits: list[dict] = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0 or idx >= len(chunk_meta):
            continue
        hits.append({**chunk_meta[idx], "score": float(score)})
    return hits, embed.logs
