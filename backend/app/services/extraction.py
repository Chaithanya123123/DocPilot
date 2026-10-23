"""PDF text extraction with per-word bounding boxes via pdfplumber.

Coordinate system: pdfplumber reports positions in PDF points with a
top-left origin, which matches the PDF.js viewport at scale 1, so the
stored boxes can be drawn on the rendered page without conversion.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class PageText:
    number: int
    width: float
    height: float
    words: list[Word] = field(default_factory=list)


class ExtractionError(Exception):
    pass


def extract_pdf(path: Path) -> list[PageText]:
    import pdfplumber

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    pages: list[PageText] = []
    try:
        if not pdf.pages:
            raise ExtractionError("PDF contains no pages.")
        for number, page in enumerate(pdf.pages, start=1):
            words = []
            for w in page.extract_words(
                x_tolerance=2.0,
                y_tolerance=2.0,
                keep_blank_chars=False,
                use_text_flow=False,
            ):
                words.append(
                    Word(
                        text=w["text"],
                        x0=float(w["x0"]),
                        top=float(w["top"]),
                        x1=float(w["x1"]),
                        bottom=float(w["bottom"]),
                    )
                )
            pages.append(
                PageText(
                    number=number,
                    width=float(page.width),
                    height=float(page.height),
                    words=words,
                )
            )
    finally:
        pdf.close()

    if not any(p.words for p in pages):
        raise ExtractionError(
            "No extractable text found. This looks like a scanned PDF; "
            "OCR is not enabled in this build."
        )
    return pages
