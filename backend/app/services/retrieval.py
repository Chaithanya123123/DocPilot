"""Hybrid retrieval: dense (FAISS/cosine) + lexical (BM25), fused with RRF."""

import json
import threading
from dataclasses import dataclass

import numpy as np

from .. import config
from ..db import db
from .bm25 import BM25Index
from .mistral_client import MistralClient
from .vector_index import DocumentIndex

_RRF_K = 60
_index_cache: dict[str, DocumentIndex] = {}
_cache_lock = threading.Lock()


@dataclass
class Evidence:
    chunk_id: str
    page_number: int
    text: str
    bbox: list[float] | None
    cosine: float
    bm25: float
    fused: float


def get_document_index(document_id: str) -> DocumentIndex | None:
    with _cache_lock:
        cached = _index_cache.get(document_id)
        if cached is not None:
            return cached
    from .vector_index import index_path

    index = DocumentIndex.load(index_path(document_id))
    if index is not None:
        with _cache_lock:
            _index_cache[document_id] = index
    return index


def invalidate_document(document_id: str) -> None:
    with _cache_lock:
        _index_cache.pop(document_id, None)


def retrieve(
    document_id: str, question: str, client: MistralClient | None = None
) -> tuple[list[Evidence], float]:
    """Return fused evidence (best first) and the best raw cosine score."""
    index = get_document_index(document_id)
    if index is None or index.size == 0:
        return [], 0.0

    query_vector = (client or MistralClient()).embed([question])[0]
    dense_hits = index.search(query_vector, k=min(config.CANDIDATE_POOL, index.size))

    with db() as conn:
        rows = conn.execute(
            "SELECT chunk_id, page_number, text, bbox_json FROM chunks "
            "WHERE document_id = ?",
            (document_id,),
        ).fetchall()
    chunk_meta = {r["chunk_id"]: r for r in rows}
    ordered_texts = [r["text"] for r in rows]

    bm25 = BM25Index()
    bm25.build(ordered_texts)
    bm25_scores = bm25.scores(question)
    lexical_ranked = sorted(
        range(len(bm25_scores)), key=lambda i: -bm25_scores[i]
    )[: config.CANDIDATE_POOL]
    lexical_hits = [
        (rows[i]["chunk_id"], float(bm25_scores[i]))
        for i in lexical_ranked
        if bm25_scores[i] > 0
    ]

    fused: dict[str, float] = {}
    for rank, (chunk_id, _score) in enumerate(dense_hits):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, (chunk_id, _score) in enumerate(lexical_hits):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)

    bm25_by_id = dict(lexical_hits)
    dense_by_id = dict(dense_hits)
    evidence: list[Evidence] = []
    for chunk_id, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        row = chunk_meta.get(chunk_id)
        if row is None:
            continue
        evidence.append(
            Evidence(
                chunk_id=chunk_id,
                page_number=int(row["page_number"]),
                text=row["text"],
                bbox=json.loads(row["bbox_json"]) if row["bbox_json"] else None,
                cosine=float(dense_by_id.get(chunk_id, 0.0)),
                bm25=float(bm25_by_id.get(chunk_id, 0.0)),
                fused=float(score),
            )
        )
        if len(evidence) >= config.TOP_K_EVIDENCE:
            break

    best_cosine = max((e.cosine for e in evidence), default=0.0)
    if not evidence and dense_hits:
        # Everything was filtered out by metadata lookup failure; still
        # surface the dense best so the caller can abstain on score alone.
        best_cosine = dense_hits[0][1]
    return evidence, best_cosine
