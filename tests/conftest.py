import os
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "AMAZONS_SETTINGS_FILE",
    os.path.join(tempfile.gettempdir(), f"amazons-tests-{os.getpid()}.ini"),
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
