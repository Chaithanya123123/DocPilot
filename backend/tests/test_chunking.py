from app.services.chunking import chunk_pages
from app.services.extraction import PageText, Word


def make_page(number: int, text: str, width: float = 612.0, height: float = 792.0) -> PageText:
    words = []
    x, y = 72.0, 72.0
    for token in text.split():
        words.append(Word(text=token, x0=x, top=y, x1=x + 40, bottom=y + 12))
        x += 45
        if x > 500:
            x = 72.0
            y += 18
    return PageText(number=number, width=width, height=height, words=words)


def test_chunks_are_page_scoped():
    pages = [
        make_page(1, " ".join(f"w{i}" for i in range(300))),
        make_page(2, " ".join(f"v{i}" for i in range(300))),
    ]
    chunks = chunk_pages(pages)
    assert chunks
    page_numbers = {c.page_number for c in chunks}
    assert page_numbers == {1, 2}
    for c in chunks:
        assert c.word_count > 0
        assert c.bbox is not None
        assert len(c.bbox) == 4


def test_long_page_is_split_with_overlap():
    words = [f"tok{i}" for i in range(500)]
    chunks = chunk_pages([make_page(1, " ".join(words))])
    assert len(chunks) >= 2
    texts = [c.text for c in chunks]
    assert any("tok0" in t for t in texts)
    assert any(f"tok{499}" in t for t in texts)
    # Consecutive chunks should share some tokens (overlap).
    first_tokens = set(chunks[0].text.split())
    second_tokens = set(chunks[1].text.split())
    assert first_tokens & second_tokens


def test_bbox_is_union_of_words():
    chunks = chunk_pages([make_page(3, "alpha beta gamma")])
    assert len(chunks) == 1
    bbox = chunks[0].bbox
    assert bbox == [72.0, 72.0, 72.0 + 40 + 45 + 45, 72.0 + 12]
    assert chunks[0].page_number == 3


def test_empty_page_produces_no_chunks():
    pages = [PageText(number=1, width=612, height=792, words=[])]
    assert chunk_pages(pages) == []
