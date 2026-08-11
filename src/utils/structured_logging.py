"""Structured logging infrastructure using structlog.

Provides:
- init_structlog(): configures structlog with JSON or console renderer
- get_logger(name): factory that returns a configured structlog logger
- LoggerMock: test double that captures log calls without side effects

Environment variables:
- BENSYNE_ENV: "production" for JSON renderer, anything else (or unset) for console
- BENSYNE_LOG_LEVEL: log level (default: "info")
- BENSYNE_LOG_FILE: path to JSONL log file with rotation (default:
  ~/.local/share/bensyne/logs/bensyne.jsonl, rotation 10 MB, 5 backups)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import (
    add_log_level,
    TimeStamper,
    StackInfoRenderer,
)
from structlog.stdlib import (
    add_logger_name,
    filter_by_level,
    PositionalArgumentsFormatter,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rotation: 10 MB per file, keep 5 backups
_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5

# Default log file path
_DEFAULT_LOG_FILE = os.path.expanduser("~/.local/share/bensyne/logs/bensyne.jsonl")

# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------

def _get_env(env_var: str, default: str) -> str:
    """Read an environment variable with a fallback default."""
    return os.environ.get(env_var, default)


def _get_log_level() -> int:
    """Return the stdlib logging level from BENSYNE_LOG_LEVEL (default INFO)."""
    level_str = _get_env("BENSYNE_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_str, logging.INFO)
    if not isinstance(level, int):
        return logging.INFO
    return level


def _is_production() -> bool:
    """Check if running in production environment."""
    return _get_env("BENSYNE_ENV", "development") == "production"


def _get_log_file() -> str:
    """Return the log file path from BENSYNE_LOG_FILE (default: ~/.local/share/bensyne/logs/bensyne.jsonl)."""
    return _get_env("BENSYNE_LOG_FILE", _DEFAULT_LOG_FILE)


def _setup_jsonl_file_handler(log_file: str, level: int) -> logging.handlers.RotatingFileHandler:
    """Create a RotatingFileHandler for JSONL log output.

    Writes one JSON object per line (JSONL format). Rotation: 10 MB max,
    5 backups retained.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def init_structlog() -> None:
    """Configure structlog globally.

    - Production (BENSYNE_ENV=production): JSON renderer for machine-parsable output.
    - Development / default: Console renderer with colors for human readability.

    Additionally, a RotatingFileHandler writes JSONL log lines to the file
    specified by BENSYNE_LOG_FILE (default: ~/.local/share/bensyne/logs/bensyne.jsonl).
    Rotation: 10 MB max, 5 backups.

    Context propagation is handled via structlog's bind/unbind mechanism.
    Each logger obtained via get_logger() supports .bind(key=value) to add
    context fields (e.g. request_id, memory_bank) that propagate to all
    subsequent log entries from that logger instance.
    """
    level = _get_log_level()
    log_file = _get_log_file()

    # Configure stdlib logging so structlog can wrap it
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()

    # Console handler — always on
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # JSONL file handler — always on (with rotation)
    json_file_handler = _setup_jsonl_file_handler(log_file, level)
    root_logger.addHandler(json_file_handler)

    processors: list[Any]

    if _is_production():
        # JSON renderer for production — machine-parsable
        processors = [
            filter_by_level,
            add_log_level,
            add_logger_name,
            StackInfoRenderer(),
            PositionalArgumentsFormatter(),
            TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console renderer for development — human-readable
        processors = [
            filter_by_level,
            add_log_level,
            add_logger_name,
            StackInfoRenderer(),
            PositionalArgumentsFormatter(),
            TimeStamper(fmt="iso"),
            ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set up a dedicated file logger with JSONRenderer for JSONL output.
    # This stdlib logger has its own handler and is wrapped by structlog
    # with JSONRenderer so the file always gets valid JSONL regardless of
    # whether the console uses ConsoleRenderer or JSONRenderer.
    file_logger = logging.getLogger("bensyne.file")
    file_logger.handlers.clear()  # Clear on re-init to avoid handler accumulation
    file_logger.setLevel(level)
    file_logger.addHandler(json_file_handler)
    file_logger.propagate = False

    # Wrap the file logger with structlog using JSONRenderer
    file_processors: list[Any] = [
        filter_by_level,
        add_log_level,
        add_logger_name,
        StackInfoRenderer(),
        PositionalArgumentsFormatter(),
        TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
    wrapped_file_logger = structlog.wrap_logger(
        file_logger,
        processors=file_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    global _FILE_LOGGER
    _FILE_LOGGER = wrapped_file_logger


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

_FILE_LOGGER: Any = None

def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger for the given module.

    Args:
        name: Module name for the logger. Defaults to the caller's module.

    Returns:
        A FilteringBoundLogger that supports .bind(), .unbind(), and standard
        log methods (debug, info, warning, error, critical).

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("starting", request_id="abc")
        >>> bound = logger.bind(memory_bank="bank-1")
        >>> bound.info("processing")  # includes memory_bank in context
    """
    return structlog.get_logger(name)


def get_file_logger() -> Any:
    """Return the JSONL file logger for structured file logging.

    This logger writes JSON lines to the file configured by BENSYNE_LOG_FILE
    with rotation (10 MB max, 5 backups). Use it for persistent structured
    logging from services.

    Returns:
        A structlog BoundLogger that writes JSONL to the configured log file.
        Returns None if init_structlog() has not been called yet.

    Example:
        >>> file_logger = get_file_logger()
        >>> file_logger.info("file created", file_id="f1", method="create_file")
    """
    return _FILE_LOGGER


# ---------------------------------------------------------------------------
# Logger mock for unit tests
# ---------------------------------------------------------------------------

class LoggerMock:
    """A logger mock that captures log calls without side effects.

    Useful for unit tests where you want to verify that logging happened
    without actually writing to stdout, stderr, or files.

    Supports the same interface as a structlog BoundLogger:
    - debug/info/warning/error/critical(event, **kwargs)
    - bind(**kwargs) -> LoggerMock
    - unbind(*keys) -> LoggerMock
    - clear()

    Example:
        >>> mock = LoggerMock()
        >>> mock.info("hello", user="alice")
        >>> assert mock.entries[0]["event"] == "hello"
        >>> assert mock.entries[0]["user"] == "alice"
    """

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self._context = dict(context) if context else {}
        self.entries: list[dict[str, Any]] = []

    def _log(self, level: str, event: str, **kwargs: Any) -> None:
        """Record a log entry without any I/O."""
        entry: dict[str, Any] = {
            "level": level,
            "event": event,
        }
        entry.update(self._context)
        entry.update(kwargs)
        self.entries.append(entry)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log("debug", event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._log("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log("warning", event, **kwargs)

    def warn(self, event: str, **kwargs: Any) -> None:
        self._log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log("error", event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._log("critical", event, **kwargs)

    def bind(self, **context: Any) -> LoggerMock:
        """Return a new LoggerMock with additional context fields.

        The new instance shares the same entries list (so captured log calls
        are visible from both the parent and the bound instance).
        """
        new_context = dict(self._context)
        new_context.update(context)
        new_mock = LoggerMock(context=new_context)
        new_mock.entries = self.entries  # Share the entries list
        return new_mock

    def unbind(self, *keys: str) -> LoggerMock:
        """Return a new LoggerMock with specified context fields removed."""
        new_context = dict(self._context)
        for key in keys:
            new_context.pop(key, None)
        return LoggerMock(context=new_context)

    def clear(self) -> None:
        """Clear all captured entries."""
        self.entries.clear()
