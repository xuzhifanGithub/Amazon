"""Application logging with a bounded, user-accessible diagnostics file."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def log_file_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmazonBoard" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "amazons.log"


def configure_logging() -> Path:
    root = logging.getLogger()
    path = log_file_path()
    if any(isinstance(handler, RotatingFileHandler)
           and Path(handler.baseFilename) == path for handler in root.handlers):
        return path
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    return path
