from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app import __version__
from app.api.exception_handlers import register_exception_handlers
from app.api.routes.extraction import router
from app.config.settings import get_settings
from app.logging_config import configure_logging
from app.services.pdf_extraction_service import PDFExtractionServiceImpl

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    service = PDFExtractionServiceImpl(settings)
    app.state.settings = settings
    app.state.extraction_service = service
    try:
        yield
    finally:
        await service.shutdown()


app = FastAPI(title=get_settings().app_name, version=__version__, lifespan=lifespan)
register_exception_handlers(app)
app.include_router(router)
