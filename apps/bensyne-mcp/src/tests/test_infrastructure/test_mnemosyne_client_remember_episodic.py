"""MnemosyneClient remember() method tests — direct INSERT into episodic_memory.

Verifies:
- remember() inserts into episodic_memory table (not working_memory)
- agent-session memories have valid_until set to 365 days from now
- non-agent-session memories have valid_until set to NULL
- remembered memory is retrievable via get() and recall()
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
import sqlite3

from src.utils.result import Result
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from pathlib import Path


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for each test."""
    return tmp_path / "bensyne-test-data"


@pytest.fixture
def agent_session_client(temp_data_dir: Path) -> MnemosyneClient:
    """Create a client for an agent-session memory bank."""
    temp_data_dir.mkdir(parents=True, exist_ok=True)
    client = MnemosyneClient(
        memory_bank="agent-session-test-session-123",
        data_dir=str(temp_data_dir),
    )
    return client


@pytest.fixture
def regular_client(temp_data_dir: Path) -> MnemosyneClient:
    """Create a client for a regular memory bank."""
    temp_data_dir.mkdir(parents=True, exist_ok=True)
    client = MnemosyneClient(
        memory_bank="test-bank",
        data_dir=str(temp_data_dir),
    )
    return client


def _connect_to_db(client: MnemosyneClient) -> sqlite3.Connection:
    """Connect directly to the client's database."""
    return client._instance.conn


class TestRememberInsertsEpisodicMemory:
    """remember() uses direct INSERT into episodic_memory table."""

    def test_remembers_to_episodic_not_working_memory(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """remember() inserts into episodic_memory, not working_memory."""
        result = agent_session_client.remember(
            content="Test content for remember episodic memory",
            source="test",
            importance=0.7,
        )

        assert result.is_ok

        conn = _connect_to_db(agent_session_client)
        try:
            episodic_count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE content = ?",
                ("Test content for remember episodic memory",),
            ).fetchone()[0]
            working_count = conn.execute(
                "SELECT COUNT(*) FROM working_memory WHERE content = ?",
                ("Test content for remember episodic memory",),
            ).fetchone()[0]

            assert episodic_count == 1, "Memory should be in episodic_memory"
            assert working_count == 0, "Memory should NOT be in working_memory"
        finally:
            conn.close()

    def test_returns_memory_id(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """remember() returns a dict with memory_id."""
        result = agent_session_client.remember(
            content="Content for ID verification",
            source="test",
            importance=0.5,
        )

        assert result.is_ok
        result_dict = result.value
        assert "memory_id" in result_dict
        assert len(result_dict["memory_id"]) == 16  # 16 hex chars

        # Verify the ID is actually stored in the database
        conn = _connect_to_db(agent_session_client)
        try:
            row = conn.execute(
                "SELECT id, content FROM episodic_memory WHERE id = ?",
                (result_dict["memory_id"],),
            ).fetchone()
            assert row is not None
            assert row[0] == result_dict["memory_id"]
            assert row[1] == "Content for ID verification"
        finally:
            conn.close()


class TestRememberValidUntilPolicy:
    """remember() applies correct TTL based on memory_bank name."""

    def test_agent_session_memory_has_365day_ttl(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """agent-session memories have valid_until set to ~365 days from now."""
        result = agent_session_client.remember(
            content="Agent session remember memory content",
            source="test",
            importance=0.6,
        )
        assert result.is_ok

        conn = _connect_to_db(agent_session_client)
        try:
            row = conn.execute(
                "SELECT id, valid_until FROM episodic_memory WHERE content = ?",
                ("Agent session remember memory content",),
            ).fetchone()
            assert row is not None
            assert row[1] is not None, "valid_until should be set for agent-session memories"

            # Parse valid_until and check it's approximately 365 days from now
            valid_until_str = row[1]
            if "T" in valid_until_str:
                valid_until = datetime.fromisoformat(valid_until_str.replace("Z", "+00:00"))
            else:
                valid_until = datetime.strptime(valid_until_str, "%Y-%m-%d %H:%M:%S")

            now = datetime.now(timezone.utc)
            expected = now + timedelta(days=365)
            # Allow 1 day tolerance
            delta = abs((valid_until - expected).total_seconds())
            assert delta < 86400, f"valid_until should be ~365 days from now, got {valid_until}"
        finally:
            conn.close()

    def test_non_agent_session_memory_has_null_ttl(
        self, regular_client: MnemosyneClient
    ) -> None:
        """Non-agent-session memories have valid_until set to NULL."""
        result = regular_client.remember(
            content="Regular remember memory content",
            source="test",
            importance=0.4,
        )
        assert result.is_ok

        conn = _connect_to_db(regular_client)
        try:
            row = conn.execute(
                "SELECT id, valid_until FROM episodic_memory WHERE content = ?",
                ("Regular remember memory content",),
            ).fetchone()
            assert row is not None
            assert row[1] is None, "valid_until should be NULL for non-agent-session memories"
        finally:
            conn.close()


class TestRememberRetrieval:
    """Remembered memories are retrievable via get() and recall()."""

    def test_remembered_memory_retrievable_via_get(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """Memory remembered via remember() can be retrieved via get()."""
        result = agent_session_client.remember(
            content="Memory for get() retrieval via remember",
            source="test",
            importance=0.5,
        )
        assert result.is_ok
        memory_id = result.value["memory_id"]

        retrieved = agent_session_client.get(memory_id)
        assert retrieved is not None
        assert retrieved["content"] == "Memory for get() retrieval via remember"

    def test_remembered_memory_retrievable_via_recall(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """Memory remembered via remember() can be retrieved via recall()."""
        result = agent_session_client.remember(
            content="Unique content for recall via remember test",
            source="test",
            importance=0.8,
        )
        assert result.is_ok

        # Give FTS a moment to index
        time.sleep(0.1)

        recall_result = agent_session_client.recall(query="Unique content for recall via remember", limit=5)
        assert recall_result.is_ok
        assert len(recall_result.value) > 0
        found = any(
            m["content"] == "Unique content for recall via remember test"
            for m in recall_result.value
        )
        assert found, "Remembered memory should be found via recall()"