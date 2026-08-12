"""Alembic environment configuration for Bensyne SQLite file metadata database.

Key behaviors:
- Reads the memory bank name from the BENSYNE_MEMORY_BANK environment variable
  (or falls back to the bensyne_bank_dir setting in alembic.ini).
- Constructs the per-bank SQLite URL: sqlite:///data/{bank_name}/file_metadata.db
- Imports the SQLAlchemy models from src.infrastructure.storage.sqlite.models
  for autogenerate support.
- Configures WAL mode and foreign keys on every connection.
"""

from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy import pool

from alembic import context

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Models (for autogenerate support)
# ---------------------------------------------------------------------------

from src.infrastructure.storage.sqlite.models import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Per-bank SQLite URL
# ---------------------------------------------------------------------------

def _get_bank_dir() -> str:
    """Return the bank directory for the current migration.

    Priority:
    1. BENSYNE_MEMORY_BANK environment variable
    2. bensyne_bank_dir setting from alembic.ini
    3. Default: data/default
    """
    import os

    bank_name = os.environ.get("BENSYNE_MEMORY_BANK")
    if bank_name:
        return f"data/{bank_name}"

    bank_dir = config.get_main_option("bensyne_bank_dir")
    if bank_dir:
        return bank_dir

    return "data/default"


def _get_sqlite_url() -> str:
    """Construct the per-bank SQLite database URL."""
    bank_dir = _get_bank_dir()
    db_path = Path(bank_dir) / "file_metadata.db"
    return f"sqlite:///{db_path}"


# ---------------------------------------------------------------------------
# SQLite pragmas
# ---------------------------------------------------------------------------

def _set_sqlite_pragma(dbapi_conn, _record):
    """Enable WAL mode and foreign keys on every Alembic connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = _get_sqlite_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    url = _get_sqlite_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"check_same_thread": False},
    )

    # Enable WAL mode and foreign keys
    event.listen(connectable, "connect", _set_sqlite_pragma)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
