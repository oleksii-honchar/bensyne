"""Validation helpers for MCP tool arguments."""

from __future__ import annotations

from src.domain.exceptions import ValidationError


def require_namespace(arguments: dict) -> str:
    """Extract namespace from arguments, raising ValidationError if missing or empty.

    Args:
        arguments: MCP tool call arguments dict.

    Returns:
        The namespace string.

    Raises:
        ValidationError: If namespace key is missing, None, or empty string.
    """
    namespace = arguments.get("namespace")
    if not namespace:
        raise ValidationError("namespace parameter is required")
    return namespace
