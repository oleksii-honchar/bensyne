"""HashIndexService — file hash → memory_id deduplication.

SQLAlchemy-backed SQLite hash index with Result-returning methods.
Includes utility methods for extracting file hashes from memory arguments.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class _HashIndexBase(DeclarativeBase):
    """Declarative base for the hash index table."""

    pass


class HashIndexRow(_HashIndexBase):
    """Row in the `hash_index` table.

    Maps a file SHA-256 hash to the Mnemosyne memory_id for deduplication.
    """

    __tablename__ = "hash_index"

    file_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    memory_id: Mapped[str] = mapped_column(String(255), nullable=False)

# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

class _HashIndexConnection:
    """Lightweight SQLAlchemy engine + session factory for the hash index DB.

    Manages its own SQLite file, WAL mode, and table creation.
    Thread-safe via per-operation locking on sessions.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._engine = self._create_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._ensure_tables()

    def _create_engine(self) -> Engine:
        """Create a SQLAlchemy Engine for this database."""

        def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        event.listen(Engine, "connect", _set_sqlite_pragma)
        return create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
        )

    def _ensure_tables(self) -> None:
        """Create the hash_index table if it doesn't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        _HashIndexBase.metadata.create_all(self._engine)

    def get_session(self) -> Session:
        """Return a new Session bound to the engine."""
        return self._session_factory()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class HashIndexService:
    """SQLAlchemy-backed hash index mapping file_hash → memory_id.

    Thread-safe via per-operation locking. Uses WAL mode for concurrent reads.
    Database is created lazily on first use; parent directory is created if needed.
    All methods return Result[T] for domain-layer integration.
    """

    def __init__(self, memory_bank: str, db_path: Path | None = None) -> None:
        self.memory_bank = memory_bank
        if db_path is None:
            db_path = Path("data") / memory_bank / "hash_index.db"
        self._conn = _HashIndexConnection(db_path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Utility helpers (moved from deduplication.py)
    # ------------------------------------------------------------------

    @staticmethod
    def is_file_based_memory(arguments: dict[str, Any]) -> bool:
        """Return True if the memory arguments contain a fileHash in metadata."""
        metadata = arguments.get("metadata")
        if not isinstance(metadata, dict):
            return False
        return "fileHash" in metadata

    @staticmethod
    def extract_file_hash(arguments: dict[str, Any]) -> str | None:
        """Extract the fileHash from memory arguments metadata, or None if absent."""
        metadata = arguments.get("metadata")
        if not isinstance(metadata, dict):
            return None
        return metadata.get("fileHash")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def lookup(self, file_hash: str) -> Result[str | None]:
        """Return memory_id for the given file_hash, or None if not found."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(HashIndexRow, file_hash)
                return Result.ok(row.memory_id if row else None)
            except Exception as exc:
                logger.error("HashIndex lookup failed", memory_bank=self.memory_bank, error=str(exc))
                return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
            finally:
                session.close()

    def store(self, file_hash: str, memory_id: str) -> Result[None]:
        """Insert or replace the mapping for file_hash → memory_id."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(HashIndexRow, file_hash)
                if row is None:
                    row = HashIndexRow(file_hash=file_hash, memory_id=memory_id)
                    session.add(row)
                else:
                    row.memory_id = memory_id
                session.commit()
                return Result.ok(None)
            except Exception as exc:
                session.rollback()
                logger.error("HashIndex store failed", memory_bank=self.memory_bank, error=str(exc))
                return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
            finally:
                session.close()

    def remove(self, memory_id: str) -> Result[str | None]:
        """Remove the hash entry for a given memory_id.

        Returns the file_hash that was removed, or None if no entry found.
        """
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.query(HashIndexRow).filter_by(memory_id=memory_id).first()
                if row is None:
                    return Result.ok(None)
                file_hash = row.file_hash
                session.delete(row)
                session.commit()
                return Result.ok(file_hash)
            except Exception as exc:
                session.rollback()
                logger.error("HashIndex remove failed", memory_bank=self.memory_bank, error=str(exc))
                return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
            finally:
                session.close()
