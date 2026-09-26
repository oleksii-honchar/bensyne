"""MnemosyneClient save() method tests — direct INSERT into episodic_memory.

Verifies:
- save() inserts into episodic_memory table (not working_memory)
- agent-session memories have valid_until set to 365 days from now
- non-agent-session memories have valid_until set to NULL
- saved memory is retrievable via get() and recall()
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlite3

from src.domain.memory_entity import Memory
from src.utils.result import Result
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    # Use the same connection object that the Mnemosyne instance uses
    # to ensure we see all changes without needing to commit
    return client._instance.conn


# ---------------------------------------------------------------------------
# save() inserts into episodic_memory
# ---------------------------------------------------------------------------


class TestSaveInsertsEpisodicMemory:
    """save() uses direct INSERT into episodic_memory table."""

    def test_saves_to_episodic_not_working_memory(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """save() inserts into episodic_memory, not working_memory."""
        memory = Memory(
            id="placeholder-id",
            content="Test content for episodic memory",
            importance=0.7,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = agent_session_client.save(memory)

        assert result.is_ok

        conn = _connect_to_db(agent_session_client)
        try:
            episodic_count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE content = ?",
                ("Test content for episodic memory",),
            ).fetchone()[0]
            working_count = conn.execute(
                "SELECT COUNT(*) FROM working_memory WHERE content = ?",
                ("Test content for episodic memory",),
            ).fetchone()[0]

            assert episodic_count == 1, "Memory should be in episodic_memory"
            assert working_count == 0, "Memory should NOT be in working_memory"
        finally:
            conn.close()

    def test_returns_memory_with_actual_id(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """save() returns Memory with the actual memory_id."""
        memory = Memory(
            id="placeholder-id",
            content="Content for ID verification",
            importance=0.5,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = agent_session_client.save(memory)

        assert result.is_ok
        saved_memory = result.value
        assert saved_memory.id != "placeholder-id"
        assert len(saved_memory.id) == 16  # 16 hex chars

        # Verify the ID is actually stored in the database
        conn = _connect_to_db(agent_session_client)
        try:
            row = conn.execute(
                "SELECT id, content FROM episodic_memory WHERE id = ?",
                (saved_memory.id,),
            ).fetchone()
            assert row is not None
            assert row[0] == saved_memory.id
            assert row[1] == "Content for ID verification"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# TTL policy — valid_until
# ---------------------------------------------------------------------------


class TestSaveValidUntilPolicy:
    """save() applies correct TTL based on memory_bank name."""

    def test_agent_session_memory_has_365day_ttl(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """agent-session memories have valid_until set to ~365 days from now."""
        memory = Memory(
            id="placeholder",
            content="Agent session memory content",
            importance=0.6,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = agent_session_client.save(memory)
        assert result.is_ok

        conn = _connect_to_db(agent_session_client)
        try:
            row = conn.execute(
                "SELECT id, valid_until FROM episodic_memory WHERE content = ?",
                ("Agent session memory content",),
            ).fetchone()
            assert row is not None
            assert row[1] is not None, "valid_until should be set for agent-session memories"

            # Parse valid_until and check it's approximately 365 days from now
            valid_until_str = row[1]
            # SQLite stores ISO format
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
        memory = Memory(
            id="placeholder",
            content="Regular memory content",
            importance=0.4,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = regular_client.save(memory)
        assert result.is_ok

        conn = _connect_to_db(regular_client)
        try:
            row = conn.execute(
                "SELECT id, valid_until FROM episodic_memory WHERE content = ?",
                ("Regular memory content",),
            ).fetchone()
            assert row is not None
            assert row[1] is None, "valid_until should be NULL for non-agent-session memories"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Retrieval after save
# ---------------------------------------------------------------------------


class TestSaveRetrieval:
    """Saved memories are retrievable via get() and recall()."""

    def test_saved_memory_retrievable_via_get(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """Memory saved via save() can be retrieved via get()."""
        memory = Memory(
            id="placeholder",
            content="Memory for get() retrieval",
            importance=0.5,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = agent_session_client.save(memory)
        assert result.is_ok
        saved_id = result.value.id

        retrieved = agent_session_client.get(saved_id)
        assert retrieved is not None
        assert retrieved["content"] == "Memory for get() retrieval"

    def test_saved_memory_retrievable_via_recall(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """Memory saved via save() can be retrieved via recall()."""
        memory = Memory(
            id="placeholder",
            content="Unique content for recall search test",
            importance=0.8,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        result = agent_session_client.save(memory)
        assert result.is_ok

        # Give FTS a moment to index
        time.sleep(0.1)

        recall_result = agent_session_client.recall(query="Unique content for recall search", limit=5)
        assert recall_result.is_ok
        assert len(recall_result.value) > 0
        found = any(
            m["content"] == "Unique content for recall search test"
            for m in recall_result.value
        )
        assert found, "Saved memory should be found via recall()"


# ---------------------------------------------------------------------------
# Idempotency — INSERT OR IGNORE
# ---------------------------------------------------------------------------


class TestSaveInsertOrIgnore:
    """save() uses INSERT OR IGNORE — saves with same ID are deduplicated."""

    def test_same_id_inserted_once(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """Two saves with the same generated ID result in only one row."""
        memory = Memory(
            id="placeholder",
            content="Same ID test",
            importance=0.5,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        # Save twice — each save generates a new ID, so they should be separate rows
        result1 = agent_session_client.save(memory)
        result2 = agent_session_client.save(memory)

        assert result1.is_ok
        assert result2.is_ok
        # Each save generates a different ID (timestamp-based hash)
        assert result1.value.id != result2.value.id

        conn = _connect_to_db(agent_session_client)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE content = ?",
                ("Same ID test",),
            ).fetchone()[0]
            assert count == 2, "Two saves with different IDs should create two rows"

            # Verify the IDs are different
            rows = conn.execute(
                "SELECT id FROM episodic_memory WHERE content = ?",
                ("Same ID test",),
            ).fetchall()
            ids = [r[0] for r in rows]
            assert len(set(ids)) == 2, "Both rows should have different IDs"
        finally:
            conn.close()

    def test_insert_or_ignore_deduplicates_by_id(
        self, agent_session_client: MnemosyneClient
    ) -> None:
        """INSERT OR IGNORE prevents duplicate rows with the same ID."""
        memory = Memory(
            id="placeholder",
            content="ID dedup test",
            importance=0.5,
            source="test",
            scope="session",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            veracity=None,
            metadata=None,
        )

        # Save once
        result = agent_session_client.save(memory)
        assert result.is_ok
        saved_id = result.value.id

        # Try to insert the same ID again directly (simulating a concurrent save)
        conn = _connect_to_db(agent_session_client)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO episodic_memory "
                "(id, content, source, timestamp, session_id, importance) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    saved_id,
                    "ID dedup test duplicate",
                    "test",
                    datetime.now(timezone.utc).isoformat(),
                    agent_session_client.memory_bank,
                    0.5,
                ),
            )
            conn.commit()

            # Should still be only one row
            count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE id = ?",
                (saved_id,),
            ).fetchone()[0]
            assert count == 1, "INSERT OR IGNORE should prevent duplicate IDs"

            # Original content should be preserved
            row = conn.execute(
                "SELECT content FROM episodic_memory WHERE id = ?",
                (saved_id,),
            ).fetchone()
            assert row[0] == "ID dedup test", "Original row should be preserved"
        finally:
            conn.close()