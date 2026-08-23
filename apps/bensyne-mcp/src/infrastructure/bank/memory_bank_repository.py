"""MemoryBankRepository — SQLAlchemy-backed persistence for memory_banks.db.

Follows the HashIndexService/D28 storage pattern: SQLite via SQLAlchemy 2.0
(``Mapped``/``mapped_column``), WAL mode, idempotent ``create_all`` fresh
bootstrap (no migration framework — DEC-0008 precedent), Result-returning
methods, and ``ON CONFLICT(name) DO UPDATE`` for upsert (never
``INSERT OR REPLACE``). The method contract matches the existing
``InMemoryMemoryBankRepository`` test fake exactly.

The aggregate's ``memories`` collection is NOT persisted (spec §4.1 binding
contract — memories live in mnemosyne.db); ``memory_count`` is denormalized
bookkeeping. Timestamps are stored as ISO-8601 UTC strings and parsed back to
``datetime`` on read.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Integer, Text, create_engine, event, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.domain.memory_bank_aggregate import MemoryBank
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)


def memory_banks_db_path(data_dir: str | Path) -> Path:
    """Return the canonical memory_banks.db path under a data directory.

    Module-level helper that breaks the DI circularity (DEC-0064): the
    repository is constructed with an explicit path while callers that only
    hold a data dir can resolve the db location without importing the router.
    """
    return Path(data_dir) / "memory_banks.db"


# ---------------------------------------------------------------------------
# ORM model (co-located)
# ---------------------------------------------------------------------------


class _MemoryBankBase(DeclarativeBase):
    """Declarative base for the memory_banks table."""

    pass


class MemoryBankRow(_MemoryBankBase):
    """Row in the `memory_banks` table — mirrors the MemoryBank aggregate.

    Timestamps are stored as ISO-8601 UTC strings (TEXT columns).
    """

    __tablename__ = "memory_banks"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="registered", server_default="registered"
    )
    created_at: Mapped[str | None] = mapped_column(Text)
    last_accessed: Mapped[str | None] = mapped_column(Text)
    memory_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


# ---------------------------------------------------------------------------
# Timestamp serialization
# ---------------------------------------------------------------------------


def _to_iso8601_utc(value: datetime) -> str:
    """Serialize a datetime to an ISO-8601 UTC string.

    Aware datetimes are converted to UTC; naive datetimes are interpreted as
    UTC (the codebase convention for naive-UTC timestamps) so the stored value
    always carries a ``+00:00`` offset.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _from_iso8601_utc(value: str) -> datetime:
    """Parse an ISO-8601 string back into a timezone-aware datetime."""
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class _MemoryBankConnection:
    """SQLAlchemy engine + session factory for the memory_banks.db file.

    Manages WAL mode and idempotent table creation. Thread-safe via
    per-operation locking on sessions.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._engine = self._create_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._ensure_tables()

    def _create_engine(self) -> Engine:
        """Create a SQLAlchemy Engine with WAL journal mode for this database."""

        def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(engine, "connect", _set_sqlite_pragma)
        return engine

    def _ensure_tables(self) -> None:
        """Bootstrap the memory_banks table on a fresh database (D28 pattern).

        Idempotent: ``create_all`` is a no-op when the table already exists.
        No versioning, no migration framework.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        _MemoryBankBase.metadata.create_all(self._engine)

    def get_session(self) -> Session:
        """Return a new Session bound to the engine."""
        return self._session_factory()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class MemoryBankRepository:
    """SQLAlchemy-backed repository for MemoryBank aggregates.

    Persists the scalar fields (name, description, status, created_at,
    last_accessed, memory_count); the ``memories`` collection is ignored.
    Contract matches ``InMemoryMemoryBankRepository``: ``save``/``find_by_id``/
    ``list`` return ``Result``, ``delete`` returns a plain bool.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn = _MemoryBankConnection(self._db_path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, aggregate: MemoryBank) -> Result[None]:
        """Upsert a MemoryBank aggregate by name.

        ``INSERT ... ON CONFLICT(name) DO UPDATE`` — never ``INSERT OR
        REPLACE`` (which would drop foreign-key references). Memories are
        ignored (not persisted). Structured logging on upsert.
        """
        with self._lock:
            session = self._conn.get_session()
            try:
                stmt = insert(MemoryBankRow).values(
                    name=aggregate.name,
                    description=aggregate.description,
                    status=aggregate.status,
                    created_at=_to_iso8601_utc(aggregate.created_at),
                    last_accessed=(
                        _to_iso8601_utc(aggregate.last_accessed)
                        if aggregate.last_accessed is not None
                        else None
                    ),
                    memory_count=aggregate.memory_count,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[MemoryBankRow.name],
                    set_={
                        "description": stmt.excluded.description,
                        "status": stmt.excluded.status,
                        "created_at": stmt.excluded.created_at,
                        "last_accessed": stmt.excluded.last_accessed,
                        "memory_count": stmt.excluded.memory_count,
                    },
                )
                session.execute(stmt)
                session.commit()
                logger.info(
                    "memory bank upserted",
                    name=aggregate.name,
                    status=aggregate.status,
                    memory_count=aggregate.memory_count,
                )
                return Result.ok(None)
            except Exception as exc:
                session.rollback()
                logger.error(
                    "memory bank save failed",
                    name=aggregate.name,
                    error=str(exc),
                )
                return Result.ko(
                    errors=[ErrorWithDetails("MEMORY_BANK_STORE_ERROR", {"detail": str(exc)})]
                )
            finally:
                session.close()

    def find_by_id(self, bank_name: str) -> Result[MemoryBank | None]:
        """Return the aggregate by name (memories=[]), or None if absent."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(MemoryBankRow, bank_name)
                if row is None:
                    return Result.ok(None)
                return Result.ok(self._to_aggregate(row))
            except Exception as exc:
                logger.error(
                    "memory bank find failed",
                    bank_name=bank_name,
                    error=str(exc),
                )
                return Result.ko(
                    errors=[ErrorWithDetails("MEMORY_BANK_READ_ERROR", {"detail": str(exc)})]
                )  # type: ignore[return-value]
            finally:
                session.close()

    def list(self) -> Result[list[MemoryBank]]:
        """Return all banks, ordered by name (memories=[])."""
        with self._lock:
            session = self._conn.get_session()
            try:
                rows = session.execute(
                    select(MemoryBankRow).order_by(MemoryBankRow.name)
                ).scalars().all()
                return Result.ok([self._to_aggregate(row) for row in rows])
            except Exception as exc:
                logger.error("memory bank list failed", error=str(exc))
                return Result.ko(
                    errors=[ErrorWithDetails("MEMORY_BANK_READ_ERROR", {"detail": str(exc)})]
                )  # type: ignore[return-value]
            finally:
                session.close()

    def delete(self, bank_name: str) -> bool:
        """Delete a bank by name. Returns True when deleted, False when absent."""
        with self._lock:
            session = self._conn.get_session()
            try:
                row = session.get(MemoryBankRow, bank_name)
                if row is None:
                    return False
                session.delete(row)
                session.commit()
                return True
            except Exception as exc:
                session.rollback()
                logger.error(
                    "memory bank delete failed",
                    bank_name=bank_name,
                    error=str(exc),
                )
                return False
            finally:
                session.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_aggregate(self, row: MemoryBankRow) -> MemoryBank:
        """Rehydrate a MemoryBank aggregate from a persisted row.

        Timestamps are parsed back from ISO-8601 UTC strings; memories are
        always rehydrated as an empty collection (never persisted).
        """
        return MemoryBank(
            name=row.name,
            description=row.description,
            status=row.status,
            created_at=_from_iso8601_utc(row.created_at) if row.created_at else datetime.now(timezone.utc),
            last_accessed=(
                _from_iso8601_utc(row.last_accessed) if row.last_accessed is not None else None
            ),
            memory_count=row.memory_count,
            memories=[],
        )
