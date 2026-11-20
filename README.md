# PDF Extract Service

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-54%20passing-brightgreen.svg)]()

Microservicio **stateless** para extracción de texto y Markdown desde archivos PDF. Parte del trabajo universitario de Desarrollo de Software — módulo `services/extract/`.

---

## 🎯 Propósito

Extraer contenido textual de PDFs de forma confiable, escalable y resiliente, exponiendo una API REST simple. Diseñado para integrarse en una arquitectura de microservicios (orquestador, documentos, resúmenes, notificaciones).

### Funcionalidades

| Funcionalidad | Descripción |
|---------------|-------------|
| **Extracción de texto plano** | `POST /extract/text` — Texto plano con saltos de línea por página |
| **Conversión a Markdown** | `POST /extract` — Markdown con detección de headings (#, ##) por tamaño de fuente |
| **OCR opcional** | Tesseract + PIL para imágenes embebidas (configurable) |
| **Validaciones** | Tamaño máximo, contenido PDF válido, archivo no vacío |
| **Concurrencia controlada** | ThreadPoolExecutor + cola acotada + HTTP 503 + Retry-After |
| **Health checks** | `/health` (liveness), `/health/live`, `/health/ready` (readiness) |
| **Graceful shutdown** | SIGTERM/SIGINT, drenado de requests en curso |

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI App                            │
├─────────────────────────────────────────────────────────────┤
│  API Routes (/extract, /extract/text, /health*)            │
│  Exception Handlers (InvalidPDFError, HTTPException, 500)  │
├─────────────────────────────────────────────────────────────┤
│  PDFExtractionService (Protocol + Impl)                    │
│  ├─ ThreadPoolExecutor (bulkhead)                          │
│  ├─ Cola acotada (max_pending) + 503 + Retry-After         │
│  └─ Timeout por extracción (asyncio.wait_for)              │
├─────────────────────────────────────────────────────────────┤
│  PDF Core (lógica pura, sin HTTP)                          │
│  ├─ extractor.py  — extract_text, extract_markdown         │
│  ├─ ocr.py        — Tesseract wrapper                      │
│  ├─ headings.py   — Detección # / ## por tamaño de fuente  │
│  └─ errors.py     — InvalidPDFError                        │
├─────────────────────────────────────────────────────────────┤
│  Config (Settings frozen dataclass + env vars)             │
│  Validators (centralizados)                                │
└─────────────────────────────────────────────────────────────┘
```

### Principios aplicados

| Principio | Implementación |
|-----------|----------------|
| **Twelve-Factor App** | Config en env vars, stateless, logs a stdout, port binding, disposability |
| **Clean Code** | Nombres descriptivos, funciones < 30 líneas, separación HTTP / lógica |
| **SOLID** | SRP (rutas/validación/extracción), OCP (Protocol), DIP (inyección) |
| **DRY/KISS/YAGNI** | Validators centralizados, sin MongoDB, sin IA, sin colas externas |
| **Resiliencia** | Bulkhead (ThreadPool + cola), Timeout, Graceful Shutdown, Fault Isolation |

---

## 🚀 Inicio Rápido

### Desarrollo local (Docker Compose)

```bash
# Construir y levantar
docker-compose up --build

# Ver logs
docker-compose logs -f pdf-extract

# Probar endpoint
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/pdf" \
  --data-binary @documento.pdf
```

### Variables de entorno (`.env`)

```bash
# Ver .env.example para lista completa
cp .env.example .env
# Editar valores según necesidad
```

| Variable | Default | Descripción |
|----------|---------|-------------|
| `APP_MAX_PDF_SIZE_BYTES` | `10485760` (10MB) | Tamaño máximo PDF |
| `APP_EXTRACT_WORKERS` | `2` | Hilos ThreadPoolExecutor |
| `APP_MAX_PENDING_EXTRACTIONS` | `100` | Capacidad cola (bulkhead) |
| `APP_EXTRACTION_TIMEOUT_SECONDS` | `30` | Timeout por extracción |
| `APP_OCR_ENABLED` | `false` | Habilita OCR (Tesseract) |
| `APP_OCR_LANGUAGES` | `eng,spa` | Idiomas Tesseract |
| `APP_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `APP_LOG_FORMAT` | `text` | `text` \| `json` |
| `PORT` | `8000` | Puerto HTTP |

---

## 📡 API Reference

### `POST /extract`
Extrae contenido como **Markdown** con headings detectados.

**Request:**
- `multipart/form-data` con campo `file` (PDF)
- **O** `application/pdf` raw body

**Response 200:**
```json
{
  "content": "# Título\n\n## Subtítulo\n\nCuerpo del documento...",
  "page_count": 3
}
```

**Errores:**
| Código | Causa |
|--------|-------|
| 400 | Archivo vacío / No es PDF válido / Falta campo `file` |
| 413 | Excede `APP_MAX_PDF_SIZE_BYTES` |
| 503 | Servicio saturado (`Retry-After: 1`) |

---

### `POST /extract/text`
Extrae **texto plano** (líneas separadas por `\n`).

**Response 200:**
```json
{
  "content": "Título\nSubtítulo\nCuerpo del documento...",
  "page_count": 3
}
```

---

### `GET /health`
Liveness probe básica.

```json
{ "status": "ok" }
```

### `GET /health/live`
Liveness probe para Kubernetes (siempre OK si proceso vivo).

```json
{ "status": "ok" }
```

### `GET /health/ready`
Readiness probe — verifica capacidad del servicio.

```json
{
  "status": "ready",
  "pending_extractions": 2,
  "max_pending_extractions": 100,
  "extraction_workers": 2,
  "queue_utilization_percent": 2.0
}
```

---

## 🐳 Docker

### Build imagen
```bash
docker build -t pdf-extract-service:latest .
```

### Run contenedor
```bash
docker run -d \
  -p 8000:8000 \
  -e APP_MAX_PDF_SIZE_BYTES=10485760 \
  -e APP_EXTRACT_WORKERS=2 \
  -e APP_OCR_ENABLED=true \
  -e APP_LOG_LEVEL=INFO \
  pdf-extract-service:latest
```

### Health check incluido
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health/live', timeout=2).raise_for_status()"
```

---

## 🧪 Testing

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# Con coverage
python -m pytest tests/ --cov=app --cov-report=term-missing

# Solo tests de integración
python -m pytest tests/test_extract.py -v

# Solo tests unitarios PDF
python -m pytest tests/test_pdf_service.py -v
```

### Fixtures disponibles (`tests/conftest.py`)
- `pdf_bytes` — PDF simple "Hola extract"
- `build_pdf` — Factory para crear PDFs con texto y tamaños de fuente
- `pdf_with_image` — PDF con texto + imagen para tests OCR

---

## 📁 Estructura del Proyecto

```
pdf-extract-service/
├── app/
│   ├── __init__.py              # Versión desde metadata
│   ├── main.py                  # FastAPI app, lifespan, wiring DI
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Settings frozen dataclass + env vars
│   ├── utils/
│   │   ├── __init__.py
│   │   └── validators.py        # Validaciones centralizadas
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── extraction.py        # Pydantic models (ExtractionResult, etc.)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── interfaces.py        # Protocol PDFExtractionService (DIP)
│   │   └── pdf_extraction_service.py  # Impl: bulkhead + timeout
│   ├── api/
│   │   ├── __init__.py
│   │   ├── exception_handlers.py # Handlers centralizados
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── extraction.py    # Endpoints HTTP
│   ├── pdf/                     # Lógica pura (sin HTTP)
│   │   ├── __init__.py
│   │   ├── extractor.py         # extract_text, extract_markdown
│   │   ├── ocr.py               # Tesseract wrapper
│   │   ├── headings.py          # Detección # / ##
│   │   └── errors.py            # InvalidPDFError
│   └── logging_config.py
├── tests/
│   ├── test_extract.py          # Integración + unitarios servicio
│   ├── test_pdf_service.py      # Extracción/OCR/headings
│   ├── test_settings.py         # Config
│   ├── test_health.py           # Health endpoints
│   ├── test_logging.py
│   └── conftest.py              # Fixtures
├── Dockerfile                   # Multi-stage, non-root, healthcheck
├── docker-compose.yml           # Desarrollo local
├── pyproject.toml               # Deps, pytest, black, mypy, coverage
├── uv.lock                      # Lockfile reproducible
├── .env.example                 # Variables documentadas
├── .gitignore
└── README.md
```

---

## 🔧 Decisiones Técnicas (ADR)

| Decisión | Justificación |
|----------|---------------|
| **Protocol + Impl** (DIP) | Permite testear con mocks, futuras estrategias (ej. OCR cloud) sin tocar routes |
| **ThreadPoolExecutor** | PyMuPDF es CPU-bound y bloqueante; async nativo no ayuda; bulkhead simple |
| **Cola acotada + 503** | Backpressure explícito; cliente/orquestador decide reintentar |
| **Timeout configurable** | Previene workers colgados indefinidamente por PDFs maliciosos/complejos |
| **Settings frozen dataclass** | Inmutabilidad, validación temprana, thread-safe |
| **Validators centralizados** | DRY, fácil testeo, single source of truth |
| **PDF core sin HTTP** | Reutilizable, testeable, sin dependencias de framework |
| **OCR como fallback silencioso** | Si Tesseract falla, continúa sin OCR (no rompe extracción) |
| **Graceful shutdown con SIGTERM** | Kubernetes/docker stop drena requests antes de matar |
| **Health live/ready separados** | Cumple patrón Kubernetes; ready refleja capacidad real |

---

## 🔗 Patrones de Resiliencia — ¿Dónde viven?

| Patrón | Implementación | Delegado a |
|--------|----------------|------------|
| **Bulkhead** | `ThreadPoolExecutor(max_workers=N)` + `_pending` counter + 503 | Servicio (este) |
| **Timeout** | `asyncio.wait_for(future, timeout=settings.extraction_timeout_seconds)` | Servicio (este) |
| **Retry + Backoff** | **No** — Extracción es determinística; reintentar PDF inválido no ayuda | **Cliente / Orquestador** |
| **Circuit Breaker** | **No** — Sin dependencias externas remotas | **Cliente / Orquestador / API Gateway** |
| **Rate Limiting** | **No** — Duplicaría control | **API Gateway** |
| **Health Checks** | `/health/live` + `/health/ready` con stats reales | Servicio (este) |
| **Graceful Shutdown** | SIGTERM/SIGINT handler + drenado 30s + pool.shutdown(wait=True) | Servicio (este) |
| **Fault Isolation** | Cada request en thread separado; excepción no rompe pool | Servicio (este) |
| **Idempotencia** | Mismo archivo + config = mismo resultado; sin side effects | Servicio (este) |

---

## 📋 Checklist de Producción

- [ ] `APP_LOG_FORMAT=json` para agregadores (ELK, Datadog)
- [ ] Límites CPU/memoria en `docker-compose.yml` / K8s
- [ ] Tesseract instalado en imagen base si `APP_OCR_ENABLED=true`
- [ ] Secrets management para variables sensibles (si las hubiere)
- [ ] Monitoreo: latency p99, queue utilization, error rate, 503 rate
- [ ] Alertas: queue_utilization > 80%, 503 rate > 1%

---

## 📚 Referencias

- Repositorio original: https://github.com/Gianluca-gitea/pdf-extractext
- Servicios hermanos (arquitectura de referencia):
  - `resumen-service`
  - `documentos-service`
  - `notificaciones-service`
  - `orquestador-service`

---

## 📄 Licencia

MIT — Ver `LICENSE` para detalles.