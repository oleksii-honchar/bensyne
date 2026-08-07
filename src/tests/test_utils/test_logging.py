"""Tests for src.utils.logging."""

import asyncio
import logging
import os
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from src.utils.logging import log_tool_call, setup_logging


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_default_log_level_is_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_logging respects LOG_LEVEL env var — default is INFO."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        logger = setup_logging()

        assert logger.name == "better-mnemosyne"
        assert logger.level == logging.INFO

    def test_log_level_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_logging respects LOG_LEVEL=DEBUG."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        logger = setup_logging()

        assert logger.level == logging.DEBUG

    def test_log_level_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_logging respects LOG_LEVEL=WARNING."""
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        logger = setup_logging()

        assert logger.level == logging.WARNING

    def test_log_level_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_logging respects LOG_LEVEL=ERROR."""
        monkeypatch.setenv("LOG_LEVEL", "ERROR")

        logger = setup_logging()

        assert logger.level == logging.ERROR

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """setup_logging falls back to INFO for invalid LOG_LEVEL."""
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        logger = setup_logging()

        assert logger.level == logging.INFO

    def test_logger_name_is_better_mnemosyne(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Logger name is 'better-mnemosyne'."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        logger = setup_logging()

        assert logger.name == "better-mnemosyne"

    def test_stream_and_file_handlers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both StreamHandler and RotatingFileHandler are always present."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        logger = setup_logging()

        handler_types = [type(h).__name__ for h in logger.handlers]
        assert any("StreamHandler" in t for t in handler_types)
        assert any("FileHandler" in t for t in handler_types)

    def test_log_file_created_and_written(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Log file is created and contains log output."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")

        logger = logging.getLogger("better-mnemosyne")
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        log_file = str(tmp_path / "logs" / "test.log")
        logger = setup_logging(log_file=log_file)

        logger.info("file logging test")

        log_content = Path(log_file).read_text()
        assert "file logging test" in log_content

    def test_log_directory_created(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Parent directories for log file are created if missing."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")

        logger = logging.getLogger("better-mnemosyne")
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        log_file = str(tmp_path / "nested" / "logs" / "test.log")
        logger = setup_logging(log_file=log_file)

        assert Path(log_file).parent.is_dir()

    def test_default_log_file_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default log file uses ~/.local/share/bensyne/logs/better-mnemosyne.log."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        logger = logging.getLogger("better-mnemosyne")
        for h in logger.handlers[:]:
            logger.removeHandler(h)

        logger = setup_logging()

        file_handlers = [h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1
        expected = os.path.expanduser("~/.local/share/bensyne/logs/bensyne.log")
        assert file_handlers[0].baseFilename == expected

    def test_log_format(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        """Log format matches specification."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        logger = setup_logging()
        caplog.set_level(logging.INFO, logger="better-mnemosyne")

        logger.info("test message")

        log_record = caplog.records[0]
        log_message = log_record.getMessage()
        assert log_message == "test message"
        assert log_record.levelname == "INFO"
        assert log_record.name == "better-mnemosyne"


class TestLogToolCallDecorator:
    """Tests for log_tool_call decorator."""

    @pytest.fixture
    def logger(self, monkeypatch: pytest.MonkeyPatch) -> logging.Logger:
        """Provide a logger with a StringIO handler for capturing logs."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        return setup_logging()

    def _capture_logs(self, logger: logging.Logger) -> StringIO:
        """Helper to attach a StringIO handler and return it."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        return stream

    def test_logs_entry_with_memory_bank(self, logger: logging.Logger) -> None:
        """Decorator logs entry with memory_bank."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str, value: int) -> int:
            return value

        stream = self._capture_logs(logger)
        my_func(memory_bank="ns1", value=42)

        log_output = stream.getvalue()
        assert "test_tool called: memory_bank=ns1" in log_output

    def test_logs_arguments_at_debug(self, logger: logging.Logger) -> None:
        """Decorator logs arguments at DEBUG level."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str, value: int) -> int:
            return value

        stream = self._capture_logs(logger)
        my_func(memory_bank="ns1", value=42)

        log_output = stream.getvalue()
        assert "test_tool arguments:" in log_output
        assert "memory_bank=ns1" in log_output or "value=42" in log_output

    def test_logs_routing(self, logger: logging.Logger) -> None:
        """Decorator logs routing to memory_bank."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str) -> str:
            return memory_bank

        stream = self._capture_logs(logger)
        my_func(memory_bank="ns1")

        log_output = stream.getvalue()
        assert "test_tool: routing to memory_bank=ns1" in log_output

    def test_logs_instance_management(self, logger: logging.Logger) -> None:
        """Decorator logs instance management."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str) -> str:
            return memory_bank

        stream = self._capture_logs(logger)
        my_func(memory_bank="ns1")

        log_output = stream.getvalue()
        assert "test_tool: getting instance for memory_bank=ns1" in log_output

    def test_logs_completion(self, logger: logging.Logger) -> None:
        """Decorator logs completion."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str) -> str:
            return "ok"

        stream = self._capture_logs(logger)
        my_func(memory_bank="ns1")

        log_output = stream.getvalue()
        assert "test_tool completed: memory_bank=ns1" in log_output

    def test_logs_error_when_function_raises(self, logger: logging.Logger) -> None:
        """Decorator logs errors when function raises."""

        @log_tool_call("test_tool")
        def my_func(memory_bank: str) -> None:
            raise ValueError("boom")

        stream = self._capture_logs(logger)

        with pytest.raises(ValueError, match="boom"):
            my_func(memory_bank="ns1")

        log_output = stream.getvalue()
        assert "test_tool failed: memory_bank=ns1" in log_output
        assert "error=" in log_output
        assert "boom" in log_output

    async def test_supports_async_functions(self, logger: logging.Logger) -> None:
        """Decorator supports async functions."""

        @log_tool_call("async_tool")
        async def my_async_func(memory_bank: str) -> str:
            await asyncio.sleep(0)
            return "done"

        stream = self._capture_logs(logger)
        result = await my_async_func(memory_bank="ns1")

        assert result == "done"
        log_output = stream.getvalue()
        assert "async_tool called: memory_bank=ns1" in log_output
        assert "async_tool completed: memory_bank=ns1" in log_output

    async def test_async_logs_error_when_function_raises(self, logger: logging.Logger) -> None:
        """Decorator logs errors for async functions that raise."""

        @log_tool_call("async_tool")
        async def my_async_func(memory_bank: str) -> None:
            await asyncio.sleep(0)
            raise RuntimeError("async boom")

        stream = self._capture_logs(logger)

        with pytest.raises(RuntimeError, match="async boom"):
            await my_async_func(memory_bank="ns1")

        log_output = stream.getvalue()
        assert "async_tool failed: memory_bank=ns1" in log_output
        assert "error=" in log_output
        assert "async boom" in log_output
