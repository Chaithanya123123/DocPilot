"""Evidence-grounded answer generation with server-side citation validation.

The model never supplies page numbers or bounding boxes: it only names
chunk_ids it was given, and the server resolves every location from the
stored chunk metadata.
"""

from dataclasses import dataclass

from .mistral_client import MistralClient, MistralError
from .retrieval import Evidence

ABSTAIN_ANSWER = (
    "I could not find sufficient evidence in this document to answer that "
    "question. Try rephrasing, or ask about content that appears in the "
    "uploaded file."
)

_SYSTEM_PROMPT = """\
You are DocPilot, a document question-answering assistant.
Answer ONLY using the evidence blocks provided by the user. Each evidence
block starts with its chunk_id and page number.

Rules:
1. Ground every factual statement in one or more evidence blocks.
2. Reply with a single JSON object:
   {
     "answer": "concise answer grounded in the evidence",
     "grounded": true,
     "citations": ["<chunk_id>", "<chunk_id>"]
   }
3. "citations" must contain only chunk_ids copied exactly from the evidence
   blocks you actually used. Never invent chunk_ids.
4. If the evidence does not contain enough information, set "grounded" to
   false, set "citations" to [], and put a short explanation (that you could
   not find sufficient evidence in the provided passages) in "answer".
5. Write the answer in the same language as the user's question.
"""


@dataclass
class GeneratedAnswer:
    answer: str
    grounded: bool
    cited_chunk_ids: list[str]


def build_evidence_block(evidence: list[Evidence]) -> str:
    parts = []
    for i, e in enumerate(evidence, start=1):
        parts.append(
            f"[{i}] chunk_id={e.chunk_id} page={e.page_number}\n{e.text}"
        )
    return "\n\n".join(parts)


def generate_answer(
    question: str, evidence: list[Evidence], client: MistralClient | None = None
) -> GeneratedAnswer:
    client = client or MistralClient()
    user_prompt = (
        f"Evidence blocks:\n\n{build_evidence_block(evidence)}\n\n"
        f"Question: {question}\n\n"
        "Respond with the JSON object only."
    )
    try:
        raw = client.chat_json(_SYSTEM_PROMPT, user_prompt)
    except MistralError:
        raise

    answer = str(raw.get("answer", "")).strip()
    grounded = bool(raw.get("grounded", False))
    raw_citations = raw.get("citations") or []
    if not isinstance(raw_citations, list):
        raw_citations = []

    valid_ids = {e.chunk_id for e in evidence}
    cited: list[str] = []
    for item in raw_citations:
        cid = str(item).strip()
        if cid in valid_ids and cid not in cited:
            cited.append(cid)

    if not answer:
        return GeneratedAnswer(
            answer=ABSTAIN_ANSWER, grounded=False, cited_chunk_ids=[]
        )
    if not grounded:
        # Model explicitly abstained (or flagged insufficient evidence).
        return GeneratedAnswer(answer=answer, grounded=False, cited_chunk_ids=cited)
    if not cited:
        # Model claimed to be grounded but cited nothing we could verify —
        # treat as unverifiable rather than presenting unsupported claims.
        return GeneratedAnswer(
            answer=ABSTAIN_ANSWER, grounded=False, cited_chunk_ids=[]
        )
    return GeneratedAnswer(answer=answer, grounded=True, cited_chunk_ids=cited)


def extractive_answer(evidence: list[Evidence]) -> GeneratedAnswer:
    """Offline fallback when the chat model is unavailable.

    Returns the closest matching passages verbatim as the answer, still
    linked to their exact source chunks — the evidence chain stays intact.
    """
    parts: list[str] = []
    for e in evidence[:3]:
        text = e.text.strip()
        if len(text) > 420:
            text = text[:420].rsplit(" ", 1)[0] + "…"
        parts.append(f"Page {e.page_number}: {text}")
    body = "\n\n".join(parts)
    answer = (
        "The language model is temporarily unavailable, so here are the "
        "closest matching passages from the document:\n\n" + body
    )
    return GeneratedAnswer(
        answer=answer,
        grounded=True,
        cited_chunk_ids=[e.chunk_id for e in evidence[:3]],
    )
