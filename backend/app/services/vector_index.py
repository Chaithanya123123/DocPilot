"""Per-document vector index with FAISS (numpy fallback) and persistence.

One index file per document keeps deletion trivial and retrieval scoped.
Vectors are L2-normalized, so an inner-product search equals cosine
similarity.
"""

import json
from pathlib import Path

import numpy as np

from .. import config

try:
    import faiss  # type: ignore

    _HAS_FAISS = True
except Exception:  # pragma: no cover - numpy fallback
    faiss = None
    _HAS_FAISS = False


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (matrix / norms).astype(np.float32)


class DocumentIndex:
    def __init__(self, dim: int = config.EMBED_DIM):
        self.dim = dim
        self.ids: list[str] = []
        self._vectors: np.ndarray | None = None
        self._faiss_index = None

    @property
    def size(self) -> int:
        return len(self.ids)

    def build(self, ids: list[str], vectors: list[list[float]]) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have the same length")
        matrix = l2_normalize(np.asarray(vectors, dtype=np.float32))
        if matrix.shape[1] != self.dim:
            raise ValueError(
                f"Embedding dimension {matrix.shape[1]} != expected {self.dim}"
            )
        self.ids = list(ids)
        self._vectors = matrix
        if _HAS_FAISS:
            index = faiss.IndexFlatIP(self.dim)
            index.add(matrix)
            self._faiss_index = index

    def search(self, query_vector: list[float], k: int = 5) -> list[tuple[str, float]]:
        if self.size == 0:
            return []
        query = l2_normalize(np.asarray([query_vector], dtype=np.float32))
        k = min(k, self.size)
        if self._faiss_index is not None:
            scores, indexes = self._faiss_index.search(query, k)
            return [
                (self.ids[int(j)], float(s))
                for s, j in zip(scores[0], indexes[0])
                if int(j) >= 0
            ]
        scores = (self._vectors @ query[0]).astype(np.float64)
        order = np.argsort(-scores)[:k]
        return [(self.ids[int(i)], float(scores[int(i)])) for i in order]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(path) + ".npy", self._vectors)
        (path.parent / (path.name + ".ids.json")).write_text(
            json.dumps(self.ids), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "DocumentIndex | None":
        vectors_path = Path(str(path) + ".npy")
        ids_path = path.parent / (path.name + ".ids.json")
        if not vectors_path.exists() or not ids_path.exists():
            return None
        vectors = np.load(str(vectors_path))
        ids = json.loads(ids_path.read_text(encoding="utf-8"))
        index = cls(dim=vectors.shape[1])
        index.build(ids, vectors.tolist())
        return index


def delete_index(document_id: str) -> None:
    path = index_path(document_id)
    for p in (
        Path(str(path) + ".npy"),
        path.parent / (path.name + ".ids.json"),
    ):
        if p.exists():
            p.unlink()


def index_path(document_id: str) -> Path:
    return config.INDEX_DIR / f"{document_id}.index"
