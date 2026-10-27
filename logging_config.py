"""
Logging configuration module for GNPC webcam system.
Handles environment-based logging setup for console or file output.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from paths import resolve_path


def setup_logging():
    """Configure logging based on environment variables."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_output = os.getenv("LOG_OUTPUT", "console").lower()
    log_file = os.getenv("LOG_FILE", "webcams.log")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", 3))

    if log_output == "file":
        handler = RotatingFileHandler(
            resolve_path(log_file), maxBytes=max_bytes, backupCount=backup_count
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logging.basicConfig(
            level=getattr(logging, log_level), handlers=[handler], force=True
        )
    else:
        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            force=True,
        )


class StatusNoteFilter(logging.Filter):
    """Append a camera's status note to the warnings and errors it logs.

    Each camera runs in a thread named after it, so the record's thread says
    which camera it came from, even when it was logged by shared code like the
    overlays that never sees the camera's name.
    """

    def __init__(self, notes):
        super().__init__()
        self.notes = notes

    def filter(self, record):
        note = self.notes.get(record.threadName)
        # A record passes every handler's filter, so tag it only once.
        if (
            note
            and record.levelno >= logging.WARNING
            and not hasattr(record, "status_note")
        ):
            record.msg = f"{record.getMessage()} [known issue: {note}]"
            record.args = None
            record.status_note = note
        return True


def install_status_notes(notes):
    """Tag each noted camera's warnings and errors on every root handler."""
    for handler in logging.root.handlers:
        for old in [f for f in handler.filters if isinstance(f, StatusNoteFilter)]:
            handler.removeFilter(old)
        handler.addFilter(StatusNoteFilter(notes))
