import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    page_count INTEGER,
    chunk_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    PRIMARY KEY (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    bbox_json TEXT,
    word_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    grounded INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    excerpt TEXT NOT NULL,
    bbox_json TEXT,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_citations_message ON citations(message_id);
"""


def init_db() -> None:
    config.ensure_dirs()
    with db() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
