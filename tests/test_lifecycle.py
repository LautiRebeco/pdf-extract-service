
import asyncio
from threading import Event

import httpx
import pytest

from app.main import app
from app.schemas.extraction import ExtractionResult

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def blocked_worker(monkeypatch):
    started, release = Event(), Event()

    def extract(*args, **kwargs):
        started.set()
        assert release.wait(8)
        return ExtractionResult(content="texto", page_count=1)

    monkeypatch.setattr("app.services.pdf_extraction_service._extract_text", extract)
    monkeypatch.setenv("APP_EXTRACT_WORKERS", "1")
    monkeypatch.setenv("APP_MAX_PENDING_EXTRACTIONS", "1")
    yield started, release
    release.set()


def client_for_app():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def wait_until(check):
    async with asyncio.timeout(4):
        while not check():
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("cancel_request", [False, True])
async def test_abandoned_request_keeps_running_job_counted(
    monkeypatch, blocked_worker, pdf_bytes, cancel_request
):
    monkeypatch.setenv("APP_EXTRACTION_TIMEOUT_SECONDS", "1")
    started, release = blocked_worker
    async with app.router.lifespan_context(app), client_for_app() as client:
        request = asyncio.create_task(client.post("/extract/text", content=pdf_bytes))
        await wait_until(started.is_set)
        if cancel_request:
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            assert (await request).status_code == 504

        try:
            assert (await client.get("/health/ready")).status_code == 503
            rejected = await client.post("/extract/text", content=pdf_bytes)
            assert rejected.status_code == 503
            assert rejected.headers["Retry-After"] == "1"
        finally:
            release.set()
        await wait_until(lambda: app.state.extraction_service.get_stats().pending == 0)
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.post("/extract/text", content=pdf_bytes)).status_code == 200


@pytest.mark.parametrize("release_during_shutdown", [True, False])
async def test_lifespan_drains_or_returns_at_deadline(
    monkeypatch, blocked_worker, pdf_bytes, release_during_shutdown
):
    monkeypatch.setenv("APP_SHUTDOWN_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("APP_MAX_PENDING_EXTRACTIONS", "2")
    started, release = blocked_worker
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    async with client_for_app() as client:
        active = asyncio.create_task(client.post("/extract/text", content=pdf_bytes))
        await wait_until(started.is_set)
        service = app.state.extraction_service
        queued = asyncio.create_task(client.post("/extract/text", content=pdf_bytes))
        await wait_until(lambda: service.get_stats().pending == 2)
        closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
        try:
            await wait_until(lambda: service.get_stats().closing)
            ready = await client.get("/health/ready")
            assert ready.status_code == 503
            assert ready.json()["status"] == "closing"
            assert (await client.get("/health/live")).status_code == 200
            assert not closing.done()
            assert (await asyncio.wait_for(queued, 0.5)).status_code == 503
            if release_during_shutdown:
                release.set()
            await asyncio.wait_for(closing, 3)
            assert service.get_stats().pending == (0 if release_during_shutdown else 1)
        finally:
            release.set()
            await closing
            await asyncio.gather(active, queued, return_exceptions=True)
