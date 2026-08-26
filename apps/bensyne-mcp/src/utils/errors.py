"""Error handling utilities."""

import json
from typing import Any, Mapping


def sanitize_pydantic_errors(errors: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Make pydantic v2 error dicts JSON-serializable.

    pydantic v2 embeds the raw exception object in ``ctx.error`` for
    field_validator failures (e.g. ``ValueError``). These objects are not
    JSON-serializable and crash ``json.dumps`` when error details are
    surfaced to MCP tool handlers. Every ``ctx`` value that is not already
    JSON-safe is stringified.
    """
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        item = dict(error)
        if "ctx" in error:
            item["ctx"] = _json_safe_ctx(error.get("ctx"))
        sanitized.append(item)
    return sanitized


def _json_safe_ctx(ctx: Any) -> Any:
    """Sanitize a pydantic error ``ctx`` dict, or pass through non-dicts."""
    if not isinstance(ctx, dict):
        return ctx
    return {key: _json_safe_value(value) for key, value in ctx.items()}


def _json_safe_value(value: Any) -> Any:
    """Return ``value`` unchanged if JSON-serializable, else its str form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
