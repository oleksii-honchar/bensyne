"""FileMetadataConnectionManager — per-bank SQLite connection manager.

Manages SQLite connections for the file metadata layer with:
- Per-bank isolation (each bank has its own file_metadata.db)
- Connection pooling for concurrent access
- Migration support for schema evolution
- WAL mode for concurrent reads
- SQLAlchemy ORM support via Engine and Session
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.storage.sqlite.file_metadata_migrations import MIGRATIONS

if TYPE_CHECKING:
    from src.infrastructure.storage.sqlite.models import Base


class FileMetadataConnectionManager:
    """Manages SQLite connections for per-bank file metadata storage.

    Each memory bank gets its own `file_metadata.db` alongside `mnemosyne.db`.
    Connections are pooled with a configurable maximum pool size. WAL mode is
    enabled for concurrent read access. Migrations are applied on initialization.

    Args:
        bank_dir: Directory containing the memory bank's data files.
        pool_size: Maximum number of concurrent connections (default 5).

    Construction is side-effect-free (lazy contract, Option A): no mkdir, no db
    file, no schema. The DB materializes only on the first write-triggered
    operation via ``_ensure_initialized()`` (mkdir + migrations + engine).
    """

    def __init__(self, bank_dir: Path, pool_size: int = 5) -> None:
        self.bank_dir = Path(bank_dir)
        self.db_path = self.bank_dir / "file_metadata.db"
        self._pool_size = pool_size
        self._pool: list[sqlite3.Connection] = []
        self._active_count = 0
        self._lock = threading.Lock()
        self._closed = False
        self._initialized = False

        # Lazy contract: NO filesystem side effects here. The bank dir and db
        # file materialize on first write-triggered use (_ensure_initialized),
        # so a plain-remember bank never gains a file_metadata.db and stays
        # "pure_memories" for the bank_type_checker file-existence heuristic.
        self._engine: Engine | None = None
        self._session_factory: sessionmaker | None = None

    # ------------------------------------------------------------------
    # Lazy initialization
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Materialize the DB (mkdir + migrations + engine) on first use.

        Idempotent: the work runs once per manager. All write-triggered paths
        (``get_session`` / ``get_connection`` / ``create_tables`` /
        ``check_migrations`` / ``engine``) funnel through here; read paths that
        must not materialize short-circuit at the repository level on
        ``db_path.exists()`` BEFORE calling into this manager.
        """
        if self._initialized:
            return
        if self._closed:
            raise RuntimeError("Connection manager is closed")

        # Ensure parent directory exists
        self.bank_dir.mkdir(parents=True, exist_ok=True)

        # Apply migrations (creates DB and tables if needed)
        self._apply_migrations()

        # SQLAlchemy Engine and Session factory
        self._engine = self._create_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._initialized = True

    # ------------------------------------------------------------------
    # Migration internals
    # ------------------------------------------------------------------

    def _apply_migrations(self) -> None:
        """Apply any pending migrations to the database."""
        current_version = self._get_current_version()

        for migration in MIGRATIONS:
            if migration.version > current_version:
                self._execute_migration(migration)
                current_version = migration.version

    def _get_current_version(self) -> int:
        """Get the current schema version from the database.

        Returns 0 if the schema_version table doesn't exist or is empty.
        """
        conn = self._create_raw_connection()
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if not cursor.fetchone():
                return 0

            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def _execute_migration(self, migration: object) -> None:
        """Execute a single migration.

        Args:
            migration: Migration object with version, up_sql, and description.
        """
        conn = self._create_raw_connection()
        try:
            conn.execute("BEGIN")
            conn.executescript(migration.up_sql)
            # Delete any existing version rows and insert the new one.
            # This avoids the INSERT OR REPLACE pitfall where non-conflicting
            # values create duplicate rows instead of replacing.
            conn.execute("DELETE FROM schema_version")
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (migration.version,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_raw_connection(self) -> sqlite3.Connection:
        """Create a raw SQLite connection without pool management.

        Used internally for migration operations.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _create_engine(self) -> Engine:
        """Create a SQLAlchemy Engine for this database.

        Configures WAL mode and foreign keys via connection events.
        """

        def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

        event.listen(Engine, "connect", _set_sqlite_pragma)
        return create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one.

        Returns:
            A SQLite connection with WAL mode and Row factory enabled.

        Raises:
            RuntimeError: If the manager is closed or pool is exhausted.
        """
        if self._closed:
            raise RuntimeError("Connection manager is closed")

        self._ensure_initialized()

        with self._lock:
            # Try to get an existing connection from the pool
            if self._pool:
                conn = self._pool.pop()
                try:
                    conn.execute("SELECT 1")
                    self._active_count += 1
                    return conn
                except sqlite3.ProgrammingError:
                    # Connection was closed externally, discard
                    pass

            # Check pool size limit
            if self._active_count >= self._pool_size:
                raise RuntimeError(f"Connection pool exhausted (max {self._pool_size} connections)")

        # Create a new connection outside the lock
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row

        with self._lock:
            self._active_count += 1

        return conn

    def close_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool or close it if the manager is closed.

        Args:
            conn: The SQLite connection to close or pool.
        """
        with self._lock:
            self._active_count -= 1

            if self._closed:
                try:
                    conn.close()
                except Exception:
                    pass
                return

            # Verify connection is still valid before pooling
            try:
                conn.execute("SELECT 1")
                if len(self._pool) < self._pool_size:
                    self._pool.append(conn)
                else:
                    conn.close()
            except sqlite3.ProgrammingError:
                # Connection is dead, discard it
                pass

    def close(self) -> None:
        """Close all pooled connections and mark the manager as closed.

        After this call, get_connection() will raise RuntimeError.
        """
        with self._lock:
            self._closed = True
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()

    def create_tables(self) -> None:
        """Create all tables if they don't exist.

        This is idempotent — calling it multiple times is safe.
        Re-applies migrations to ensure schema is up to date. Materializes the
        DB (mkdir + migrations + engine) on first call (lazy contract).
        """
        self._ensure_initialized()

    def check_migrations(self) -> int:
        """Check the current schema version and apply any pending migrations.

        Returns:
            The current schema version after applying any pending migrations.
        """
        self._ensure_initialized()
        return self._get_current_version()

    # ------------------------------------------------------------------
    # SQLAlchemy Session API
    # ------------------------------------------------------------------

    def get_session(self) -> Session:
        """Get a SQLAlchemy Session for ORM operations.

        Returns:
            A new Session bound to the SQLAlchemy Engine.

        Raises:
            RuntimeError: If the manager is closed.
        """
        if self._closed:
            raise RuntimeError("Connection manager is closed")
        self._ensure_initialized()
        session_factory = self._session_factory
        assert session_factory is not None
        return session_factory()

    def close_session(self, session: Session) -> None:
        """Close a SQLAlchemy Session.

        Args:
            session: The Session to close.
        """
        try:
            session.close()
        except Exception:
            pass

    @property
    def engine(self) -> Engine:
        """Return the SQLAlchemy Engine for this database.

        Materializes the DB on first access (lazy contract).
        """
        self._ensure_initialized()
        engine = self._engine
        assert engine is not None
        return engine
