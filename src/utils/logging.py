"""Logging utilities."""

import asyncio
import functools
import logging
import os
from typing import Any, Callable, Coroutine, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


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


def setup_logging() -> logging.Logger:
    """Configure application logging.

    Reads LOG_LEVEL from environment (default: INFO).
    Accepts: DEBUG, INFO, WARNING, ERROR.
    Format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    Uses StreamHandler only (stdout/stderr, no file handlers).

    Returns:
        Logger named "better-mnemosyne".
    """
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    if not isinstance(log_level, int):
        log_level = logging.INFO

    logger = logging.getLogger("better-mnemosyne")
    logger.setLevel(log_level)

    # Avoid duplicate handlers on repeated calls
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

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
    logger = logging.getLogger("better-mnemosyne")

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
