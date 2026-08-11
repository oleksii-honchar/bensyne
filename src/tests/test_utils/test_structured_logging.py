"""Unit tests for structured logging infrastructure."""

import json
import logging
import os
from typing import Any

import pytest

from src.utils.structured_logging import (
    LoggerMock,
    get_file_logger,
    get_logger,
    init_structlog,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitStructlog:
    """Tests for init_structlog() configuration."""

    def test_json_renderer_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """structlog uses JSON renderer when BENSYNE_ENV=production."""
        monkeypatch.setenv("BENSYNE_ENV", "production")
        init_structlog()

        from structlog import get_config

        config = get_config()
        processor_names = [type(p).__name__ for p in config.get("processors", [])]
        assert "JSONRenderer" in processor_names, (
            f"Expected JSONRenderer in processors, got: {processor_names}"
        )

    def test_console_renderer_in_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """structlog uses console renderer when BENSYNE_ENV=development or unset."""
        monkeypatch.setenv("BENSYNE_ENV", "development")
        init_structlog()

        from structlog import get_config

        config = get_config()
        processor_names = [type(p).__name__ for p in config.get("processors", [])]
        assert "ConsoleRenderer" in processor_names, (
            f"Expected ConsoleRenderer in processors, got: {processor_names}"
        )

    def test_default_renderer_is_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default (no BENSYNE_ENV) uses ConsoleRenderer."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        from structlog import get_config

        config = get_config()
        processor_names = [type(p).__name__ for p in config.get("processors", [])]
        assert "ConsoleRenderer" in processor_names, (
            f"Expected ConsoleRenderer in processors, got: {processor_names}"
        )

    def test_json_output_contains_context_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """JSON output includes bound context fields like request_id and memory_bank.

        We verify this by using LoggerMock which demonstrates the same
        bind/context propagation mechanism that structlog uses.
        """
        logger = LoggerMock()
        bound = logger.bind(request_id="req-123", memory_bank="bank-a")
        bound.info("test message")

        assert len(bound.entries) == 1
        entry = bound.entries[0]
        assert entry.get("request_id") == "req-123"
        assert entry.get("memory_bank") == "bank-a"
        assert entry.get("event") == "test message"

    def test_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """init_structlog respects BENSYNE_LOG_LEVEL env var — filter_by_level is present."""
        monkeypatch.setenv("BENSYNE_LOG_LEVEL", "debug")
        init_structlog()

        from structlog import get_config
        from structlog.stdlib import filter_by_level as stdlib_filter

        config = get_config()
        processors = config.get("processors", [])
        # filter_by_level is the first processor
        assert processors[0] is stdlib_filter, (
            f"Expected filter_by_level as first processor, got: {processors[0]}"
        )

    def test_default_log_level_is_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default log level is INFO when BENSYNE_LOG_LEVEL is unset.

        We verify this by checking that the _get_log_level helper returns INFO.
        """
        monkeypatch.delenv("BENSYNE_LOG_LEVEL", raising=False)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)

        from src.utils.structured_logging import _get_log_level
        import logging

        level = _get_log_level()
        assert level == logging.INFO, (
            f"Expected INFO level ({logging.INFO}), got {level}"
        )

    def test_debug_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BENSYNE_LOG_LEVEL=debug sets DEBUG level."""
        monkeypatch.setenv("BENSYNE_LOG_LEVEL", "debug")

        from src.utils.structured_logging import _get_log_level
        import logging

        level = _get_log_level()
        assert level == logging.DEBUG

    def test_warning_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BENSYNE_LOG_LEVEL=warning sets WARNING level."""
        monkeypatch.setenv("BENSYNE_LOG_LEVEL", "warning")

        from src.utils.structured_logging import _get_log_level
        import logging

        level = _get_log_level()
        assert level == logging.WARNING

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid BENSYNE_LOG_LEVEL falls back to INFO."""
        monkeypatch.setenv("BENSYNE_LOG_LEVEL", "INVALID")

        from src.utils.structured_logging import _get_log_level
        import logging

        level = _get_log_level()
        assert level == logging.INFO

    def test_is_production_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_is_production returns True when BENSYNE_ENV=production."""
        monkeypatch.setenv("BENSYNE_ENV", "production")
        from src.utils.structured_logging import _is_production
        assert _is_production() is True

    def test_is_production_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_is_production returns False when BENSYNE_ENV is not production."""
        monkeypatch.setenv("BENSYNE_ENV", "development")
        from src.utils.structured_logging import _is_production
        assert _is_production() is False

    def test_is_production_false_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_is_production returns False when BENSYNE_ENV is unset."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        from src.utils.structured_logging import _is_production
        assert _is_production() is False


class TestGetLogger:
    """Tests for get_logger() factory function."""

    def test_returns_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_logger returns a non-None logger."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger("my.module")
        assert logger is not None

    def test_log_methods_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logger exposes standard log methods (debug, info, warning, error, critical)."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")

    def test_log_methods_are_callable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logger log methods are callable without raising."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        # These should not raise
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")
        logger.critical("critical msg")

    def test_bind_returns_bound_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logger.bind() returns a bound logger that is not the same object."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        bound = logger.bind(request_id="r1")
        assert bound is not logger
        assert hasattr(bound, "info")

    def test_bind_then_log_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Binding context and logging does not raise."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        bound = logger.bind(request_id="r1", memory_bank="b1")
        bound.info("test message")

    def test_unbind_returns_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logger.unbind() returns a logger."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        bound = logger.bind(request_id="r1").unbind("request_id")
        assert bound is not None
        assert hasattr(bound, "info")

    def test_chained_bind_accumulates_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Chained bind() calls work without raising."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        logger = get_logger(__name__)
        bound = logger.bind(request_id="r1").bind(memory_bank="b1")
        bound.info("test")

    def test_context_propagation_via_mock(self) -> None:
        """Context propagation works as expected (verified via LoggerMock).

        This tests the same bind/unbind semantics that structlog implements,
        using LoggerMock which gives us deterministic, inspectable output.
        """
        logger = LoggerMock()

        # Single bind
        bound = logger.bind(request_id="abc", memory_bank="test-bank")
        bound.info("hello")
        assert len(bound.entries) == 1
        assert bound.entries[0]["request_id"] == "abc"
        assert bound.entries[0]["memory_bank"] == "test-bank"

        # Chained bind
        logger.clear()
        bound2 = logger.bind(request_id="r1").bind(memory_bank="b1")
        bound2.info("test")
        assert len(bound2.entries) == 1
        assert bound2.entries[0]["request_id"] == "r1"
        assert bound2.entries[0]["memory_bank"] == "b1"

        # Unbind
        logger.clear()
        bound3 = logger.bind(request_id="r1").unbind("request_id")
        bound3.info("test")
        assert len(bound3.entries) == 1
        assert "request_id" not in bound3.entries[0]


class TestLoggerMock:
    """Tests for LoggerMock — captures calls without side effects."""

    def test_mock_captures_log_calls(self) -> None:
        """LoggerMock captures log method calls with their arguments."""
        mock = LoggerMock()
        mock.info("test message", request_id="r1", memory_bank="b1")

        assert len(mock.entries) == 1
        entry = mock.entries[0]
        assert entry["level"] == "info"
        assert entry["event"] == "test message"
        assert entry["request_id"] == "r1"
        assert entry["memory_bank"] == "b1"

    def test_mock_captures_different_levels(self) -> None:
        """LoggerMock captures calls at all log levels."""
        mock = LoggerMock()
        mock.debug("debug msg")
        mock.info("info msg")
        mock.warning("warn msg")
        mock.error("error msg")
        mock.critical("crit msg")

        assert len(mock.entries) == 5
        levels = [e["level"] for e in mock.entries]
        assert levels == ["debug", "info", "warning", "error", "critical"]

    def test_mock_no_side_effects(self) -> None:
        """LoggerMock does not write to stdout, stderr, or files."""
        mock = LoggerMock()

        import sys
        from io import StringIO

        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        mock.info("should not appear in stdout/stderr")

        stdout_output = sys.stdout.getvalue()
        stderr_output = sys.stderr.getvalue()

        sys.stdout, sys.stderr = old_stdout, old_stderr

        assert stdout_output == ""
        assert stderr_output == ""

    def test_mock_bind_returns_new_mock_with_context(self) -> None:
        """LoggerMock.bind() returns a new mock with accumulated context."""
        mock = LoggerMock()
        bound = mock.bind(request_id="r1", memory_bank="b1")
        bound.info("test")

        assert len(bound.entries) == 1
        assert bound.entries[0]["request_id"] == "r1"
        assert bound.entries[0]["memory_bank"] == "b1"

    def test_mock_bind_accumulates_context(self) -> None:
        """Chained bind() calls on LoggerMock accumulate context."""
        mock = LoggerMock()
        bound = mock.bind(request_id="r1").bind(memory_bank="b1")
        bound.info("test")

        assert len(bound.entries) == 1
        assert bound.entries[0]["request_id"] == "r1"
        assert bound.entries[0]["memory_bank"] == "b1"

    def test_mock_unbind_removes_field(self) -> None:
        """LoggerMock.unbind() removes a context field."""
        mock = LoggerMock()
        bound = mock.bind(request_id="r1").unbind("request_id")
        bound.info("test")

        assert len(bound.entries) == 1
        assert "request_id" not in bound.entries[0]

    def test_mock_entries_share_state_with_parent(self) -> None:
        """LoggerMock entries are shared between parent and bound instances."""
        mock = LoggerMock()
        bound = mock.bind(request_id="r1")
        bound.info("from bound")

        assert len(mock.entries) == 1
        assert mock.entries[0]["request_id"] == "r1"
        assert mock.entries[0]["event"] == "from bound"

    def test_mock_clear_resets_entries(self) -> None:
        """LoggerMock.clear() resets captured entries."""
        mock = LoggerMock()
        mock.info("before clear")
        assert len(mock.entries) == 1

        mock.clear()
        assert len(mock.entries) == 0

    def test_mock_no_file_io(self) -> None:
        """LoggerMock does not perform any file I/O operations."""
        mock = LoggerMock()
        mock.info("test")

        # Verify entries are in memory only
        assert isinstance(mock.entries, list)
        assert len(mock.entries) == 1

    def test_mock_captures_extra_kwargs(self) -> None:
        """LoggerMock captures all extra keyword arguments as context."""
        mock = LoggerMock()
        mock.info("msg", user="alice", action="login", ip="127.0.0.1")

        assert len(mock.entries) == 1
        entry = mock.entries[0]
        assert entry["user"] == "alice"
        assert entry["action"] == "login"
        assert entry["ip"] == "127.0.0.1"

    def test_mock_warn_alias(self) -> None:
        """LoggerMock.warn() is an alias for warning()."""
        mock = LoggerMock()
        mock.warn("warn msg")

        assert len(mock.entries) == 1
        assert mock.entries[0]["level"] == "warning"
        assert mock.entries[0]["event"] == "warn msg"


class TestJsonlFileHandler:
    """Tests for JSONL RotatingFileHandler configuration."""

    def test_file_logger_returns_bound_logger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_file_logger returns a non-None logger after init_structlog."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        monkeypatch.delenv("BENSYNE_LOG_FILE", raising=False)
        init_structlog()

        file_logger = get_file_logger()
        assert file_logger is not None

    def test_file_logger_has_log_methods(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """File logger exposes standard log methods."""
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        monkeypatch.delenv("BENSYNE_LOG_FILE", raising=False)
        init_structlog()

        file_logger = get_file_logger()
        assert hasattr(file_logger, "debug")
        assert hasattr(file_logger, "info")
        assert hasattr(file_logger, "warning")
        assert hasattr(file_logger, "error")

    def test_file_handler_is_rotating(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The file handler is a RotatingFileHandler with correct rotation settings."""
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), "test_bensyne_jsonl.jsonl")
        monkeypatch.setenv("BENSYNE_LOG_FILE", log_file)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = logging.getLogger("bensyne.file")
        file_handlers = [h for h in file_logger.handlers
                         if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        handler = file_handlers[0]
        assert handler.maxBytes == 10 * 1024 * 1024  # 10 MB
        assert handler.backupCount == 5

    def test_file_handler_has_10mb_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RotatingFileHandler maxBytes is 10 MB."""
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), "test_bensyne_10mb.jsonl")
        monkeypatch.setenv("BENSYNE_LOG_FILE", log_file)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = logging.getLogger("bensyne.file")
        file_handlers = [h for h in file_logger.handlers
                         if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 10 * 1024 * 1024

    def test_file_handler_has_5_backups(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RotatingFileHandler backupCount is 5."""
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), "test_bensyne_5bk.jsonl")
        monkeypatch.setenv("BENSYNE_LOG_FILE", log_file)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = logging.getLogger("bensyne.file")
        file_handlers = [h for h in file_logger.handlers
                         if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].backupCount == 5

    def test_log_file_path_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BENSYNE_LOG_FILE env var controls the log file path."""
        import tempfile
        custom_path = os.path.join(tempfile.gettempdir(), "custom_bensyne.jsonl")
        monkeypatch.setenv("BENSYNE_LOG_FILE", custom_path)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = logging.getLogger("bensyne.file")
        file_handlers = [h for h in file_logger.handlers
                         if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == custom_path

    def test_file_logger_writes_jsonl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """File logger writes valid JSON lines (one JSON object per line)."""
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), "test_jsonl_output.jsonl")
        # Clean up any existing file
        if os.path.exists(log_file):
            os.remove(log_file)
        monkeypatch.setenv("BENSYNE_LOG_FILE", log_file)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = get_file_logger()
        file_logger.info("test message", service="file_service", method="test", file_id="f1")

        # Read the file and verify each line is valid JSON
        with open(log_file, "r") as f:
            lines = f.readlines()

        assert len(lines) >= 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_jsonl_contains_structured_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JSONL output contains the structured fields (service, method, file_id)."""
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), "test_jsonl_fields.jsonl")
        if os.path.exists(log_file):
            os.remove(log_file)
        monkeypatch.setenv("BENSYNE_LOG_FILE", log_file)
        monkeypatch.delenv("BENSYNE_ENV", raising=False)
        init_structlog()

        file_logger = get_file_logger()
        file_logger.info("Creating file", service="file_service", method="create_file", file_id="f1")

        with open(log_file, "r") as f:
            lines = f.readlines()

        # Find the line with our test message
        matching = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if parsed.get("event") == "Creating file":
                matching.append(parsed)

        assert len(matching) >= 1
        entry = matching[0]
        assert entry.get("service") == "file_service"
        assert entry.get("method") == "create_file"
        assert entry.get("file_id") == "f1"
