"""Application logging with a bounded, user-accessible diagnostics file."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


_MAX_LOG_BYTES = 1_000_000
_BACKUP_COUNT = 3


def log_file_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmazonBoard" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "amazons.log"


def _clear_previous_logs(path: Path) -> None:
    """Clear diagnostics left by previous application runs."""
    path.write_text("", encoding="utf-8")
    for index in range(1, _BACKUP_COUNT + 1):
        backup = Path(f"{path}.{index}")
        try:
            backup.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # A stale backup may briefly be held by antivirus or another
            # process; failure to remove it must not prevent the app starting.
            continue


def configure_logging() -> Path:
    root = logging.getLogger()
    path = log_file_path()
    if any(isinstance(handler, RotatingFileHandler)
           and Path(handler.baseFilename) == path for handler in root.handlers):
        return path
    _clear_previous_logs(path)
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        path, maxBytes=_MAX_LOG_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    return path
