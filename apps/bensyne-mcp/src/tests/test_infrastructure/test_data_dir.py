"""Tests for resolve_data_dir — DATA_DIR env → config → ./data precedence.

Resolution order (highest to lowest priority):
1. Explicit value (from CLI --data-dir / config)
2. DATA_DIR environment variable
3. "./data" (relative to CWD)
"""

import pytest

from src.infrastructure.config.data_dir import resolve_data_dir


class TestResolveDataDir:
    def test_no_env_no_explicit_returns_relative_default(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """No explicit value and no DATA_DIR env -> relative ./data."""
        monkeypatch.delenv("DATA_DIR", raising=False)
        assert resolve_data_dir() == "./data"

    def test_explicit_none_falls_through_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """resolve_data_dir(None) behaves like no explicit value."""
        monkeypatch.delenv("DATA_DIR", raising=False)
        assert resolve_data_dir(None) == "./data"

    def test_env_wins_over_default_when_no_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """DATA_DIR env var is honored when no explicit value is given."""
        monkeypatch.setenv("DATA_DIR", "/from/env")
        assert resolve_data_dir() == "/from/env"
        assert resolve_data_dir(None) == "/from/env"

    def test_explicit_wins_over_env(self, monkeypatch: pytest.MonkeyPatch):
        """An explicit value wins over the DATA_DIR env var."""
        monkeypatch.setenv("DATA_DIR", "/from/env")
        assert resolve_data_dir("/from/cli") == "/from/cli"
