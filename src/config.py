from __future__ import annotations

import os

from PyQt6.QtCore import QSettings


APP_ORGANIZATION = "AmazonBoard"
APP_NAME = "Amazons"


def create_settings() -> QSettings:
    """Create persistent settings, with an isolated file override for tests."""
    settings_file = os.environ.get("AMAZONS_SETTINGS_FILE")
    if settings_file:
        return QSettings(settings_file, QSettings.Format.IniFormat)
    return QSettings(APP_ORGANIZATION, APP_NAME)
