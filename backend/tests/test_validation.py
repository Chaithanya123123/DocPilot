from app.services.ingestion import validate_pdf


def test_rejects_non_pdf_extension():
    assert validate_pdf(b"%PDF-1.4 fake", "notes.txt") is not None


def test_rejects_wrong_magic_bytes():
    error = validate_pdf(b"GIF89a not a pdf at all" + b" " * 200, "doc.pdf")
    assert error is not None and "valid PDF" in error


def test_rejects_tiny_file():
    assert validate_pdf(b"%PDF-", "doc.pdf") is not None


def test_accepts_valid_pdf_header(app_env, sample_pdf_bytes):
    assert validate_pdf(sample_pdf_bytes, "sample.pdf") is None


def test_rejects_oversize(app_env, monkeypatch, sample_pdf_bytes):
    from app import config

    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    big = sample_pdf_bytes + b"0" * (2 * 1024 * 1024)
    error = validate_pdf(big, "big.pdf")
    assert error is not None and "limit" in error
