import hashlib
import math
import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


EMBED_DIM = 1024


def hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hashing embeddings for tests."""
    vec = [0.0] * EMBED_DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeMistralClient:
    """Stand-in for MistralClient: deterministic embeddings, canned chat."""

    chat_response: dict = {
        "answer": "The method is slow and memory hungry.",
        "grounded": True,
        "citations": [],
    }

    def __init__(self, *args, **kwargs):
        pass

    def embed(self, texts, batch_size=8):
        return [hash_embed(t) for t in texts]

    def chat_json(self, system, user, temperature=0.1):
        return dict(self.chat_response)

    def close(self):
        pass


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "storage" / "uploads")
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path / "storage" / "indexes")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "storage" / "test.db")
    # Hash-based test embeddings do not have realistic cosine ranges.
    monkeypatch.setattr(config, "SUFFICIENCY_THRESHOLD", 0.05)
    config.ensure_dirs()

    from app.db import init_db

    init_db()

    from app.services.retrieval import _index_cache

    _index_cache.clear()
    yield
    _index_cache.clear()


@pytest.fixture()
def fake_client():
    return FakeMistralClient()


@pytest.fixture()
def sample_pdf_bytes():
    """A one-page PDF with known text, built with reportlab."""
    import io

    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    c.setFont("Helvetica", 11)
    y = 720
    for line in [
        "DocPilot test document.",
        "The limitations of this method include slow speed and high memory usage.",
        "The system validates citations on the server side before responding.",
        "Unrelated filler text about cooking pasta with tomato sauce.",
    ]:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()
    return buffer.getvalue()


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
