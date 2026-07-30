"""Logging utilities."""

import asyncio
import functools
import logging
import os
from typing import Any, Callable, Coroutine, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _extract_namespace(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extract namespace from handler call arguments.

    Handlers are called as: handler(router, arguments_dict)
    where arguments_dict contains the namespace key.
    """
    # First check kwargs directly (defensive)
    if "namespace" in kwargs:
        return kwargs["namespace"]
    # Then check arguments dict (second positional arg)
    if len(args) > 1 and isinstance(args[1], dict):
        return args[1].get("namespace", "default")
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
    """Decorator that logs tool call lifecycle with namespace context.

    Logs:
        - Entry with namespace (INFO)
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
            namespace = _extract_namespace(args, kwargs)

            logger.info(f"{tool_name} called: namespace={namespace}")
            logger.debug(f"{tool_name} arguments: {kwargs} (args[1]={args[1] if len(args) > 1 else None})")
            logger.debug(f"{tool_name}: routing to namespace={namespace}")
            logger.debug(f"{tool_name}: getting instance for namespace={namespace}")

            try:
                result = func(*args, **kwargs)
                logger.info(f"{tool_name} completed: namespace={namespace}")
                return result
            except Exception as e:
                logger.error(f"{tool_name} failed: namespace={namespace}, error={str(e)}")
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            namespace = _extract_namespace(args, kwargs)

            logger.info(f"{tool_name} called: namespace={namespace}")
            logger.debug(f"{tool_name} arguments: {kwargs} (args[1]={args[1] if len(args) > 1 else None})")
            logger.debug(f"{tool_name}: routing to namespace={namespace}")
            logger.debug(f"{tool_name}: getting instance for namespace={namespace}")

            try:
                result = await func(*args, **kwargs)
                logger.info(f"{tool_name} completed: namespace={namespace}")
                return result
            except Exception as e:
                logger.error(f"{tool_name} failed: namespace={namespace}, error={str(e)}")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
