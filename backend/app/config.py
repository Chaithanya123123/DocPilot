import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/")
MISTRAL_CHAT_MODEL = os.getenv("MISTRAL_CHAT_MODEL", "mistral-small-latest")
MISTRAL_EMBED_MODEL = os.getenv("MISTRAL_EMBED_MODEL", "mistral-embed")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))

TOP_K_EVIDENCE = int(os.getenv("TOP_K_EVIDENCE", "6"))
CANDIDATE_POOL = int(os.getenv("CANDIDATE_POOL", "20"))
SUFFICIENCY_THRESHOLD = float(os.getenv("SUFFICIENCY_THRESHOLD", "0.45"))

CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "220"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
CHAT_TIMEOUT = float(os.getenv("CHAT_TIMEOUT", "60"))

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BACKEND_DIR / "storage")))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(STORAGE_DIR / "uploads")))
INDEX_DIR = Path(os.getenv("INDEX_DIR", str(STORAGE_DIR / "indexes")))
DB_PATH = Path(os.getenv("DB_PATH", str(STORAGE_DIR / "docpilot.db")))

SAMPLE_DIR = BACKEND_DIR.parent / "samples"


def ensure_dirs() -> None:
    for d in (STORAGE_DIR, UPLOAD_DIR, INDEX_DIR):
        d.mkdir(parents=True, exist_ok=True)
