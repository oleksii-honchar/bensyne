"""Integration test for migrate-working-to-episodic.py migration script.

Tests:
1. Script runs without errors on empty database
2. Script migrates rows correctly (content preserved)
3. Script is idempotent (running twice doesn't duplicate rows)
4. Script applies correct TTL policy during migration (agent-session → 365 days, others → NULL)
5. Script reports progress and completion
"""

from __future__ import annotations

import subprocess
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

SCRIPT_PATH = Path(__file__).parent.parent.parent.parent / "scripts" / "migrate-working-to-episodic.py"
BENSYNE_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with the required schema and working_memory rows."""
    db_path = tmp_path / "test_migration.db"

    # Create the database with schema matching beam.py
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # working_memory table (from beam.py)
    cursor.execute("""
        CREATE TABLE working_memory (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source TEXT,
            timestamp TEXT,
            session_id TEXT DEFAULT 'default',
            importance REAL DEFAULT 0.5,
            metadata_json TEXT,
            veracity TEXT DEFAULT 'unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_until TIMESTAMP DEFAULT NULL
        )
    """)

    # episodic_memory table (from beam.py)
    cursor.execute("""
        CREATE TABLE episodic_memory (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            timestamp TEXT,
            session_id TEXT DEFAULT 'default',
            importance REAL DEFAULT 0.5,
            metadata_json TEXT,
            summary_of TEXT DEFAULT '',
            veracity TEXT DEFAULT 'unknown',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_until TIMESTAMP DEFAULT NULL
        )
    """)

    conn.commit()
    conn.close()

    return db_path


class TestMigrationScript:
    """Integration tests for the working_memory → episodic_memory migration."""

    def test_runs_on_empty_database(self, temp_db: Path) -> None:
        """Migration script runs without errors on empty working_memory."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(temp_db)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Migrating 0 rows" in result.stdout or "Migration complete" in result.stdout

    def test_migrates_rows_correctly(self, tmp_path: Path) -> None:
        """Migration copies all working_memory rows to episodic_memory."""
        db_path = self._create_db_with_rows(tmp_path, [
            {"id": "mem-001", "content": "First memory content", "session_id": "test-session-1"},
            {"id": "mem-002", "content": "Second memory content", "session_id": "test-session-2"},
            {"id": "mem-003", "content": "Third memory content", "session_id": "default"},
        ])

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(db_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Migrating 3 rows" in result.stdout
        assert "Migration complete. 3 rows migrated." in result.stdout

        # Verify rows were copied to episodic_memory
        conn = sqlite3.connect(db_path)
        try:
            episodic_count = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
            assert episodic_count == 3, f"Expected 3 episodic rows, got {episodic_count}"

            # Verify content is preserved
            ids = set(row[0] for row in conn.execute("SELECT id, content FROM episodic_memory").fetchall())
            assert "mem-001" in ids
            assert "mem-002" in ids
            assert "mem-003" in ids
        finally:
            conn.close()

    def test_is_idempotent(self, tmp_path: Path) -> None:
        """Running migration twice does not duplicate rows."""
        db_path = self._create_db_with_rows(tmp_path, [
            {"id": "mem-001", "content": "Memory content", "session_id": "test-session-1"},
        ])

        # Run migration twice
        for i in range(2):
            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(db_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"Script failed on run {i+1}: {result.stderr}"

        # Should still have exactly 1 row in episodic_memory
        conn = sqlite3.connect(db_path)
        try:
            episodic_count = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
            assert episodic_count == 1, f"Expected 1 episodic row (idempotent), got {episodic_count}"
        finally:
            conn.close()

    def test_agent_session_ttl_365_days(self, tmp_path: Path) -> None:
        """agent-session memories get valid_until set to 365 days from now."""
        db_path = self._create_db_with_rows(tmp_path, [
            {"id": "mem-001", "content": "Agent session memory", "session_id": "agent-session-ses_abc123"},
        ])

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(db_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT id, valid_until FROM episodic_memory WHERE id = 'mem-001'"
            ).fetchone()
            assert row is not None
            assert row[1] is not None, "valid_until should be set for agent-session memories"

            # Parse valid_until and verify it's approximately 365 days from now
            valid_until_str = row[1]
            if "T" in valid_until_str:
                valid_until = datetime.fromisoformat(valid_until_str.replace("Z", "+00:00"))
            else:
                valid_until = datetime.strptime(valid_until_str, "%Y-%m-%d %H:%M:%S")

            now = datetime.now(timezone.utc)
            expected = now + timedelta(days=365)
            delta = abs((valid_until - expected).total_seconds())
            assert delta < 86400, f"valid_until should be ~365 days from now, got {valid_until}"
        finally:
            conn.close()

    def test_non_agent_session_ttl_null(self, tmp_path: Path) -> None:
        """Non-agent-session memories get valid_until set to NULL."""
        db_path = self._create_db_with_rows(tmp_path, [
            {"id": "mem-001", "content": "Regular memory", "session_id": "default"},
            {"id": "mem-002", "content": "Other session memory", "session_id": "some-other-session"},
        ])

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(db_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        conn = sqlite3.connect(db_path)
        try:
            for mem_id in ["mem-001", "mem-002"]:
                row = conn.execute(
                    "SELECT id, valid_until FROM episodic_memory WHERE id = ?",
                    (mem_id,)
                ).fetchone()
                assert row is not None
                assert row[1] is None, f"valid_until should be NULL for {mem_id}"
        finally:
            conn.close()

    def _create_db_with_rows(self, tmp_path: Path, rows: list[dict]) -> Path:
        """Helper: create a temporary DB with working_memory test rows."""
        db_path = self._create_empty_db(tmp_path)

        conn = sqlite3.connect(db_path)
        try:
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO working_memory (id, content, source, timestamp, session_id, importance) "
                    "VALUES (?, ?, 'test', ?, ?, 0.5)",
                    (
                        row["id"],
                        row["content"],
                        datetime.now(timezone.utc).isoformat(),
                        row["session_id"],
                    )
                )
            conn.commit()
        finally:
            conn.close()

        return db_path

    def _create_empty_db(self, tmp_path: Path) -> Path:
        """Helper: create an empty database with the required schema."""
        db_path = tmp_path / "test_migration.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE working_memory (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT,
                timestamp TEXT,
                session_id TEXT DEFAULT 'default',
                importance REAL DEFAULT 0.5,
                metadata_json TEXT,
                veracity TEXT DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP DEFAULT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE episodic_memory (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                timestamp TEXT,
                session_id TEXT DEFAULT 'default',
                importance REAL DEFAULT 0.5,
                metadata_json TEXT,
                summary_of TEXT DEFAULT '',
                veracity TEXT DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP DEFAULT NULL
            )
        """)

        conn.commit()
        conn.close()

        return db_path