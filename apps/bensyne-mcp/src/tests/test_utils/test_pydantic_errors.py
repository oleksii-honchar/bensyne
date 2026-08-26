"""Unit tests for JSON-safe pydantic error sanitization.

pydantic v2 embeds the raw exception object in ``ctx.error`` for
field_validator failures. Error details are later passed through
``json.dumps`` (handlers._raise_on_ko), which crashes on raw exception
objects — this helper guarantees the details are always JSON-serializable.
"""

import json

from src.utils.errors import sanitize_pydantic_errors


class TestSanitizePydanticErrors:
    """sanitize_pydantic_errors makes pydantic error dicts JSON-serializable."""

    def test_stringifies_raw_exception_in_ctx(self) -> None:
        """A raw ValueError embedded in ctx.error becomes its message string."""
        errors = [
            {
                "type": "value_error",
                "loc": ("scope",),
                "msg": "Value error, Invalid scope: user-profile",
                "input": "user-profile",
                "ctx": {"error": ValueError("Invalid scope: user-profile")},
            }
        ]

        sanitized = sanitize_pydantic_errors(errors)

        assert sanitized[0]["ctx"]["error"] == "Invalid scope: user-profile"
        # The sanitized details must survive json.dumps (the handler path).
        json.dumps(sanitized)

    def test_leaves_json_safe_ctx_unchanged(self) -> None:
        """Primitive ctx values (e.g. min_length) pass through untouched."""
        errors = [
            {
                "type": "string_too_short",
                "loc": ("content",),
                "msg": "String should have at least 1 character",
                "input": "",
                "ctx": {"min_length": 1},
            }
        ]

        sanitized = sanitize_pydantic_errors(errors)

        assert sanitized[0]["ctx"] == {"min_length": 1}
        assert json.dumps(sanitized)

    def test_passthrough_when_no_ctx_key(self) -> None:
        """Errors without a ctx key are returned unchanged."""
        errors = [
            {
                "type": "missing",
                "loc": ("id",),
                "msg": "Field required",
                "input": {},
            }
        ]

        assert sanitize_pydantic_errors(errors) == errors

    def test_keeps_json_safe_collections_in_ctx(self) -> None:
        """JSON-safe collections (lists/dicts) in ctx stay as-is."""
        errors = [
            {
                "type": "value_error",
                "loc": ("x",),
                "msg": "m",
                "input": {},
                "ctx": {"allowed": [1, 2, 3], "nested": {"k": "v"}},
            }
        ]

        sanitized = sanitize_pydantic_errors(errors)

        assert sanitized[0]["ctx"]["allowed"] == [1, 2, 3]
        assert sanitized[0]["ctx"]["nested"] == {"k": "v"}
