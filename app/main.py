from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app import __version__
from app.api.exception_handlers import register_exception_handlers
from app.api.routes import extraction as extraction_routes
from app.config.settings import get_settings
from app.logging_config import configure_logging
from app.services.interfaces import PDFExtractionService
from app.services.pdf_extraction_service import PDFExtractionServiceImpl

load_dotenv()

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
logger.info("Settings loaded: %s", settings)

# Configurar multipart parser para mantener archivos grandes en memoria
from starlette.formparsers import MultiPartParser
MultiPartParser.spool_max_size = sys.maxsize


# --- DI Container simple ---
_extraction_service: PDFExtractionService | None = None


def get_extraction_service() -> PDFExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = PDFExtractionServiceImpl(settings)
    return _extraction_service


def reset_extraction_service() -> None:
    """Reset the cached service (for testing)."""
    global _extraction_service
    if _extraction_service is not None:
        _extraction_service.shutdown()
        _extraction_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting PDF Extract Service")
    # NO inicializar aquí - dejar que la primera request lo haga (lazy init)
    
    # Signal handlers para graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig: int) -> None:
        logger.info("Received signal %s, initiating graceful shutdown...", sig)
        shutdown_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler, sig)
        except NotImplementedError:
            # Windows no soporta add_signal_handler para SIGTERM/SIGINT en algunos casos
            pass
    
    yield
    
    # Shutdown graceful
    logger.info("Shutting down PDF Extract Service...")
    # Esperar a que terminen las extracciones en curso (con timeout)
    service = get_extraction_service()
    stats = service.get_stats()
    if stats.pending > 0:
        logger.info("Waiting for %d pending extractions to complete...", stats.pending)
        # Esperar máximo 30 segundos para que terminen
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for pending extractions, forcing shutdown")
    
    service.shutdown()
    _extraction_service = None
    logger.info("PDF Extract Service stopped")


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

# Registrar exception handlers
register_exception_handlers(app)

# Incluir rutas
app.include_router(extraction_routes.router)