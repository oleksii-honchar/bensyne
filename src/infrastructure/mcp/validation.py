"""Validation helpers for MCP tool arguments."""

from __future__ import annotations

from src.domain.exceptions import ValidationError


def require_memory_bank(arguments: dict) -> str:
    """Extract memory_bank from arguments, raising ValidationError if missing or empty.

    Args:
        arguments: MCP tool call arguments dict.

    Returns:
        The memory_bank string.

    Raises:
        ValidationError: If memory_bank key is missing, None, or empty string.
    """
    memory_bank = arguments.get("memory_bank")
    if not memory_bank:
        raise ValidationError("memory_bank parameter is required")
    return memory_bank
