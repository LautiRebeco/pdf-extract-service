
# PDF Extract Service

Microservicio HTTP en Python 3.14 y FastAPI para extraer texto y Markdown de PDFs. PyMuPDF lee el texto nativo y las fuentes. Tesseract reconoce texto en bloques de imagen cuando se habilita. El servicio procesa cada documento de forma independiente y devuelve el resultado sin persistirlo.

## Inicio rápido

Ejecutar desde la raíz del repositorio, donde están `pyproject.toml` y `Dockerfile`.

```sh
docker compose up --build --detach --wait
docker compose ps
curl -fsS http://localhost:8000/health/ready
curl -fsS -H 'Content-Type: application/pdf' --data-binary @documento.pdf http://localhost:8000/extract/text
curl -fsS -F 'file=@documento.pdf' http://localhost:8000/extract
docker compose down
```

En PowerShell, usar `curl.exe` y citar `'@documento.pdf'`. Para arrancar la misma aplicación localmente, instalar Python 3.14 y uv, luego ejecutar:

```sh
uv sync --locked
uv run --locked python -m app.server
```

La imagen multi-stage instala solo las dependencias de producción del lock, ejecuta como usuario sin privilegios e incluye Tesseract y los idiomas `eng` y `spa`. Docker comprueba `/health/live` con `urllib.request`. Compose usa la imagen sin montar el código local y asigna 1 CPU y 512 MiB al contenedor.

## API

| Ruta | Resultado |
| --- | --- |
| `POST /extract` | Markdown con encabezados inferidos a partir del tamaño de fuente. |
| `POST /extract/text` | Texto plano en orden de lectura. |
| `GET /health` y `GET /health/live` | HTTP 200 con `{"status":"ok"}`, incluso con la capacidad agotada. |
| `GET /health/ready` | HTTP 200 si hay capacidad. HTTP 503 con estado `busy`, `closing` o `unavailable` si el servicio no acepta trabajo. |

Ambos POST aceptan `multipart/form-data` con campo `file` y un cuerpo binario `application/pdf`. La respuesta exitosa conserva `{"content":"…","page_count":1}`. Un documento vacío de contenido puede devolver `content: ""` con su número de páginas.

| HTTP | Condición |
| --- | --- |
| 400 | Archivo vacío, formulario inválido o sin `file`, firma incorrecta o documento que PyMuPDF no puede leer, incluido un PDF que necesita contraseña. |
| 413 | PDF demasiado grande o cuerpo multipart por encima del presupuesto. |
| 503 | Capacidad agotada, pool indisponible o cierre. Incluye `Retry-After: 1` en los POST. |
| 504 | Se agotó la espera de extracción, incluida la cola. |
| 500 | Fallo interno u OCR fallido sin texto recuperable. Si hay texto recuperable, se conserva el resultado parcial y se registra el fallo. |

Readiness informa `pending_extractions`, `max_pending_extractions`, `extraction_workers`, `queue_utilization_percent` y `closing`. El total pendiente incluye recepciones, cola y trabajos en ejecución. La liveness se mantiene independiente del pool.

## Configuración

Copiar `.env.example` a `.env` si se quieren personalizar valores. Las variables de entorno tienen prioridad sobre el archivo local.

| Variable | Valor por defecto | Uso |
| --- | --- | --- |
| `APP_NAME` | `PDF Extractext Extract` local, `PDF Extract Service` en Compose | Título en OpenAPI. |
| `APP_MAX_PDF_SIZE_BYTES` | `10485760` | Máximo por PDF. Multipart permite hasta 1 MiB adicional para el cuerpo completo. |
| `APP_EXTRACT_WORKERS` | `1` | Máximo de extracciones activas por proceso de API, acotado también por el total pendiente. |
| `APP_MAX_PENDING_EXTRACTIONS` | `100` en la aplicación, `16` en Compose y en el ejemplo | Máximo total por proceso, incluidas las cargas en curso. |
| `APP_EXTRACTION_TIMEOUT_SECONDS` | `30` | Espera HTTP de procesamiento tras la recepción del PDF, incluida la cola. |
| `APP_SHUTDOWN_TIMEOUT_SECONDS` | `30` | Presupuesto de Uvicorn para drenar solicitudes y, por separado, del lifespan para esperar trabajos activos. |
| `APP_OCR_ENABLED` | `false` | Habilita OCR de imágenes. |
| `APP_OCR_LANGUAGES` | `eng+spa` | Acepta `eng,spa` y `eng+spa`. Tesseract recibe la forma con `+`. |
| `APP_LOG_LEVEL` | `INFO` | Nivel de logs. |
| `APP_LOG_FORMAT` | `text` | `text` o `json` por línea, en stdout con el arranque recomendado. |
| `PORT` | `8000` | Puerto de escucha de `app.server`. En Compose controla el puerto publicado del host. |

## Arquitectura y resiliencia

| Capa | Responsabilidad |
| --- | --- |
| `app/api/` | HTTP, admisión antes de leer el cuerpo, DI, probes y traducción de excepciones. |
| `app/services/` | Bulkhead, espera de workers, timeout y apagado. |
| `app/pdf/` | Validación estructural, extracción, detección de títulos y OCR. |
| `app/config/`, `app/utils/`, `app/schemas/` | Configuración, lectura acotada y contratos de datos. |

- **Bulkhead y backpressure.** FastAPI crea una instancia en el lifespan y la comparte por `app.state` entre ambas rutas y readiness. El límite se reserva antes de leer el cuerpo. El trabajo espera en el loop de la API y solo se envía al pool cuando hay un worker libre.
- **Timeout y cancelación.** Una recepción cancelada o un trabajo que vence en cola devuelve su cupo. Si la extracción ya está en marcha, el 504 finaliza la espera HTTP y el cupo se devuelve cuando concluye el trabajo. Cada invocación de Tesseract tiene además un límite de 10 segundos por bloque.
- **Aislamiento.** Con un worker se usa un hilo dedicado. Con varios se usan procesos para mantener PyMuPDF en un único hilo por proceso. Una excepción de un documento se devuelve al solicitante y el pool sigue disponible. Si se rompe el pool de procesos, readiness pasa a `unavailable` y la instancia necesita reiniciarse. [Guía de PyMuPDF sobre concurrencia](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html)
- **Cierre.** Uvicorn maneja las señales y drena las solicitudes. Al iniciar el cierre del lifespan, el servicio rechaza nuevos trabajos y despierta la cola con 503. Espera hasta el presupuesto configurado y cierra el executor. Si quedan workers de procesos, solicita su terminación. En modo de un hilo, el lifespan devuelve el control al vencer el plazo, pero el intérprete puede esperar a que termine el hilo nativo. El supervisor debe aplicar un plazo de terminación externo. Ajustar `stop_grace_period` si se cambia el presupuesto de apagado. [API de concurrencia de Python 3.14](https://docs.python.org/3.14/library/concurrent.futures.html)
- **Memoria.** El límite se comprueba al recibir los bytes, incluso sin `Content-Length`. Multipart conserva el spool temporal de Starlette y aplica presupuestos al cuerpo y al archivo. Esa validación limita la entrada comprimida. Un PDF pequeño aún puede expandirse considerablemente durante la extracción. Dimensionar la cola, el tamaño máximo y los workers junto con la RAM y la CPU disponibles.
- **Coordinación externa.** El gateway controla tamaño total del cuerpo, tiempo de subida, conexiones y rate limiting por consumidor. El orquestador decide reintentos acotados con backoff y jitter respetando `Retry-After`, configura su circuit breaker y evita reintentar 400 o 413. Un 504 puede dejar una extracción activa, por lo que conviene contabilizar ese costo al reintentar. La extracción no depende de APIs remotas.

Si se necesitara detener estrictamente un único trabajo al vencer el HTTP, sería necesario ejecutarlo en un proceso cancelable individualmente y manejar también sus descendientes, como Tesseract. Terminar el pool completo en cada 504 interrumpiría otros documentos. El servicio conserva el cupo y limita la cantidad de trabajos activos.

## Twelve-Factor App

| Factor | Aplicación |
| --- | --- |
| I. Base de código | Un repositorio Git para el servicio, con cambios verificados por CI. |
| II. Dependencias | `pyproject.toml` y `uv.lock` declaran y fijan paquetes Python. La imagen declara los paquetes del sistema. |
| III. Configuración | Entorno en ejecución y `.env.example` como referencia local. |
| IV. Servicios de respaldo | La extracción usa bibliotecas y un ejecutable local. No requiere backing services. |
| V. Build, release, run | Imagen construida a partir del lock, configuración al liberar y arranque con `app.server`. El etiquetado y la promoción quedan en el despliegue. |
| VI. Procesos | Estado transitorio por proceso. No hay base de datos ni almacenamiento persistente de PDFs. |
| VII. Puerto | La aplicación expone HTTP en `PORT`. |
| VIII. Concurrencia | Workers y admisión acotados por instancia. Las réplicas escalan horizontalmente y multiplican la capacidad total. |
| IX. Desechabilidad | Inicio mediante lifespan y drenaje con plazo. Un hilo bloqueado requiere el límite del supervisor. |
| X. Paridad | Mismo comando y lock en desarrollo y producción. CI instala ambos idiomas y comprueba la imagen de producción. |
| XI. Logs | Eventos y accesos en stdout con formato de texto o JSON. La plataforma los recolecta. |
| XII. Procesos administrativos | Sin migraciones ni tareas de administración de datos. Las pruebas y diagnósticos se ejecutan por separado. |

## Decisiones de diseño

- **SRP e ISP.** Las rutas manejan HTTP y consumen un protocolo con extracción y estadísticas. El lifespan conserva la responsabilidad del cierre.
- **DIP y LSP.** Las rutas dependen del protocolo, con una implementación inyectada por FastAPI. Una implementación de prueba puede sustituirla si respeta los resultados y errores esperados.
- **OCP.** El servicio aplica la misma admisión y el mismo timeout a las funciones de texto y Markdown. Las estrategias del núcleo se pueden ampliar sin duplicar la gestión de capacidad.
- **Clean Code y DRY.** Una apertura validada y un recorrido común de bloques respaldan ambos formatos. Los errores de dominio separan PDF inválido, saturación y timeout.
- **KISS y YAGNI.** El camino habitual usa un hilo y la cola vive en la API. Los procesos se usan cuando se configura paralelismo y el orquestador maneja reintentos y circuit breaker.

## Pruebas y evidencia

```sh
uv run --locked python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --locked python -m mypy app
uv run --locked python -m flake8 --jobs=1 app tests --select E9,F63,F7,F82
```

La línea base pasó 54 pruebas antes de la refactorización. Las nuevas regresiones comprobaron que la saturación era invisible para readiness, que los trabajos en cola seguían esperando durante el cierre y que el OCR fallido sin texto se devolvía como éxito. Las pruebas actuales incluyen concurrencia HTTP, 503 y `Retry-After`, timeout, cancelación, cierre, PDFs corruptos, cargas binarias y multipart por encima del límite, encabezados Markdown, logs JSON y OCR real. La integración OCR se salta si falta Tesseract o alguno de los idiomas solicitados. El workflow de GitHub Actions ejecuta pytest con cobertura mínima del 90 %, análisis estático, build de Docker y verificación de salud.

Verificación local en Windows con Python 3.14.3

- 79 pruebas pasaron, 1 quedó omitida y la cobertura fue 95,88 %. La omisión corresponde al OCR bilingüe porque la instalación local solo tenía `eng`. Starlette emitió una advertencia sobre el uso de `httpx` en `TestClient`.
- mypy 1.19.1 revisó 24 archivos de aplicación y Flake8 pasó los controles de sintaxis y errores configurados en CI.
- En Docker, la imagen quedó `healthy` y las tres rutas de salud devolvieron 200 en reposo. Una prueba HTTP con dos workers extrajo `HELLO WORLD` de un PDF de imagen usando `eng+spa`, con logs JSON y un usuario sin privilegios.

## Para la exposición universitaria

1. Mostrar dos solicitudes que comparten la misma capacidad y una tercera que recibe 503 con `Retry-After`. Mientras tanto, liveness devuelve 200 y readiness devuelve 503.
2. Explicar el 504 usando un trabajo activo que sigue ocupando un cupo. La señal de finalización del worker, separada del timeout HTTP, habilita el siguiente trabajo.
3. Enviar el mismo PDF a ambas rutas para comparar texto plano y Markdown. Activar OCR para mostrar la extracción desde un PDF de imagen.
4. Cerrar la instancia y explicar los plazos de Uvicorn, del lifespan y del supervisor. Relacionar cada plazo con la recepción HTTP, la ejecución nativa y el ciclo de vida del contenedor.
