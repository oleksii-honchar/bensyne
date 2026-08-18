"""SQLAlchemy ORM model tests — verify models map correctly to the SQLite schema.

Tests that:
- ORM models can be created and persisted via SQLAlchemy Session
- ORM models round-trip correctly (save → retrieve)
- ORM models map to the same schema as the raw SQL migrations
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.models import (
    Base,
    FileChunkORM,
    FileORM,
    FileRelationORM,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_bank_dir(tmp_path: Path) -> Path:
    """Return a temporary directory simulating a memory bank's data dir."""
    return tmp_path / "test_bank"


@pytest.fixture
def manager(tmp_bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Create a FileMetadataConnectionManager backed by a temporary directory."""
    mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
    yield mgr
    mgr.close()


@pytest.fixture
def session(manager: FileMetadataConnectionManager) -> Generator:
    """Create a SQLAlchemy Session with auto-flush disabled for explicit control."""
    from sqlalchemy.orm import Session

    s = Session(bind=manager.engine, autoflush=False)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HASH = "a" * 64


# ---------------------------------------------------------------------------
# FileORM model tests
# ---------------------------------------------------------------------------


class TestFileORM:
    """FileORM model maps correctly to the files table."""

    def test_create_and_persist_file_orm(self, session: Session) -> None:
        """FileORM instance can be created, added, and flushed to DB."""
        orm_file = FileORM(
            id="orm1",
            path="/tmp/orm_test.py",
            source_type="vault",
            file_hash=VALID_HASH,
            file_type="python",
            size=1024,
            language="python",
            status="indexed",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        # Retrieve via raw SQL to verify it was persisted
        import sqlite3

        raw_conn = sqlite3.connect(str(session.get_bind().url.database))
        raw_conn.row_factory = sqlite3.Row
        cursor = raw_conn.execute("SELECT * FROM files WHERE id = ?", ("orm1",))
        row = cursor.fetchone()
        raw_conn.close()

        assert row is not None
        assert row["path"] == "/tmp/orm_test.py"
        assert row["file_type"] == "python"
        assert row["size"] == 1024
        assert row["language"] == "python"
        assert row["status"] == "indexed"

    def test_file_orm_round_trip(self, session: Session) -> None:
        """FileORM save → retrieve via Session returns correct values."""
        orm_file = FileORM(
            id="orm2",
            path="/tmp/roundtrip.py",
            source_type="obsidian",
            file_hash=VALID_HASH,
            file_type="python",
            size=2048,
            language="python",
            status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        retrieved = session.get(FileORM, "orm2")
        assert retrieved is not None
        assert retrieved.path == "/tmp/roundtrip.py"
        assert retrieved.source_type == "obsidian"
        assert retrieved.file_type == "python"
        assert retrieved.size == 2048
        assert retrieved.language == "python"
        assert retrieved.status == "pending"

    def test_file_orm_with_optional_fields_none(self, session: Session) -> None:
        """FileORM with None optional fields persists correctly."""
        orm_file = FileORM(
            id="orm3",
            path="/tmp/minimal.txt",
            source_type="vault",
            status="pending",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        retrieved = session.get(FileORM, "orm3")
        assert retrieved is not None
        assert retrieved.file_hash is None
        assert retrieved.file_type is None
        assert retrieved.size is None
        assert retrieved.language is None

    def test_file_orm_with_json_fields(self, session: Session) -> None:
        """FileORM with JSON-encoded keywords/tags persists correctly."""
        import json

        orm_file = FileORM(
            id="orm4",
            path="/tmp/with_json.py",
            source_type="agent-sessions",
            keywords=json.dumps(["domain", "entity"]),
            tags=json.dumps(["core", "important"]),
            status="indexed",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        retrieved = session.get(FileORM, "orm4")
        assert retrieved is not None
        assert json.loads(retrieved.keywords) == ["domain", "entity"]
        assert json.loads(retrieved.tags) == ["core", "important"]

    def test_file_orm_update_existing(self, session: Session) -> None:
        """FileORM can update an existing row."""
        orm_file = FileORM(
            id="orm5",
            path="/tmp/old.py",
            source_type="vault",
            status="pending",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        retrieved = session.get(FileORM, "orm5")
        assert retrieved is not None
        retrieved.path = "/tmp/updated.py"
        retrieved.status = "indexed"
        session.commit()

        updated = session.get(FileORM, "orm5")
        assert updated.path == "/tmp/updated.py"
        assert updated.status == "indexed"

    def test_file_orm_delete(self, session: Session) -> None:
        """FileORM can delete a row."""
        orm_file = FileORM(
            id="orm6",
            path="/tmp/deletable.py",
            source_type="vault",
            status="pending",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        session.delete(orm_file)
        session.commit()

        deleted = session.get(FileORM, "orm6")
        assert deleted is None

    def test_file_orm_query_by_path(self, session: Session) -> None:
        """FileORM can be queried by path."""
        orm_file = FileORM(
            id="orm7",
            path="/tmp/unique_path.py",
            source_type="vault",
            status="pending",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        result = session.query(FileORM).filter(FileORM.path == "/tmp/unique_path.py").one_or_none()
        assert result is not None
        assert result.id == "orm7"

    def test_file_orm_list_all_ordered(self, session: Session) -> None:
        """FileORM can list all files ordered by created_at DESC."""
        now = datetime.now()
        orm1 = FileORM(id="orm8a", path="/tmp/a.py", source_type="vault", status="pending", created_at=now)
        orm2 = FileORM(id="orm8b", path="/tmp/b.py", source_type="vault", status="pending", created_at=now)
        session.add_all([orm1, orm2])
        session.commit()

        results = session.query(FileORM).order_by(FileORM.created_at.desc()).all()
        assert len(results) == 2

    def test_file_orm_summary_field(self, session: Session) -> None:
        """FileORM summary column (V5 migration) persists correctly."""
        orm_file = FileORM(
            id="orm9",
            path="/tmp/with_summary.py",
            source_type="vault",
            status="pending",
            summary="This is a summary",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        retrieved = session.get(FileORM, "orm9")
        assert retrieved is not None
        assert retrieved.summary == "This is a summary"


# ---------------------------------------------------------------------------
# FileChunkORM model tests
# ---------------------------------------------------------------------------


class TestFileChunkORM:
    """FileChunkORM model maps correctly to the file_chunks table."""

    def test_create_and_persist_chunk_orm(self, session: Session) -> None:
        """FileChunkORM can be created and persisted."""
        # First create a file (FK constraint)
        orm_file = FileORM(
            id="fc1", path="/tmp/chunk_file.py", source_type="vault", status="pending", created_at=datetime.now()
        )
        session.add(orm_file)
        session.flush()

        chunk = FileChunkORM(
            id="fc_orm1",
            file_id="fc1",
            memory_id="mem1",
            chunk_index=0,
            start_line=1,
            end_line=50,
            content_hash="c" * 64,
            content_type="code",
            is_partial=False,
            created_at=datetime.now(),
        )
        session.add(chunk)
        session.commit()

        retrieved = session.get(FileChunkORM, ("fc1", "mem1"))
        assert retrieved is not None
        assert retrieved.chunk_index == 0
        assert retrieved.start_line == 1
        assert retrieved.end_line == 50
        assert retrieved.content_hash == "c" * 64
        assert retrieved.content_type == "code"
        assert retrieved.is_partial is False

    def test_chunk_orm_ordered_by_chunk_index(self, session: Session) -> None:
        """FileChunkORM can be queried ordered by chunk_index."""
        orm_file = FileORM(
            id="fc2", path="/tmp/ordered.py", source_type="vault", status="pending", created_at=datetime.now()
        )
        session.add(orm_file)
        session.flush()

        c2 = FileChunkORM(id="fc_orm2", file_id="fc2", memory_id="m2", chunk_index=2, created_at=datetime.now())
        c0 = FileChunkORM(id="fc_orm0", file_id="fc2", memory_id="m0", chunk_index=0, created_at=datetime.now())
        c1 = FileChunkORM(id="fc_orm1", file_id="fc2", memory_id="m1", chunk_index=1, created_at=datetime.now())
        session.add_all([c2, c0, c1])
        session.commit()

        results = (
            session.query(FileChunkORM)
            .filter(FileChunkORM.file_id == "fc2")
            .order_by(FileChunkORM.chunk_index.asc())
            .all()
        )
        assert len(results) == 3
        assert results[0].chunk_index == 0
        assert results[1].chunk_index == 1
        assert results[2].chunk_index == 2


# ---------------------------------------------------------------------------
# FileRelationORM model tests
# ---------------------------------------------------------------------------


class TestFileRelationORM:
    """FileRelationORM model maps correctly to the file_relations table."""

    def test_create_and_persist_relation_orm(self, session: Session) -> None:
        """FileRelationORM can be created and persisted."""
        f1 = FileORM(
            id="fr1", path="/tmp/src.py", source_type="vault", status="pending", created_at=datetime.now()
        )
        f2 = FileORM(
            id="fr2", path="/tmp/tgt.py", source_type="vault", status="pending", created_at=datetime.now()
        )
        session.add_all([f1, f2])
        session.flush()

        rel = FileRelationORM(
            id="fr_orm1",
            source_file_id="fr1",
            target_file_id="fr2",
            relation_type="parent_child",
            strength=0.9,
            direction="unidirectional",
            description="Parent-child",
            created_at=datetime.now(),
        )
        session.add(rel)
        session.commit()

        retrieved = session.get(FileRelationORM, ("fr1", "fr2", "parent_child"))
        assert retrieved is not None
        assert retrieved.strength == 0.9
        assert retrieved.direction == "unidirectional"
        assert retrieved.description == "Parent-child"

    def test_relation_orm_query_by_file_id(self, session: Session) -> None:
        """FileRelationORM can be queried where file is source or target."""
        f1 = FileORM(id="fr3", path="/tmp/a.py", source_type="vault", status="pending", created_at=datetime.now())
        f2 = FileORM(id="fr4", path="/tmp/b.py", source_type="vault", status="pending", created_at=datetime.now())
        session.add_all([f1, f2])
        session.flush()

        rel1 = FileRelationORM(
            id="fr_orm3",
            source_file_id="fr3",
            target_file_id="fr4",
            relation_type="sibling",
            strength=1.0,
            created_at=datetime.now(),
        )
        session.add(rel1)
        session.commit()

        results = (
            session.query(FileRelationORM)
            .filter((FileRelationORM.source_file_id == "fr3") | (FileRelationORM.target_file_id == "fr3"))
            .all()
        )
        assert len(results) == 1
        assert results[0].id == "fr_orm3"

    def test_relation_orm_query_by_type(self, session: Session) -> None:
        """FileRelationORM can be queried by relation_type."""
        f1 = FileORM(id="fr5", path="/tmp/x.py", source_type="vault", status="pending", created_at=datetime.now())
        f2 = FileORM(id="fr6", path="/tmp/y.py", source_type="vault", status="pending", created_at=datetime.now())
        session.add_all([f1, f2])
        session.flush()

        rel1 = FileRelationORM(
            id="fr_orm5",
            source_file_id="fr5",
            target_file_id="fr6",
            relation_type="dependency",
            strength=0.5,
            created_at=datetime.now(),
        )
        session.add(rel1)
        session.commit()

        results = session.query(FileRelationORM).filter(FileRelationORM.relation_type == "dependency").all()
        assert len(results) == 1


# ---------------------------------------------------------------------------
# FTS5 compatibility
# ---------------------------------------------------------------------------


class TestFTS5Compatibility:
    """FTS5 virtual table still works after ORM models are in place."""

    def test_fts5_table_exists(self, manager: FileMetadataConnectionManager) -> None:
        """FTS5 virtual table is still present in the schema."""
        import sqlite3

        conn = sqlite3.connect(str(manager.db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files_fts'")
            row = cursor.fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_fts5_search_still_works(self, session: Session) -> None:
        """Saving via ORM still populates FTS5 index."""
        orm_file = FileORM(
            id="fts_orm1",
            path="/tmp/fts_searchable.py",
            source_type="vault",
            status="pending",
            created_at=datetime.now(),
        )
        session.add(orm_file)
        session.commit()

        # Search via raw SQL on FTS5
        import sqlite3

        conn = sqlite3.connect(str(session.get_bind().url.database))
        try:
            cursor = conn.execute(
                """SELECT f.* FROM files f
                   INNER JOIN files_fts ON files_fts.rowid = f.rowid
                   WHERE files_fts MATCH ?""",
                ("fts_searchable",),
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
        finally:
            conn.close()
