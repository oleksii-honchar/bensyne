"""SQLite-backed hash index for file hash → memory_id deduplication."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS hash_index (
    file_hash TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL
);
"""

INSERT_SQL = "INSERT OR REPLACE INTO hash_index (file_hash, memory_id) VALUES (?, ?)"

LOOKUP_SQL = "SELECT memory_id FROM hash_index WHERE file_hash = ?"

REMOVE_BY_MEMORY_ID_SQL = "DELETE FROM hash_index WHERE memory_id = ?"

SELECT_BY_MEMORY_ID_SQL = "SELECT file_hash FROM hash_index WHERE memory_id = ?"


class HashIndex:
    """SQLite-backed hash index mapping file_hash → memory_id.

    Thread-safe via per-connection locking. Uses WAL mode for concurrent reads.
    Database is created lazily on first use; parent directory is created if needed.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create the database file and table if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(CREATE_TABLE_SQL)
                conn.commit()
            finally:
                conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a new connection (thread-safe: each thread gets its own)."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def lookup(self, file_hash: str) -> Optional[str]:
        """Return memory_id for the given file_hash, or None if not found."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(LOOKUP_SQL, (file_hash,))
                row = cursor.fetchone()
                return row[0] if row else None
            finally:
                conn.close()

    def store(self, file_hash: str, memory_id: str) -> None:
        """Insert or replace the mapping for file_hash → memory_id."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(INSERT_SQL, (file_hash, memory_id))
                conn.commit()
            finally:
                conn.close()

    def remove(self, memory_id: str) -> Optional[str]:
        """Remove the hash entry for a given memory_id.

        Returns the file_hash that was removed, or None if no entry found.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(SELECT_BY_MEMORY_ID_SQL, (memory_id,))
                row = cursor.fetchone()
                if row is None:
                    return None
                file_hash = row[0]
                conn.execute(REMOVE_BY_MEMORY_ID_SQL, (memory_id,))
                conn.commit()
                return file_hash
            finally:
                conn.close()
