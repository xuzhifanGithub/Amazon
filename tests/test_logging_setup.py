import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import src.logging_setup as logging_setup


def _remove_test_handler(path: Path) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if (isinstance(handler, RotatingFileHandler)
                and Path(handler.baseFilename) == path):
            root.removeHandler(handler)
            handler.close()


def test_configure_logging_clears_previous_run_files(tmp_path, monkeypatch):
    path = tmp_path / "amazons.log"
    path.write_text("上一轮主日志", encoding="utf-8")
    for index in range(1, 4):
        Path(f"{path}.{index}").write_text(
            f"上一轮备份 {index}", encoding="utf-8")
    monkeypatch.setattr(logging_setup, "log_file_path", lambda: path)

    try:
        assert logging_setup.configure_logging() == path
        assert path.read_text(encoding="utf-8") == ""
        assert not any(Path(f"{path}.{index}").exists() for index in range(1, 4))
    finally:
        _remove_test_handler(path)


def test_repeated_configuration_keeps_current_run_log(tmp_path, monkeypatch):
    path = tmp_path / "amazons.log"
    monkeypatch.setattr(logging_setup, "log_file_path", lambda: path)

    try:
        logging_setup.configure_logging()
        logging.getLogger("test.current_run").info("本次运行日志")
        for handler in logging.getLogger().handlers:
            handler.flush()

        logging_setup.configure_logging()

        assert "本次运行日志" in path.read_text(encoding="utf-8")
    finally:
        _remove_test_handler(path)
