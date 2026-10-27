"""Unit tests for logging setup and rotation configuration."""

import logging
from logging.handlers import RotatingFileHandler

from logging_config import setup_logging


def _teardown_root_handlers():
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)


def test_file_output_uses_rotating_handler(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_OUTPUT", "file")
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "test.log"))
    monkeypatch.setenv("LOG_MAX_BYTES", "1000")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "2")

    setup_logging()
    try:
        handlers = [
            h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(handlers) == 1
        assert handlers[0].maxBytes == 1000
        assert handlers[0].backupCount == 2
    finally:
        _teardown_root_handlers()


def test_rotation_caps_log_size(monkeypatch, tmp_path):
    log_file = tmp_path / "rotate.log"
    monkeypatch.setenv("LOG_OUTPUT", "file")
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_MAX_BYTES", "500")
    monkeypatch.setenv("LOG_BACKUP_COUNT", "2")
    # environment.env may set a quieter level, and importing main loads it
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    setup_logging()
    try:
        logger = logging.getLogger("rotation-test")
        for i in range(100):
            logger.info("filler line %d to push the file over the size limit", i)

        assert log_file.stat().st_size <= 500
        assert (tmp_path / "rotate.log.1").exists()
    finally:
        _teardown_root_handlers()


def test_status_note_tags_a_noted_cameras_warnings_once(monkeypatch, tmp_path):
    import threading

    from logging_config import install_status_notes

    log_file = tmp_path / "notes.log"
    monkeypatch.setenv("LOG_OUTPUT", "file")
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    setup_logging()
    # A second handler sees the same record; the note must still appear once.
    logging.root.addHandler(logging.FileHandler(tmp_path / "second.log"))
    try:
        install_status_notes({"noted": "Sensor offline"})
        logger = logging.getLogger("status-note-test")

        def log_all():
            logger.info("info from %s", threading.current_thread().name)
            logger.warning("warning from %s", threading.current_thread().name)

        for name in ("noted", "quiet"):
            thread = threading.Thread(name=name, target=log_all)
            thread.start()
            thread.join()

        for path in (log_file, tmp_path / "second.log"):
            lines = path.read_text().splitlines()
            assert sum("[known issue: Sensor offline]" in line for line in lines) == 1
            tagged = next(line for line in lines if "known issue" in line)
            assert "warning from noted" in tagged
    finally:
        _teardown_root_handlers()
