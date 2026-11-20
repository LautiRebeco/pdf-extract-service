import importlib
import logging
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
APP_MODULES = [
    ".".join(path.relative_to(APP_DIR.parent).with_suffix("").parts)
    for path in sorted(APP_DIR.rglob("*.py"))
]


@pytest.mark.parametrize("module_name", APP_MODULES)
def test_module_logger_inherits_level_from_root(module_name) -> None:
    importlib.import_module(module_name)

    assert logging.getLogger(module_name).level == logging.NOTSET


def test_configure_logging_sets_root_level(monkeypatch) -> None:
    from app.logging_config import configure_logging

    root = logging.getLogger()
    monkeypatch.setattr(root, "level", root.level)

    configure_logging("WARNING")

    assert root.level == logging.WARNING


def test_json_logging_emits_one_record_to_stdout(monkeypatch, capsys):
    import json

    from app.logging_config import configure_logging

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", root.handlers.copy())
    monkeypatch.setattr(root, "level", root.level)
    for handler in root.handlers[:]:
        if handler.name == "pdf-extract-stdout":
            root.removeHandler(handler)

    configure_logging("INFO", "json")
    configure_logging("INFO", "json")
    logging.getLogger("uvicorn.access").info("Solicitud %s", "PDF")
    payload = json.loads(capsys.readouterr().out)
    assert payload["message"] == "Solicitud PDF"
    assert payload["logger"] == "uvicorn.access"
    assert payload["level"] == "INFO"
    assert payload["timestamp"].endswith("+00:00")
