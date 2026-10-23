"""Generate a multi-page sample research paper for demos and tests."""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[2] / "samples" / "sample_report.pdf"

SECTIONS = [
    (
        "Abstract",
        [
            "We present RegionRAG, a retrieval-augmented generation system that "
            "grounds large language model answers in exact regions of source "
            "documents. Unlike conventional chunk-level RAG, RegionRAG retains "
            "page coordinates for every passage so that user interfaces can "
            "highlight the precise text supporting each claim.",
            "In evaluation on 1,200 questions over technical reports, RegionRAG "
            "improved citation accuracy by 31 percent over a strong baseline and "
            "reduced unverifiable answers by half.",
        ],
    ),
    (
        "1. Introduction",
        [
            "Large language models frequently produce fluent but unsupported "
            "statements when answering questions about long documents. "
            "Retrieval-augmented generation mitigates this by conditioning the "
            "model on retrieved passages, but standard pipelines discard the "
            "spatial information needed to show users where evidence came from.",
            "DocPilot is a voice-first application built on RegionRAG. Users "
            "upload documents, ask questions by voice or text, and receive "
            "answers linked to the exact supporting passages in the original "
            "file.",
        ],
    ),
    (
        "2. Method",
        [
            "Documents are parsed with a layout-aware extractor that records "
            "bounding boxes for each text region. Pages are split into "
            "overlapping chunks of roughly 220 words; chunks never span pages so "
            "each citation resolves to a single highlight rectangle.",
            "Each chunk is embedded with a dense encoder and indexed with FAISS. "
            "At query time we fuse dense cosine similarity with BM25 lexical "
            "scores using reciprocal rank fusion, which recovers technical terms "
            "that dense encoders sometimes underweight.",
            "The generator is instructed to answer only from retrieved evidence "
            "and to cite chunk identifiers. A server-side validator drops any "
            "cited identifier that was not actually retrieved, preventing the "
            "model from inventing page numbers or coordinates.",
        ],
    ),
    (
        "3. Experiments",
        [
            "We evaluate on three corpora: arXiv computer science papers, "
            "internal engineering reports, and product manuals. Metrics include "
            "answer correctness judged by experts, citation precision, "
            "end-to-end latency, and abstention quality on unanswerable "
            "questions.",
            "RegionRAG achieves 88 percent citation precision versus 67 percent "
            "for chunk-only RAG. Median latency is 2.4 seconds for retrieval and "
            "generation combined, with retrieval accounting for 310 milliseconds.",
        ],
    ),
    (
        "4. Results",
        [
            "Ablations show that removing the lexical branch reduces citation "
            "precision by 9 points on manuals containing rare part numbers. "
            "Removing server-side citation validation increases hallucinated "
            "citations from 2 percent to 14 percent.",
            "Users completed document question tasks 38 percent faster with "
            "source highlighting enabled, and reported higher trust when answers "
            "displayed the supporting excerpt next to the viewer.",
        ],
    ),
    (
        "5. Limitations",
        [
            "Our method depends on a usable text layer. Scanned documents "
            "require optical character recognition, and OCR errors propagate "
            "into chunks, embeddings, and highlighted regions. This build does "
            "not yet include an OCR fallback, so image-only PDFs are rejected "
            "during ingestion.",
            "Bounding box quality varies with document structure. Tables, "
            "multi-column layouts, and math-heavy pages can produce fragmented "
            "reading order, which occasionally yields chunks that mix unrelated "
            "sentences and dilute retrieval quality.",
            "The retrieval threshold is a single global constant. Documents "
            "written in very different styles may need per-document calibration, "
            "and we have not studied automatic threshold tuning.",
            "Evaluation covers English documents only. Code-switched text and "
            "right-to-left scripts remain untested, and the speech interface "
            "inherits the recognition errors of the underlying browser engine.",
        ],
    ),
    (
        "6. Conclusion",
        [
            "Preserving the link between an answer and its original evidence is "
            "the core requirement for trustworthy document assistants. RegionRAG "
            "demonstrates that lightweight spatial metadata plus server-side "
            "citation validation is sufficient to make RAG answers verifiable.",
        ],
    ),
]


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=LETTER)
    width, height = LETTER
    margin = inch
    y = height - margin

    def new_page():
        nonlocal y
        c.showPage()
        y = height - margin

    def ensure(space: float):
        nonlocal y
        if y - space < margin:
            new_page()

    for title, paragraphs in SECTIONS:
        ensure(36)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, y, title)
        y -= 22
        for para in paragraphs:
            c.setFont("Helvetica", 10.5)
            words = para.split()
            line = ""
            for word in words:
                trial = f"{line} {word}".strip()
                if c.stringWidth(trial, "Helvetica", 10.5) > width - 2 * margin:
                    ensure(16)
                    c.drawString(margin, y, line)
                    y -= 14
                    line = word
                else:
                    line = trial
            if line:
                ensure(16)
                c.drawString(margin, y, line)
                y -= 18
        y -= 8

    c.save()
    return OUT


if __name__ == "__main__":
    print("wrote", build())
