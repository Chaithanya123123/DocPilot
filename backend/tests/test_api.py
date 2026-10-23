from app.services.ingestion import run_ingestion, set_status


def upload_pdf(client, sample_pdf_bytes, name="sample.pdf"):
    resp = client.post(
        "/api/documents",
        files={"file": (name, sample_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["document_id"]


def ingest_ready(client, document_id, monkeypatch, fake_client):
    """Upload with background work disabled, then run ingestion inline."""
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    monkeypatch.setattr("app.services.ingestion.MistralClient", lambda *a, **k: fake_client)
    run_ingestion(document_id)
    status = client.get(f"/api/documents/{document_id}/status").json()
    assert status["status"] == "ready", status
    return status


def test_upload_rejects_non_pdf(client):
    resp = client.post(
        "/api/documents",
        files={"file": ("malware.exe", b"MZ\x90\x00" + b"\x00" * 200, "application/pdf")},
    )
    assert resp.status_code == 400


def test_full_document_lifecycle(client, app_env, monkeypatch, sample_pdf_bytes, fake_client):
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)

    # Upload
    document_id = upload_pdf(client, sample_pdf_bytes)
    status = client.get(f"/api/documents/{document_id}/status").json()
    assert status["status"] == "uploaded"

    # Ingest with fake embeddings
    status = ingest_ready(client, document_id, monkeypatch, fake_client)
    assert status["page_count"] == 1
    assert status["chunk_count"] >= 1

    # Page metadata resolves chunks with bboxes
    page = client.get(f"/api/documents/{document_id}/pages/1").json()
    assert page["chunks"]
    assert page["chunks"][0]["bbox"] is not None

    # Ask a question; model cites one real chunk and one invented id
    real_chunk = page["chunks"][0]["chunk_id"]
    fake_client.chat_response = {
        "answer": "The method is slow and memory hungry.",
        "grounded": True,
        "citations": [real_chunk, "doc_fake:p9:9"],
    }
    monkeypatch.setattr("app.routers.questions.MistralClient", lambda *a, **k: fake_client)

    resp = client.post(
        f"/api/documents/{document_id}/questions",
        json={"question": "What are the limitations of this method?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["grounded"] is True
    assert len(body["citations"]) == 1
    assert body["citations"][0]["chunk_id"] == real_chunk
    assert body["citations"][0]["page_number"] == 1
    assert body["citations"][0]["bbox"]

    # Conversation history restores with citations
    conv = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert len(conv["messages"]) == 2
    assert conv["messages"][1]["citations"][0]["chunk_id"] == real_chunk

    # Follow-up in same conversation
    resp2 = client.post(
        f"/api/documents/{document_id}/questions",
        json={"question": "How does citation validation work?", "conversation_id": body["conversation_id"]},
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == body["conversation_id"]

    # Delete removes everything
    assert client.delete(f"/api/documents/{document_id}").status_code == 200
    assert client.get(f"/api/documents/{document_id}/status").status_code == 404
    assert client.get(f"/api/conversations/{body['conversation_id']}").status_code == 404


def test_question_requires_ready_document(client, sample_pdf_bytes, monkeypatch):
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)
    resp = client.post(f"/api/documents/{document_id}/questions", json={"question": "hi?"})
    assert resp.status_code == 409


def test_model_abstention_returns_no_citations(client, monkeypatch, sample_pdf_bytes, fake_client):
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)
    ingest_ready(client, document_id, monkeypatch, fake_client)
    fake_client.chat_response = {
        "answer": "I could not find sufficient evidence in the provided passages.",
        "grounded": False,
        "citations": [],
    }
    monkeypatch.setattr("app.routers.questions.MistralClient", lambda *a, **k: fake_client)
    resp = client.post(
        f"/api/documents/{document_id}/questions",
        json={"question": "What is the airspeed velocity of an unladen swallow?"},
    )
    body = resp.json()
    assert body["grounded"] is False
    assert body["citations"] == []


def test_threshold_forces_abstention_without_model_call(client, monkeypatch, sample_pdf_bytes, fake_client):
    from app import config

    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)
    ingest_ready(client, document_id, monkeypatch, fake_client)

    monkeypatch.setattr(config, "SUFFICIENCY_THRESHOLD", 1.5)

    def boom(*a, **k):
        raise AssertionError("model must not be called when evidence is insufficient")

    fake_client.chat_json = boom
    monkeypatch.setattr("app.routers.questions.MistralClient", lambda *a, **k: fake_client)
    resp = client.post(
        f"/api/documents/{document_id}/questions", json={"question": "anything at all"}
    )
    body = resp.json()
    assert body["grounded"] is False
    assert body["citations"] == []


def test_chat_failure_falls_back_to_extractive(client, monkeypatch, sample_pdf_bytes, fake_client):
    from app.services.mistral_client import MistralError

    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)
    ingest_ready(client, document_id, monkeypatch, fake_client)

    def raise_rate_limited(*a, **k):
        raise MistralError("Mistral API 429 rate limited")

    fake_client.chat_json = raise_rate_limited
    monkeypatch.setattr("app.routers.questions.MistralClient", lambda *a, **k: fake_client)
    resp = client.post(
        f"/api/documents/{document_id}/questions",
        json={"question": "What are the limitations?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounded"] is True
    assert body["citations"]
    assert "closest matching passages" in body["answer"]


def test_failed_document_can_be_retried(client, app_env, sample_pdf_bytes, monkeypatch, fake_client):
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)

    # Simulate a past failure (e.g. model outage during first attempt)
    set_status(document_id, "failed", "model outage")
    resp = client.post(f"/api/documents/{document_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "uploaded"

    ingest_ready(client, document_id, monkeypatch, fake_client)
    assert client.get(f"/api/documents/{document_id}/status").json()["status"] == "ready"


def test_retry_rejects_ready_document(client, monkeypatch, sample_pdf_bytes, fake_client):
    monkeypatch.setattr("app.routers.documents.schedule_ingestion", lambda _id: None)
    document_id = upload_pdf(client, sample_pdf_bytes)
    ingest_ready(client, document_id, monkeypatch, fake_client)
    assert client.post(f"/api/documents/{document_id}/retry").status_code == 409


def test_retry_missing_file_returns_410(client, app_env):
    from app import config
    from app.services.ingestion import create_document

    document_id = create_document("gone.pdf", b"%PDF-1.4 x" * 30)
    set_status(document_id, "failed", "boom")
    (config.UPLOAD_DIR / f"{document_id}.pdf").unlink()
    assert client.post(f"/api/documents/{document_id}/retry").status_code == 410


def test_startup_recovery_requeues_interrupted_documents(app_env, monkeypatch, sample_pdf_bytes):
    from app.db import db
    from app.services.ingestion import create_document, recover_interrupted_documents

    scheduled = []
    monkeypatch.setattr(
        "app.services.ingestion.schedule_ingestion", lambda doc_id: scheduled.append(doc_id)
    )

    live = create_document("live.pdf", sample_pdf_bytes)
    set_status(live, "processing")

    orphan = create_document("orphan.pdf", sample_pdf_bytes)
    set_status(orphan, "processing")
    from app import config

    (config.UPLOAD_DIR / f"{orphan}.pdf").unlink()

    recovered = recover_interrupted_documents()
    assert recovered == 1
    assert scheduled == [live]

    with db() as conn:
        live_status = conn.execute(
            "SELECT status FROM documents WHERE document_id = ?", (live,)
        ).fetchone()["status"]
        orphan_status = conn.execute(
            "SELECT status FROM documents WHERE document_id = ?", (orphan,)
        ).fetchone()["status"]
    assert live_status == "uploaded"
    assert orphan_status == "failed"
