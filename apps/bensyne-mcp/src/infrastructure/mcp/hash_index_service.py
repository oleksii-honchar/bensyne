"""HashIndexService — chunk hash → memory_id deduplication.

SQLAlchemy-backed SQLite hash index with Result-returning methods.
Includes utility methods for extracting chunk hashes from memory arguments.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text, create_engine, event, inspect
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

    Maps a chunk content hash to the Mnemosyne memory_id for deduplication.
    """

    __tablename__ = "hash_index"

    chunk_hash: Mapped[str] = mapped_column(Text, primary_key=True)
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

    def _migrate_legacy_schema(self) -> None:
        """Migrate a legacy file_hash-keyed hash_index table to the chunk_hash schema.

        One-time, idempotent migration: the legacy table is dropped and
        recreated with the new chunk_hash primary key. Rows are NOT copied —
        legacy keys are file hashes (a different value space from chunk
        content hashes), so copying would produce incorrect dedup entries.
        """
        inspector = inspect(self._engine)
        if not inspector.has_table("hash_index"):
            return
        columns = {column["name"] for column in inspector.get_columns("hash_index")}
        if "file_hash" in columns:
            logger.info(
                "Migrating legacy file_hash hash_index table to chunk_hash schema",
                db_path=str(self._db_path),
            )
            HashIndexRow.__table__.drop(self._engine)

    def _ensure_tables(self) -> None:
        """Create the hash_index table, migrating a legacy schema if present."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_schema()
        _HashIndexBase.metadata.create_all(self._engine)

    def get_session(self) -> Session:
        """Return a new Session bound to the engine."""
        return self._session_factory()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class HashIndexService:
    """SQLAlchemy-backed hash index mapping chunk_hash → memory_id.

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
    def has_chunk_hash(arguments: dict[str, Any]) -> bool:
        """Return True if the memory arguments contain a chunk_hash in metadata."""
        metadata = arguments.get("metadata")
        if not isinstance(metadata, dict):
            return False
        return "chunk_hash" in metadata

    @staticmethod
    def extract_chunk_hash(arguments: dict[str, Any]) -> str | None:
        """Extract the chunk_hash from memory arguments metadata, or None if absent."""
        metadata = arguments.get("metadata")
        if not isinstance(metadata, dict):
            return None
        return metadata.get("chunk_hash")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def lookup(self, chunk_hash: str) -> Result[str | None]:
        """Return memory_id for the given chunk_hash, or None if not found."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(HashIndexRow, chunk_hash)
                return Result.ok(row.memory_id if row else None)
            except Exception as exc:
                logger.error("HashIndex lookup failed", memory_bank=self.memory_bank, error=str(exc))
                return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
            finally:
                session.close()

    def store(self, chunk_hash: str, memory_id: str) -> Result[None]:
        """Insert or replace the mapping for chunk_hash → memory_id."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(HashIndexRow, chunk_hash)
                if row is None:
                    row = HashIndexRow(chunk_hash=chunk_hash, memory_id=memory_id)
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

        Returns the chunk_hash that was removed, or None if no entry found.
        """
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.query(HashIndexRow).filter_by(memory_id=memory_id).first()
                if row is None:
                    return Result.ok(None)
                chunk_hash = row.chunk_hash
                session.delete(row)
                session.commit()
                return Result.ok(chunk_hash)
            except Exception as exc:
                session.rollback()
                logger.error("HashIndex remove failed", memory_bank=self.memory_bank, error=str(exc))
                return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
            finally:
                session.close()
