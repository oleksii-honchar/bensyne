"""Logging utilities."""

import asyncio
import functools
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Rotation: 10 MB per file, keep 3 backups
_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 3

# Default log file: ~/.local/share/bensyne/logs/bensyne.log
_DEFAULT_LOG_FILE = os.path.expanduser("~/.local/share/bensyne/logs/bensyne.log")


def _extract_memory_bank(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extract memory_bank from handler call arguments.

    Handlers are called as: handler(router, arguments_dict)
    where arguments_dict contains the memory_bank key.
    """
    # First check kwargs directly (defensive)
    if "memory_bank" in kwargs:
        return kwargs["memory_bank"]
    # Then check arguments dict (second positional arg)
    if len(args) > 1 and isinstance(args[1], dict):
        return args[1].get("memory_bank", "default")
    return "default"


def setup_logging(log_file: str | None = None) -> logging.Logger:
    """Configure application logging.

    Reads LOG_LEVEL from environment (default: INFO).
    Accepts: DEBUG, INFO, WARNING, ERROR.
    Format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    Always writes to file with rotation (10 MB, 3 backups) and stdout.
    Default log file: ~/.local/share/bensyne/logs/bensyne.log

    Args:
        log_file: Optional path to log file. Defaults to ~/.local/share/bensyne/logs/

    Returns:
        Logger named "bensyne".
    """
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    if not isinstance(log_level, int):
        log_level = logging.INFO

    effective_log_file = log_file or _DEFAULT_LOG_FILE

    logger = logging.getLogger("bensyne")
    logger.setLevel(log_level)

    # Avoid duplicate handlers on repeated calls
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

        # Console handler — always on
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler — always on (with rotation)
        log_path = Path(effective_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            effective_log_file,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_tool_call(tool_name: str) -> Callable[[F], F]:
    """Decorator that logs tool call lifecycle with memory_bank context.

    Logs:
        - Entry with memory_bank (INFO)
        - Arguments (DEBUG)
        - Routing decision (DEBUG)
        - Instance management (DEBUG)
        - Completion (INFO)
        - Errors (ERROR)

    Supports both sync and async functions.
    """
    logger = logging.getLogger("bensyne")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            memory_bank = _extract_memory_bank(args, kwargs)

            logger.info(f"{tool_name} called: memory_bank={memory_bank}")
            logger.debug(f"{tool_name} arguments: {kwargs} (args[1]={args[1] if len(args) > 1 else None})")
            logger.debug(f"{tool_name}: routing to memory_bank={memory_bank}")
            logger.debug(f"{tool_name}: getting instance for memory_bank={memory_bank}")

            try:
                result = func(*args, **kwargs)
                logger.info(f"{tool_name} completed: memory_bank={memory_bank}")
                return result
            except Exception as e:
                logger.error(f"{tool_name} failed: memory_bank={memory_bank}, error={str(e)}")
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            memory_bank = _extract_memory_bank(args, kwargs)

            logger.info(f"{tool_name} called: memory_bank={memory_bank}")
            logger.debug(f"{tool_name} arguments: {kwargs} (args[1]={args[1] if len(args) > 1 else None})")
            logger.debug(f"{tool_name}: routing to memory_bank={memory_bank}")
            logger.debug(f"{tool_name}: getting instance for memory_bank={memory_bank}")

            try:
                result = await func(*args, **kwargs)
                logger.info(f"{tool_name} completed: memory_bank={memory_bank}")
                return result
            except Exception as e:
                logger.error(f"{tool_name} failed: memory_bank={memory_bank}, error={str(e)}")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
