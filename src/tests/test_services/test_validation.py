"""Validation helpers tests."""

from __future__ import annotations

import pytest

from src.domain.exceptions import ValidationError
from src.services.tools.validation import require_namespace


class TestRequireNamespace:
    """require_namespace extracts namespace or raises ValidationError."""

    def test_returns_namespace_when_present(self) -> None:
        result = require_namespace({"namespace": "my-namespace"})
        assert result == "my-namespace"

    def test_returns_default_namespace(self) -> None:
        result = require_namespace({"namespace": "default"})
        assert result == "default"

    def test_raises_when_namespace_key_missing(self) -> None:
        with pytest.raises(ValidationError, match="namespace parameter is required"):
            require_namespace({})

    def test_raises_when_namespace_key_missing_with_other_keys(self) -> None:
        with pytest.raises(ValidationError, match="namespace parameter is required"):
            require_namespace({"content": "test", "query": "foo"})

    def test_raises_when_namespace_is_empty_string(self) -> None:
        with pytest.raises(ValidationError, match="namespace parameter is required"):
            require_namespace({"namespace": ""})

    def test_raises_when_namespace_is_none(self) -> None:
        with pytest.raises(ValidationError, match="namespace parameter is required"):
            require_namespace({"namespace": None})
