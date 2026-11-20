from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app


def test_multiple_process_workers_extract_pdfs(monkeypatch, build_pdf):
    monkeypatch.setenv("APP_EXTRACT_WORKERS", "2")
    first_pdf = build_pdf([("Primero", 11)])
    second_pdf = build_pdf([("Segundo", 11)])

    with TestClient(app) as client, ThreadPoolExecutor(2) as callers:
        assert client.get("/health/ready").json()["extraction_workers"] == 2
        first = callers.submit(client.post, "/extract/text", content=first_pdf)
        second = callers.submit(client.post, "/extract", content=second_pdf)
        assert first.result().json() == {"content": "Primero", "page_count": 1}
        assert second.result().json() == {"content": "Segundo", "page_count": 1}
