"""Page-scoped chunking.

Chunks never span pages, which keeps every citation resolvable to a single
page and a single highlight rectangle. Long pages are split with overlap;
a soft preference is given to sentence boundaries near the cut point.
"""

from dataclasses import dataclass

from .. import config
from .extraction import PageText, Word

_SENTENCE_END = (".", "?", "!", ";")


@dataclass
class ChunkDraft:
    page_number: int
    seq: int
    text: str
    bbox: list[float] | None
    word_count: int


def _line_key(word: Word, tolerance: float = 3.0) -> int:
    return int(round(word.top / tolerance))


def _group_lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    current: list[Word] = []
    current_key: int | None = None
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        key = _line_key(w)
        if current_key is None or key == current_key:
            current.append(w)
            current_key = key
        else:
            lines.append(current)
            current = [w]
            current_key = key
    if current:
        lines.append(current)
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def _union_bbox(words: list[Word]) -> list[float]:
    return [
        round(min(w.x0 for w in words), 2),
        round(min(w.top for w in words), 2),
        round(max(w.x1 for w in words), 2),
        round(max(w.bottom for w in words), 2),
    ]


def _pick_cut(words: list[Word], target: int) -> int:
    """Cut at a sentence boundary near `target` when one exists."""
    window_start = max(int(target * 0.7), 1)
    for i in range(min(target, len(words) - 1), window_start, -1):
        if words[i - 1].text.endswith(_SENTENCE_END):
            return i
    return target


def _chunk_line_words(
    words: list[Word], chunk_words: int, overlap_words: int
) -> list[tuple[list[Word], int]]:
    """Return (word_run, seq) groups for one page."""
    runs: list[tuple[list[Word], int]] = []
    i = 0
    seq = 0
    n = len(words)
    while i < n:
        end = min(i + chunk_words, n)
        if end < n:
            end = i + _pick_cut(words[i:end], chunk_words) if end - i == chunk_words else end
            end = min(end, n)
        run = words[i:end]
        if len(run) < 15 and runs:
            # Too-small tail: fold it into the previous chunk.
            prev_run, prev_seq = runs[-1]
            runs[-1] = (prev_run + run, prev_seq)
            break
        runs.append((run, seq))
        seq += 1
        if end >= n:
            break
        i = max(end - overlap_words, i + 1)
    return runs


def chunk_pages(pages: list[PageText]) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for page in pages:
        if not page.words:
            continue
        lines = _group_lines(page.words)
        flat: list[Word] = [w for line in lines for w in line]
        for run, seq in _chunk_line_words(
            flat, config.CHUNK_WORDS, config.CHUNK_OVERLAP_WORDS
        ):
            text = " ".join(w.text for w in run)
            chunks.append(
                ChunkDraft(
                    page_number=page.number,
                    seq=seq,
                    text=text,
                    bbox=_union_bbox(run),
                    word_count=len(run),
                )
            )
    return chunks
