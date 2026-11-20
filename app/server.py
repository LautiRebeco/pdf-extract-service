import os

import uvicorn
from dotenv import load_dotenv

from app.settings import get_settings
from app.logging_config import configure_logging


def main() -> None:
    load_dotenv()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_config=None,
        timeout_graceful_shutdown=settings.shutdown_timeout_seconds,
    )


if __name__ == "__main__":
    main()
