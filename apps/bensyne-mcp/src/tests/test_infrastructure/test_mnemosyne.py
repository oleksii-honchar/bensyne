"""Mnemosyne infrastructure tests: BankManager and MnemosyneClient."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.infrastructure.mnemosyne.client import MnemosyneClient


# ---------------------------------------------------------------------------
# BankManager tests
# ---------------------------------------------------------------------------


class TestBankManagerPaths:
    """BankManager.get_bank_db_path returns correct paths."""

    @pytest.fixture
    def bank_manager(self, tmp_path: Path) -> BankManager:
        return BankManager(data_dir=str(tmp_path), default_bank="default")

    def test_default_bank_returns_root_db(self, bank_manager: BankManager, tmp_path: Path) -> None:
        """Default memory bank resolves to {data_dir}/mnemosyne.db."""
        path = bank_manager.get_bank_db_path("default")
        assert path == tmp_path / "mnemosyne.db"

    def test_custom_bank_returns_nested_db(self, bank_manager: BankManager, tmp_path: Path) -> None:
        """Custom memory bank resolves to {data_dir}/banks/{memory_bank}/mnemosyne.db."""
        path = bank_manager.get_bank_db_path("obsidian-vault")
        assert path == tmp_path / "banks" / "obsidian-vault" / "mnemosyne.db"

    def test_custom_bank_creates_parent_directory(self, bank_manager: BankManager, tmp_path: Path) -> None:
        """Parent directory for custom bank is created if missing."""
        banks_dir = tmp_path / "banks" / "agent-sessions"
        assert not banks_dir.exists()

        path = bank_manager.get_bank_db_path("agent-sessions")

        assert path.parent.exists()
        assert path == tmp_path / "banks" / "agent-sessions" / "mnemosyne.db"

    def test_default_bank_creates_parent_if_missing(self, tmp_path: Path) -> None:
        """Default bank path works even if data_dir is empty."""
        bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
        path = bank_manager.get_bank_db_path("default")
        assert path.parent.exists()
        assert path == tmp_path / "mnemosyne.db"

    def test_custom_default_bank_name(self, tmp_path: Path) -> None:
        """When default_bank is customized, that name maps to root db."""
        bank_manager = BankManager(data_dir=str(tmp_path), default_bank="main")
        assert bank_manager.get_bank_db_path("main") == tmp_path / "mnemosyne.db"
        assert bank_manager.get_bank_db_path("other") == tmp_path / "banks" / "other" / "mnemosyne.db"


# ---------------------------------------------------------------------------
# MnemosyneClient tests
# ---------------------------------------------------------------------------


class TestMnemosyneClientCreation:
    """MnemosyneClient wraps mnemosyne.Mnemosyne(bank=...) correctly."""

    @pytest.fixture
    def mock_mnemosyne_class(self) -> MagicMock:
        """Return a mock Mnemosyne class and instance."""
        mock_instance = MagicMock()
        mock_instance.remember.return_value = "mem_123"
        mock_instance.recall.return_value = []
        mock_instance.forget.return_value = True
        mock_instance.update.return_value = True
        mock_instance.sleep.return_value = {"status": "ok"}
        mock_instance.get_stats.return_value = {"working": 0, "episodic": 0}
        mock_instance.get.return_value = None
        mock_class = MagicMock(return_value=mock_instance)
        return mock_class

    def _mock_mnemosyne_instance(self) -> MagicMock:
        """Helper to create a fully configured mock Mnemosyne instance."""
        mock = MagicMock()
        mock.remember.return_value = "mem_abc"
        mock.recall.return_value = []
        mock.forget.return_value = True
        mock.update.return_value = True
        mock.sleep.return_value = {"status": "ok"}
        mock.get_stats.return_value = {"working": 0, "episodic": 0}
        mock.get.return_value = None
        return mock

    def test_creates_instance_for_given_bank(self, tmp_path: Path) -> None:
        """MnemosyneClient instantiates Mnemosyne with correct bank and db_path."""
        mock_instance = self._mock_mnemosyne_instance()

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="test-bank", bank_manager=bank_manager)

            assert client.memory_bank == "test-bank"
            assert client._instance is mock_instance

    def test_tracks_created_at_timestamp(self, tmp_path: Path) -> None:
        """MnemosyneClient records created_at for LRU eviction."""
        import time

        mock_instance = self._mock_mnemosyne_instance()

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            before = time.time()
            client = MnemosyneClient(memory_bank="test-bank", bank_manager=bank_manager)
            after = time.time()

            assert before <= client.created_at <= after

    def test_remember_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """remember() calls wrapped Mnemosyne.remember and returns dict."""
        mock_instance = MagicMock()
        mock_instance.remember.return_value = "mem_123"

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.remember("test content", source="test")

            mock_instance.remember.assert_called_once()
            call_kwargs = mock_instance.remember.call_args.kwargs
            assert call_kwargs["content"] == "test content"
            assert call_kwargs["source"] == "test"
            assert result["memory_id"] == "mem_123"

    def test_recall_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """recall() calls wrapped Mnemosyne.recall and returns list."""
        mock_results = [{"id": "mem_1", "content": "hello"}]
        mock_instance = MagicMock()
        mock_instance.recall.return_value = mock_results

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.recall("hello", limit=5)

            mock_instance.recall.assert_called_once()
            call_kwargs = mock_instance.recall.call_args.kwargs
            assert call_kwargs["query"] == "hello"
            assert call_kwargs["top_k"] == 5
            assert result == mock_results

    def test_forget_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """forget() calls wrapped Mnemosyne.forget and returns status dict."""
        mock_instance = MagicMock()
        mock_instance.forget.return_value = True

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.forget("mem_123")

            mock_instance.forget.assert_called_once_with("mem_123")
            assert result["status"] == "deleted"

    def test_update_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """update() calls wrapped Mnemosyne.update and returns status dict."""
        mock_instance = MagicMock()
        mock_instance.update.return_value = True

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.update("mem_123", content="updated", importance=0.8)

            mock_instance.update.assert_called_once_with(
                "mem_123",
                content="updated",
                importance=0.8,
            )
            assert result["status"] == "updated"

    def test_sleep_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """sleep() calls wrapped Mnemosyne.sleep and returns result dict."""
        mock_result = {"status": "consolidated", "consolidated": 5}
        mock_instance = MagicMock()
        mock_instance.sleep.return_value = mock_result

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.sleep()

            mock_instance.sleep.assert_called_once()
            assert result == mock_result

    def test_stats_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """stats() calls wrapped Mnemosyne.get_stats and returns stats dict."""
        mock_stats = {"working": 10, "episodic": 5}
        mock_instance = MagicMock()
        mock_instance.get_stats.return_value = mock_stats

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.stats()

            mock_instance.get_stats.assert_called_once()
            assert result == mock_stats

    def test_get_delegates_to_wrapped_instance(self, tmp_path: Path) -> None:
        """get() calls wrapped Mnemosyne.get and returns memory or None."""
        mock_memory = {"id": "mem_123", "content": "test"}
        mock_instance = MagicMock()
        mock_instance.get.return_value = mock_memory

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.get("mem_123")

            mock_instance.get.assert_called_once_with("mem_123")
            assert result == mock_memory

    def test_get_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """get() returns None when wrapped instance returns None."""
        mock_instance = MagicMock()
        mock_instance.get.return_value = None

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
            },
        ):
            from src.infrastructure.mnemosyne.client import MnemosyneClient

            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            client = MnemosyneClient(memory_bank="default", bank_manager=bank_manager)

            result = client.get("nonexistent")

            assert result is None
