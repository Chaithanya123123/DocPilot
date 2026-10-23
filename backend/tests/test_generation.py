from app.services.generation import ABSTAIN_ANSWER, extractive_answer, generate_answer
from app.services.retrieval import Evidence


def make_evidence(chunk_id: str, page: int = 1, text: str = "some evidence text") -> Evidence:
    return Evidence(
        chunk_id=chunk_id,
        page_number=page,
        text=text,
        bbox=[10.0, 20.0, 300.0, 60.0],
        cosine=0.8,
        bm25=2.0,
        fused=0.03,
    )


class StubClient:
    def __init__(self, response):
        self.response = response

    def chat_json(self, system, user, temperature=0.1):
        return self.response


def test_valid_citations_kept_invalid_dropped():
    evidence = [make_evidence("c1"), make_evidence("c2")]
    client = StubClient(
        {
            "answer": "Because of X.",
            "grounded": True,
            "citations": ["c1", "chunk_invented_by_model"],
        }
    )
    result = generate_answer("q?", evidence, client=client)
    assert result.grounded is True
    assert result.cited_chunk_ids == ["c1"]


def test_grounded_without_valid_citations_becomes_abstention():
    evidence = [make_evidence("c1")]
    client = StubClient(
        {"answer": "Confident claim.", "grounded": True, "citations": ["made_up"]}
    )
    result = generate_answer("q?", evidence, client=client)
    assert result.grounded is False
    assert result.cited_chunk_ids == []
    assert result.answer == ABSTAIN_ANSWER


def test_explicit_model_abstention_is_preserved():
    evidence = [make_evidence("c1")]
    client = StubClient(
        {
            "answer": "I could not find sufficient evidence in the provided passages.",
            "grounded": False,
            "citations": [],
        }
    )
    result = generate_answer("q?", evidence, client=client)
    assert result.grounded is False
    assert "sufficient evidence" in result.answer.lower()


def test_duplicate_citations_deduplicated():
    evidence = [make_evidence("c1"), make_evidence("c2")]
    client = StubClient(
        {"answer": "A and B.", "grounded": True, "citations": ["c1", "c1", "c2"]}
    )
    result = generate_answer("q?", evidence, client=client)
    assert result.cited_chunk_ids == ["c1", "c2"]


def test_extractive_fallback_cites_top_evidence():
    evidence = [
        make_evidence("c1", page=2, text="first passage"),
        make_evidence("c2", page=5, text="second passage"),
    ]
    result = extractive_answer(evidence)
    assert result.grounded is True
    assert result.cited_chunk_ids == ["c1", "c2"]
    assert "Page 2" in result.answer and "first passage" in result.answer
