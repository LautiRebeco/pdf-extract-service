# PDF Extract Service

Este servicio recibe un PDF y devuelve su texto en formato plano o Markdown. Usa PyMuPDF para leer el documento y, si activás el OCR, Tesseract para leer texto de las imágenes. El extractor devuelve el resultado en la misma respuesta y funciona sin base de datos propia.

## Repositorios del proyecto

- [Extractor](https://github.com/LautiRebeco/pdf-extract-service) — código de este servicio.
- [Orquestador](https://github.com/LautiRebeco/pdf-extract-orchestrator) — coordina el despliegue y configura Traefik como puerta de entrada a la API.
- [GUI](https://github.com/LautiRebeco/pdf-gui) — interfaz para trabajar con los PDFs y ver el texto extraído.
- [Documents](https://github.com/LautiRebeco/pdf-documents-service) — almacena los PDFs.

## Puesta en marcha

Ejecutá los comandos desde el directorio que contiene el `Dockerfile`.

```sh
docker build -t pdf-extract-service .
docker run --rm --init --name pdf-extract -p 8000:8000 pdf-extract-service
```

Para desarrollo local, con Python 3.14 y uv:

```sh
uv sync --locked
uv run --locked python -m app.server
```

El servicio escucha en el puerto 8000 por defecto. Podés copiar [`.env.example`](.env.example) a `.env` y ajustar los valores. Con Docker, pasá el archivo con `--env-file .env` y ajustá el mapeo de puertos si cambiás `PORT`.

El OCR está desactivado por defecto. Para habilitarlo, configurá `APP_OCR_ENABLED=true`. La imagen Docker ya trae Tesseract con inglés y español. Si ejecutás el servicio localmente, instalá Tesseract y los idiomas configurados en `APP_OCR_LANGUAGES`.

## API

| Ruta | Qué devuelve |
| --- | --- |
| `POST /extract` | Markdown con encabezados inferidos a partir del tamaño de fuente. |
| `POST /extract/text` | Texto plano en orden de lectura. |
| `GET /health` y `GET /health/live` | `{"status":"ok"}` si la API responde. |
| `GET /health/ready` | Estado y capacidad de la cola. Devuelve HTTP 503 si el servicio no puede aceptar otro trabajo. |

Las dos rutas de extracción aceptan el PDF como cuerpo `application/pdf` o como formulario multipart en el campo `file`. Devuelven un JSON con `content` y `page_count`. El límite por defecto es de 10 MiB por PDF.

```sh
curl -fsS -H 'Content-Type: application/pdf' --data-binary '@documento.pdf' http://localhost:8000/extract/text
curl -fsS -F 'file=@documento.pdf' http://localhost:8000/extract
```

La conversión a Markdown no reconstruye tablas ni diseños complejos. Si falla el OCR de alguna imagen, la API devuelve el texto que pudo recuperar. Si hubo un fallo de OCR y no se recuperó texto, devuelve HTTP 500.

## Límites y configuración

| Variable | Por defecto | Qué controla |
| --- | --- | --- |
| `APP_MAX_PDF_SIZE_BYTES` | 10 MiB | Tamaño máximo del PDF (HTTP 413 al superarlo). |
| `APP_MAX_PENDING_EXTRACTIONS` | 100 | Solicitudes por proceso, incluidas las que están subiendo el PDF, esperando o en extracción (HTTP 503 al llenarse). |
| `APP_EXTRACT_WORKERS` | 1 | Extracciones que pueden ejecutarse en paralelo por proceso. |
| `APP_UPLOAD_TIMEOUT_SECONDS` | 30 s | Tiempo para recibir el PDF (HTTP 408). |
| `APP_EXTRACTION_TIMEOUT_SECONDS` | 30 s | Tiempo de extracción, incluida la espera por un worker (HTTP 504). |

Si vence el plazo mientras una extracción está en curso, esa solicitud sigue ocupando un cupo hasta que termina el trabajo.

## Pruebas

```sh
uv run --locked python -m pytest
```

## Despliegue con el orquestador

Para actualizar el extractor, ejecutá estos comandos desde el directorio del orquestador.

```sh
docker compose pull extract
docker compose up -d extract
```

Si la imagen es privada, iniciá sesión primero con `docker login ghcr.io` usando un token clásico con permiso `read:packages` y acceso al paquete.

## Licencia

El servicio deriva de [`services/extract` de pdf-extractext](https://github.com/Gianluca-gitea/pdf-extractext/tree/0123464/services/extract) y se distribuye bajo la licencia [AGPL-3.0-only](LICENSE).
