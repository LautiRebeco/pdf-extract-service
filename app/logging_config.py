import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, log_format: str = "text") -> None:
    root = logging.getLogger()
    handler = next((item for item in root.handlers if item.name == "pdf-extract-stdout"), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name("pdf-extract-stdout")
        root.addHandler(handler)
    formatter = (
        JsonFormatter()
        if log_format == "json"
        else logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    handler.setFormatter(formatter)
    root.setLevel(level)
