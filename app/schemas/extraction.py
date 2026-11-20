from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict


class ExtractionResult(BaseModel):
    """Respuesta estándar de extracción — compatible con contrato original."""
    model_config = ConfigDict(extra="forbid")
    
    content: str = Field(description="Texto extraído (plano o Markdown)")
    page_count: int = Field(ge=0, description="Número de páginas del PDF")


class HealthResponse(BaseModel):
    """Health check liveness."""
    status: str = "ok"


class ReadinessResponse(BaseModel):
    """Health check readiness."""
    status: str
    pending_extractions: int
    max_pending_extractions: int
    extraction_workers: int
    queue_utilization_percent: float