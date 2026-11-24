# PDF Extract Service

API que recibe un PDF y devuelve su texto en formato plano o Markdown. Usa PyMuPDF para leer el documento y puede usar Tesseract para extraer texto de las imágenes.

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

## Límites de procesamiento

Por defecto, cada proceso de la API admite hasta 100 solicitudes entre cargas, esperas y extracciones activas, y ejecuta una extracción a la vez. Al alcanzar el límite devuelve HTTP 503. La recepción del PDF tiene un plazo de 30 segundos (HTTP 408) y la extracción tiene otros 30 segundos, incluida la espera por un worker (HTTP 504). Si una extracción ya empezó cuando vence el plazo, ocupa su cupo hasta terminar.

## Despliegue con el orquestador

Cuando pasan las pruebas y la verificación del contenedor, CI publica la imagen en GHCR tras un push a `master`, con las etiquetas `latest` y el SHA completo del commit. La verificación guarda el informe de Trivy como artefacto y bloquea la publicación si encuentra vulnerabilidades de severidad alta o crítica con una corrección disponible.

En el escaneo local del 20 de noviembre de 2026, Trivy registró 134 hallazgos de severidad alta o crítica en paquetes Debian. El informe no indicaba una versión corregida para esos hallazgos.

El Compose del orquestador usa `ghcr.io/lighuen04/pdf-extract-service:latest` por defecto. Para actualizar solo el extractor, ejecutá desde el directorio del orquestador:

```sh
docker compose pull extract
docker compose up -d extract
```

Para fijar una versión, indicá la imagen con el SHA del commit en `EXTRACT_IMAGE` en el `.env` del orquestador. Si el paquete es privado, iniciá sesión con `docker login ghcr.io` usando un token clásico con permiso `read:packages` y acceso al paquete.

El servicio deriva de [`services/extract` de pdf-extractext](https://github.com/Gianluca-gitea/pdf-extractext/tree/0123464/services/extract) y se distribuye bajo la licencia [AGPL-3.0-only](LICENSE).
