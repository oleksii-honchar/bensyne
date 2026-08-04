"""Validation helpers tests."""

from __future__ import annotations

import pytest

from src.domain.exceptions import ValidationError
from src.services.tools.validation import require_memory_bank


class TestRequireMemoryBank:
    """require_memory_bank extracts memory_bank or raises ValidationError."""

    def test_returns_memory_bank_when_present(self) -> None:
        result = require_memory_bank({"memory_bank": "my-bank"})
        assert result == "my-bank"

    def test_returns_default_bank(self) -> None:
        result = require_memory_bank({"memory_bank": "default"})
        assert result == "default"

    def test_raises_when_memory_bank_key_missing(self) -> None:
        with pytest.raises(ValidationError, match="memory_bank parameter is required"):
            require_memory_bank({})

    def test_raises_when_memory_bank_key_missing_with_other_keys(self) -> None:
        with pytest.raises(ValidationError, match="memory_bank parameter is required"):
            require_memory_bank({"content": "test", "query": "foo"})

    def test_raises_when_memory_bank_is_empty_string(self) -> None:
        with pytest.raises(ValidationError, match="memory_bank parameter is required"):
            require_memory_bank({"memory_bank": ""})

    def test_raises_when_memory_bank_is_none(self) -> None:
        with pytest.raises(ValidationError, match="memory_bank parameter is required"):
            require_memory_bank({"memory_bank": None})
