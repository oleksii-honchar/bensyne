"""Unit tests for the handlers._raise_on_ko helper.

_pins the contract that MCP tool errors surface Result error details_ so
agents get actionable context (e.g. ``available_chunk_indexes``) rather than
a bare error code.
"""

from __future__ import annotations

import json

import pytest

from src.domain.exceptions import ValidationError
from src.infrastructure.mcp.handlers import _raise_on_ko
from src.utils.result import ErrorWithDetails, Result


class TestRaiseOnKo:
    """_raise_on_ko maps Result -> value or ValidationError (with details)."""

    def test_ko_with_details_includes_error_code_and_details(self) -> None:
        """AC1: KO with non-empty details -> message carries code AND details."""
        details = {
            "available_chunk_indexes": [0, 1, 2],
            "center_chunk_index": 5,
            "total_chunks": 3,
        }
        result = Result.ko(
            [ErrorWithDetails("CENTER_CHUNK_INDEX_OUT_OF_RANGE", details)]
        )

        with pytest.raises(ValidationError) as exc_info:
            _raise_on_ko(result, "fetchFile")

        msg = str(exc_info.value)
        # Handler name + error code present
        assert "fetchFile" in msg
        assert "CENTER_CHUNK_INDEX_OUT_OF_RANGE" in msg
        # Detail keys and values present (JSON-encoded)
        assert "available_chunk_indexes" in msg
        assert json.dumps(details) in msg

    def test_ko_with_empty_details_has_unchanged_format(self) -> None:
        """AC2: KO with empty details -> message format unchanged (no details fragment)."""
        result = Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])

        with pytest.raises(ValidationError) as exc_info:
            _raise_on_ko(result, "recallMemory")

        msg = str(exc_info.value)
        # Error code present
        assert "QUERY_REQUIRED" in msg
        # No stray "details:" fragment
        assert "details:" not in msg
        # Exact legacy format preserved
        assert msg == "recallMemory failed: QUERY_REQUIRED"

    def test_ko_with_none_details_has_unchanged_format(self) -> None:
        """AC2 (defensive): KO with None details -> no details fragment."""
        result = Result.ko([ErrorWithDetails("SOME_ERROR", None)])

        with pytest.raises(ValidationError) as exc_info:
            _raise_on_ko(result, "searchFiles")

        msg = str(exc_info.value)
        assert "SOME_ERROR" in msg
        assert "details:" not in msg
        assert msg == "searchFiles failed: SOME_ERROR"

    def test_ok_path_returns_value(self) -> None:
        """AC3: OK path unchanged -> returns result.value."""
        value = {"status": "stored", "memory_id": "mem_123"}
        result = Result.ok(value)

        returned = _raise_on_ko(result, "rememberMemory")
        assert returned == value
