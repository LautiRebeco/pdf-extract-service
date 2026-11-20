
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.extraction import ExtractionResult


def test_requests_share_capacity(monkeypatch, pdf_bytes):
    monkeypatch.setenv("APP_MAX_PENDING_EXTRACTIONS", "2")
    monkeypatch.setenv("APP_EXTRACT_WORKERS", "1")
    started, release = Event(), Event()
    calls = []

    def blocked_extract(*args, **kwargs):
        calls.append(1)
        started.set()
        assert release.wait(8)
        return ExtractionResult(content="texto", page_count=1)

    monkeypatch.setattr("app.services.pdf_extraction_service._extract_text", blocked_extract)
    with TestClient(app) as client, ThreadPoolExecutor(2) as callers:
        first = callers.submit(client.post, "/extract/text", content=pdf_bytes)
        try:
            assert started.wait(4)
            second = callers.submit(client.post, "/extract/text", content=pdf_bytes)
            import time

            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                ready = client.get("/health/ready")
                if ready.json()["pending_extractions"] == 2:
                    break
                time.sleep(0.01)
            assert ready.status_code == 503
            assert ready.json()["pending_extractions"] == 2
            assert len(calls) == 1
            assert client.get("/health/live").status_code == 200
            rejected = client.post("/extract", content=pdf_bytes)
            assert rejected.status_code == 503
            assert rejected.headers["Retry-After"] == "1"
        finally:
            release.set()
        assert first.result().json() == {"content": "texto", "page_count": 1}
        assert second.result().status_code == 200
        assert client.get("/health/ready").json()["pending_extractions"] == 0
