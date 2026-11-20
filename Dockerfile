# ========================================================================
# PDF Extract Service - Multi-stage Dockerfile
# ========================================================================
# Builder stage: instala dependencias y compila
# ========================================================================
FROM python:3.14-slim AS builder

WORKDIR /app

# Dependencias del sistema para compilar
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmupdf-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv
RUN pip install --no-cache-dir uv

# Copiar archivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar dependencias Python en entorno virtual
RUN uv sync --frozen --no-default-groups --no-cache

# ========================================================================
# Runtime stage: imagen mínima para producción
# ========================================================================
FROM python:3.14-slim AS runtime

WORKDIR /app

# Dependencias de runtime (sin build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    # Para healthcheck
    curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup --home /home/appuser appuser

# Copiar entorno virtual desde builder
COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv

# Copiar código de la aplicación
COPY --chown=appuser:appgroup app/ ./app/

# Variables de entorno
ENV PATH="/app/.venv/bin:$PATH" \
    UV_CACHE_DIR=/tmp/.uv-cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Usuario no-root
USER appuser

# Puerto
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health/live', timeout=2).raise_for_status()"

# Metadata
LABEL org.opencontainers.image.title="PDF Extract Service" \
      org.opencontainers.image.description="Microservicio stateless para extracción de texto y Markdown desde PDFs" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="PDF Extract Team" \
      org.opencontainers.image.source="https://github.com/example/pdf-extract-service" \
      org.opencontainers.image.licenses="MIT"

# Comando de inicio
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]