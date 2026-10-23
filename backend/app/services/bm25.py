"""Tiny Okapi BM25 implementation for hybrid lexical retrieval."""

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "were", "with", "from", "we", "our", "their", "they",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens: list[list[str]] = []
        self.doc_freqs: list[Counter] = []
        self.doc_lens: list[int] = []
        self.avg_len: float = 0.0
        self.idf: dict[str, float] = {}

    def build(self, texts: list[str]) -> None:
        self.doc_tokens = [tokenize(t) for t in texts]
        self.doc_freqs = [Counter(toks) for toks in self.doc_tokens]
        self.doc_lens = [len(toks) for toks in self.doc_tokens]
        total = sum(self.doc_lens)
        self.avg_len = (total / len(texts)) if texts else 0.0
        df: Counter = Counter()
        for freqs in self.doc_freqs:
            df.update(freqs.keys())
        n = max(len(texts), 1)
        self.idf = {
            term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()
        }

    def scores(self, query: str) -> list[float]:
        q_tokens = tokenize(query)
        out: list[float] = []
        for freqs, length in zip(self.doc_freqs, self.doc_lens):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
            for term in q_tokens:
                tf = freqs.get(term)
                if not tf:
                    continue
                idf = self.idf.get(term, 0.0)
                score += idf * (tf * (self.k1 + 1)) / (tf + norm)
            out.append(score)
        return out
