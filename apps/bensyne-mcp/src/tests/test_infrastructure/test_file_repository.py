"""FileRepository tests — SQLite-backed FileRepository implementation.

Tests all repository operations using an in-memory SQLite database via
FileMetadataConnectionManager.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

import pytest

from src.domain.file_entity import File, FileStatus, SourceType
from src.utils.result import Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.infrastructure.storage.sqlite.models import FileORM

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
def repo(manager: FileMetadataConnectionManager) -> Generator[FileRepository, None, None]:
    """Create a FileRepository backed by a temporary database."""
    r = FileRepository(manager)
    yield r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HASH = "a" * 64


def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    # D28: bootstrap DDL freezes the D29 source_type CHECK set; only
    # SourceType.UNKNOWN (the current enum member in that set) is persistable
    # until Task 16 reshapes the enum.
    source_type: SourceType = SourceType.UNKNOWN,
    hash: Optional[str] = None,
    file_type: Optional[str] = None,
    size: Optional[int] = None,
    language: Optional[str] = None,
    aggregated_keywords: Optional[List[str]] = None,
    aggregated_tags: Optional[List[str]] = None,
    status: FileStatus = FileStatus.PENDING,
    total_chunks: int = 0,
    average_importance: float = 0.5,
    metadata: Optional[dict] = None,
    created_at: Optional[datetime] = None,
) -> File:
    """Create a valid File instance with sensible defaults."""
    result = File.of(
        {
            "id": id,
            "path": path,
            "source_type": source_type,
            "hash": hash,
            "file_type": file_type,
            "size": size,
            "language": language,
            "aggregated_keywords": aggregated_keywords or [],
            "aggregated_tags": aggregated_tags or [],
            "status": status,
            "total_chunks": total_chunks,
            "average_importance": average_importance,
            "metadata": metadata or {},
            "created_at": created_at or datetime.now(),
        }
    )
    assert result.is_ok, f"Failed to create test file: {result.errors}"
    return result.value


# ---------------------------------------------------------------------------
# save_file
# ---------------------------------------------------------------------------


class TestSaveFile:
    """save_file persists a File entity to SQLite."""

    def test_save_file_returns_result_ok_with_file(self, repo: FileRepository) -> None:
        file = _a_file(id="s1")
        result = repo.save_file(file)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "s1"

    def test_save_file_persists_and_retrievable(self, repo: FileRepository) -> None:
        file = _a_file(id="s2", path="/tmp/persist.txt")
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("s2")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/persist.txt"

    def test_save_file_overwrites_existing(self, repo: FileRepository) -> None:
        file1 = _a_file(id="s3", path="/tmp/first.txt")
        file2 = _a_file(id="s3", path="/tmp/second.txt")

        repo.save_file(file1)
        result = repo.save_file(file2)

        assert result.is_ok
        assert result.value.path == "/tmp/second.txt"

        find_result = repo.get_file_by_id("s3")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/second.txt"

    def test_save_file_stores_all_fields(self, repo: FileRepository) -> None:
        file = _a_file(
            id="s4",
            path="/tmp/all_fields.py",
            source_type=SourceType.UNKNOWN,
            hash=VALID_HASH,
            file_type="python",
            size=1024,
            language="python",
            aggregated_keywords=["test", "keyword"],
            aggregated_tags=["tag1", "tag2"],
            status=FileStatus.INDEXED,
        )
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("s4")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.path == "/tmp/all_fields.py"
        assert f.source_type == SourceType.UNKNOWN
        assert f.hash == VALID_HASH
        assert f.file_type == "python"
        assert f.size == 1024
        assert f.language == "python"
        assert f.aggregated_keywords == ["test", "keyword"]
        assert f.aggregated_tags == ["tag1", "tag2"]
        assert f.status == FileStatus.INDEXED

    def test_save_file_with_none_optional_fields(self, repo: FileRepository) -> None:
        file = _a_file(id="s5", hash=None, file_type=None, size=None, language=None)
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("s5")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.hash is None
        assert f.file_type is None
        assert f.size is None
        assert f.language is None

    def test_save_file_handles_empty_keywords_tags(self, repo: FileRepository) -> None:
        file = _a_file(id="s6", aggregated_keywords=[], aggregated_tags=[])
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("s6")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.aggregated_keywords == []
        assert f.aggregated_tags == []

    def test_save_file_stores_new_fields(self, repo: FileRepository) -> None:
        file = _a_file(
            id="s7",
            total_chunks=12,
            average_importance=0.75,
            metadata={"session_id": "s-42", "note": "hello world"},
        )
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("s7")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.total_chunks == 12
        assert f.average_importance == 0.75
        assert f.metadata == {"session_id": "s-42", "note": "hello world"}

    def test_save_file_new_fields_defaults_when_db_null(
        self, repo: FileRepository, manager: FileMetadataConnectionManager
    ) -> None:
        """A row written without the new fields (e.g. pre-existing DB data)
        maps back to entity defaults."""
        file = _a_file(id="s8")
        save_result = repo.save_file(file)
        assert save_result.is_ok

        # Simulate legacy row state: NULL metadata column, default columns as-is
        session = manager.get_session()
        try:
            orm = session.query(FileORM).filter(FileORM.id == "s8").first()
            orm.metadata_json = None
            session.commit()
        finally:
            manager.close_session(session)

        find_result = repo.get_file_by_id("s8")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.total_chunks == 0
        assert f.average_importance == 0.5
        assert f.metadata == {}


# ---------------------------------------------------------------------------
# get_file_by_id
# ---------------------------------------------------------------------------


class TestGetFileById:
    """get_file_by_id retrieves a File by its id."""

    def test_returns_result_ok_with_file(self, repo: FileRepository) -> None:
        file = _a_file(id="g1")
        repo.save_file(file)

        result = repo.get_file_by_id("g1")
        assert result.is_ok
        assert result.value is not None
        assert result.value.id == "g1"

    def test_returns_none_when_not_found(self, repo: FileRepository) -> None:
        result = repo.get_file_by_id("nonexistent")
        assert result.is_ok
        assert result.value is None

    def test_returns_correct_file_among_many(self, repo: FileRepository) -> None:
        f1 = _a_file(id="g2", path="/tmp/a.txt")
        f2 = _a_file(id="g3", path="/tmp/b.txt")
        f3 = _a_file(id="g4", path="/tmp/c.txt")
        repo.save_file(f1)
        repo.save_file(f2)
        repo.save_file(f3)

        result = repo.get_file_by_id("g3")
        assert result.is_ok
        assert result.value is not None
        assert result.value.path == "/tmp/b.txt"


# ---------------------------------------------------------------------------
# get_file_by_path
# ---------------------------------------------------------------------------


class TestGetFileByPath:
    """get_file_by_path retrieves a File by its path."""

    def test_returns_result_ok_with_file(self, repo: FileRepository) -> None:
        file = _a_file(id="p1", path="/tmp/unique_path.txt")
        repo.save_file(file)

        result = repo.get_file_by_path("/tmp/unique_path.txt")
        assert result.is_ok
        assert result.value is not None
        assert result.value.id == "p1"

    def test_returns_none_when_not_found(self, repo: FileRepository) -> None:
        result = repo.get_file_by_path("/tmp/notfound.txt")
        assert result.is_ok
        assert result.value is None

    def test_returns_first_match_for_duplicate_paths(self, repo: FileRepository) -> None:
        file = _a_file(id="p2", path="/tmp/dup.txt")
        repo.save_file(file)

        result = repo.get_file_by_path("/tmp/dup.txt")
        assert result.is_ok
        assert result.value is not None
        assert result.value.id == "p2"


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    """list_files returns all saved files."""

    def test_returns_empty_list_when_no_files(self, repo: FileRepository) -> None:
        result = repo.list_files()
        assert result.is_ok
        assert result.value == []

    def test_returns_all_saved_files(self, repo: FileRepository) -> None:
        f1 = _a_file(id="l1", path="/tmp/a.txt")
        f2 = _a_file(id="l2", path="/tmp/b.txt")
        f3 = _a_file(id="l3", path="/tmp/c.txt")
        repo.save_file(f1)
        repo.save_file(f2)
        repo.save_file(f3)

        result = repo.list_files()
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 3
        ids = {f.id for f in result.value}
        assert ids == {"l1", "l2", "l3"}

    def test_returns_files_with_correct_data(self, repo: FileRepository) -> None:
        file = _a_file(
            id="l4",
            path="/tmp/typed.py",
            file_type="python",
            size=2048,
            language="python",
            aggregated_keywords=["domain"],
            aggregated_tags=["core"],
            status=FileStatus.INDEXED,
        )
        repo.save_file(file)

        result = repo.list_files()
        assert result.is_ok
        found = next((f for f in result.value if f.id == "l4"), None)
        assert found is not None
        assert found.file_type == "python"
        assert found.size == 2048
        assert found.language == "python"
        assert found.aggregated_keywords == ["domain"]
        assert found.aggregated_tags == ["core"]
        assert found.status == FileStatus.INDEXED


# ---------------------------------------------------------------------------
# search_files_by_query
# ---------------------------------------------------------------------------


class TestSearchFilesByQuery:
    """search_files_by_query searches across path, keywords, and tags."""

    def test_matches_path(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q1", path="/tmp/test_file.txt")
        f2 = _a_file(id="q2", path="/tmp/other.txt")
        repo.save_file(f1)
        repo.save_file(f2)

        result = repo.search_files_by_query("test")
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q1"

    def test_matches_keywords(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q3", path="/tmp/x.txt", aggregated_keywords=["domain", "entity"])
        f2 = _a_file(id="q4", path="/tmp/y.txt", aggregated_keywords=["infra"])
        repo.save_file(f1)
        repo.save_file(f2)

        result = repo.search_files_by_query("domain")
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q3"

    def test_matches_tags(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q5", path="/tmp/a.txt", aggregated_tags=["core", "important"])
        f2 = _a_file(id="q6", path="/tmp/b.txt", aggregated_tags=["util"])
        repo.save_file(f1)
        repo.save_file(f2)

        result = repo.search_files_by_query("core")
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q5"

    def test_returns_empty_when_no_matches(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q7", path="/tmp/a.txt")
        repo.save_file(f1)

        result = repo.search_files_by_query("nonexistent")
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 0

    def test_case_insensitive_search(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q8", path="/tmp/TestFile.txt")
        repo.save_file(f1)

        result = repo.search_files_by_query("test")
        assert result.is_ok
        assert len(result.value) == 1

    def test_matches_multiple_fields(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q9", path="/tmp/alpha.txt", aggregated_keywords=["domain"])
        f2 = _a_file(id="q10", path="/tmp/beta.txt", aggregated_tags=["domain"])
        f3 = _a_file(id="q11", path="/tmp/gamma.txt")
        repo.save_file(f1)
        repo.save_file(f2)
        repo.save_file(f3)

        result = repo.search_files_by_query("domain")
        assert result.is_ok
        assert result.value is not None
        ids = {f.id for f in result.value}
        assert ids == {"q9", "q10"}

    def test_multiple_keywords_match(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q12", path="/tmp/m.txt", aggregated_keywords=["domain", "entity", "aggregate"])
        repo.save_file(f1)

        result = repo.search_files_by_query("entity")
        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].id == "q12"

    def test_multiple_tags_match(self, repo: FileRepository) -> None:
        f1 = _a_file(id="q13", path="/tmp/n.txt", aggregated_tags=["core", "critical", "p0"])
        repo.save_file(f1)

        result = repo.search_files_by_query("critical")
        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].id == "q13"


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


class TestDeleteFile:
    """delete_file removes a File by id."""

    def test_returns_true_when_found(self, repo: FileRepository) -> None:
        file = _a_file(id="d1")
        repo.save_file(file)

        result = repo.delete_file("d1")
        assert result.is_ok
        assert result.value is True

    def test_returns_false_when_not_found(self, repo: FileRepository) -> None:
        result = repo.delete_file("nonexistent")
        assert result.is_ok
        assert result.value is False

    def test_removes_from_store(self, repo: FileRepository) -> None:
        file = _a_file(id="d2")
        repo.save_file(file)

        repo.delete_file("d2")

        find_result = repo.get_file_by_id("d2")
        assert find_result.is_ok
        assert find_result.value is None

    def test_delete_does_not_affect_other_files(self, repo: FileRepository) -> None:
        f1 = _a_file(id="d3", path="/tmp/d3.txt")
        f2 = _a_file(id="d4", path="/tmp/d4.txt")
        repo.save_file(f1)
        repo.save_file(f2)

        repo.delete_file("d3")

        # f1 deleted
        assert repo.get_file_by_id("d3").value is None

        # f2 still there
        find_result = repo.get_file_by_id("d4")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.id == "d4"

    def test_delete_idempotent(self, repo: FileRepository) -> None:
        file = _a_file(id="d5")
        repo.save_file(file)

        result1 = repo.delete_file("d5")
        assert result1.value is True

        result2 = repo.delete_file("d5")
        assert result2.value is False


# ---------------------------------------------------------------------------
# Round-trip and integration
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Round-trip tests for save and retrieve operations."""

    def test_save_and_get_by_id(self, repo: FileRepository) -> None:
        file = _a_file(id="rt1", path="/tmp/roundtrip.txt")
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/roundtrip.txt"

    def test_save_and_get_by_path(self, repo: FileRepository) -> None:
        file = _a_file(id="rt2", path="/tmp/by_path.txt")
        repo.save_file(file)

        find_result = repo.get_file_by_path("/tmp/by_path.txt")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.id == "rt2"

    def test_save_search_and_delete(self, repo: FileRepository) -> None:
        file = _a_file(id="rt3", path="/tmp/searchable.txt", aggregated_keywords=["search"])
        repo.save_file(file)

        # Search finds it
        search_result = repo.search_files_by_query("search")
        assert search_result.is_ok
        assert len(search_result.value) == 1

        # Delete removes it
        delete_result = repo.delete_file("rt3")
        assert delete_result.value is True

        # Search no longer finds it
        search_result2 = repo.search_files_by_query("search")
        assert search_result2.is_ok
        assert len(search_result2.value) == 0

    def test_save_and_get_new_fields_round_trip(self, repo: FileRepository) -> None:
        file = _a_file(
            id="rt4",
            total_chunks=33,
            average_importance=0.125,
            metadata={"a": "1", "b": "two"},
        )
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("rt4")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.total_chunks == 33
        assert f.average_importance == 0.125
        assert f.metadata == {"a": "1", "b": "two"}

    def test_save_and_get_new_fields_defaults_round_trip(self, repo: FileRepository) -> None:
        file = _a_file(id="rt5")
        save_result = repo.save_file(file)
        assert save_result.is_ok

        find_result = repo.get_file_by_id("rt5")
        assert find_result.is_ok
        f = find_result.value
        assert f is not None
        assert f.total_chunks == 0
        assert f.average_importance == 0.5
        assert f.metadata == {}

    def test_full_round_trip_with_all_fields(self, repo: FileRepository) -> None:
        file = _a_file(
            id="rt4",
            path="/tmp/full.py",
            source_type=SourceType.UNKNOWN,
            hash=VALID_HASH,
            file_type="python",
            size=4096,
            language="python",
            aggregated_keywords=["domain", "ddd", "entity"],
            aggregated_tags=["core", "important"],
            status=FileStatus.INDEXED,
        )
        repo.save_file(file)

        # Retrieve by id
        by_id = repo.get_file_by_id("rt4")
        assert by_id.is_ok
        f = by_id.value
        assert f is not None
        assert f.id == "rt4"
        assert f.path == "/tmp/full.py"
        assert f.source_type == SourceType.UNKNOWN
        assert f.hash == VALID_HASH
        assert f.file_type == "python"
        assert f.size == 4096
        assert f.language == "python"
        assert f.aggregated_keywords == ["domain", "ddd", "entity"]
        assert f.aggregated_tags == ["core", "important"]
        assert f.status == FileStatus.INDEXED

        # Retrieve by path
        by_path = repo.get_file_by_path("/tmp/full.py")
        assert by_path.is_ok
        assert by_path.value is not None
        assert by_path.value.id == "rt4"

        # Search by keyword
        search = repo.search_files_by_query("ddd")
        assert search.is_ok
        assert len(search.value) == 1
        assert search.value[0].id == "rt4"

        # Search by tag
        search2 = repo.search_files_by_query("important")
        assert search2.is_ok
        assert len(search2.value) == 1

        # Search by path
        search3 = repo.search_files_by_query("full")
        assert search3.is_ok
        assert len(search3.value) == 1

        # List includes it
        listed = repo.list_files()
        assert listed.is_ok
        assert any(f.id == "rt4" for f in listed.value)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Repository returns Result.ko on database errors."""

    def test_save_file_returns_ko_on_db_error(self, tmp_bank_dir: Path) -> None:
        """If the DB is corrupted, save_file returns Result.ko."""
        # Create a manager, then corrupt the DB by writing garbage
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        repo = FileRepository(mgr)

        # Corrupt the DB
        import sqlite3

        raw_conn = sqlite3.connect(str(mgr.db_path))
        raw_conn.execute("DROP TABLE files")
        raw_conn.commit()
        raw_conn.close()

        file = _a_file(id="err1")
        result = repo.save_file(file)
        assert result.is_ko is True

        mgr.close()

    def test_get_file_by_id_returns_ko_on_db_error(self, tmp_bank_dir: Path) -> None:
        """If the DB is corrupted, get_file_by_id returns Result.ko."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        repo = FileRepository(mgr)

        # Corrupt the DB
        import sqlite3

        raw_conn = sqlite3.connect(str(mgr.db_path))
        raw_conn.execute("DROP TABLE files")
        raw_conn.commit()
        raw_conn.close()

        result = repo.get_file_by_id("err2")
        assert result.is_ko is True

        mgr.close()

    def test_list_files_returns_ko_on_db_error(self, tmp_bank_dir: Path) -> None:
        """If the DB is corrupted, list_files returns Result.ko."""
        mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
        repo = FileRepository(mgr)

        # Corrupt the DB
        import sqlite3

        raw_conn = sqlite3.connect(str(mgr.db_path))
        raw_conn.execute("DROP TABLE files")
        raw_conn.commit()
        raw_conn.close()

        result = repo.list_files()
        assert result.is_ko is True

        mgr.close()


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


class TestFTS5Search:
    """Full-text search using FTS5 works correctly."""

    def test_fts5_table_exists(self, manager: FileMetadataConnectionManager, tmp_bank_dir: Path) -> None:
        """FTS5 virtual table is created."""
        import sqlite3

        conn = sqlite3.connect(str(manager.db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files_fts'")
            row = cursor.fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_fts5_search_path(self, repo: FileRepository) -> None:
        """FTS5 search matches path content."""
        file = _a_file(id="fts1", path="/tmp/important_config.yaml")
        repo.save_file(file)

        result = repo.search_files_by_query("important")
        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].id == "fts1"

    def test_fts5_search_keywords(self, repo: FileRepository) -> None:
        """FTS5 search matches keywords content."""
        file = _a_file(id="fts2", path="/tmp/x.txt", aggregated_keywords=["architecture", "patterns"])
        repo.save_file(file)

        result = repo.search_files_by_query("patterns")
        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].id == "fts2"

    def test_fts5_search_tags(self, repo: FileRepository) -> None:
        """FTS5 search matches tags content."""
        file = _a_file(id="fts3", path="/tmp/y.txt", aggregated_tags=["production", "critical"])
        repo.save_file(file)

        result = repo.search_files_by_query("production")
        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].id == "fts3"

    def test_fts5_cross_field_search(self, repo: FileRepository) -> None:
        """FTS5 search matches across path, keywords, and tags."""
        f1 = _a_file(id="fts4", path="/tmp/path_match.txt")
        f2 = _a_file(id="fts5", path="/tmp/no_match.txt", aggregated_keywords=["keyword_match"])
        f3 = _a_file(id="fts6", path="/tmp/also_no.txt", aggregated_tags=["tag_match"])
        repo.save_file(f1)
        repo.save_file(f2)
        repo.save_file(f3)

        # Search for "match" should find all three
        result = repo.search_files_by_query("match")
        assert result.is_ok
        ids = {f.id for f in result.value}
        assert ids == {"fts4", "fts5", "fts6"}

    def test_fts5_delete_removes_from_index(self, repo: FileRepository) -> None:
        """Deleting a file removes it from the FTS5 index."""
        file = _a_file(id="fts7", path="/tmp/deletable.txt", aggregated_keywords=["deletable"])
        repo.save_file(file)

        # Verify it's searchable
        result = repo.search_files_by_query("deletable")
        assert result.is_ok
        assert len(result.value) == 1

        # Delete it
        repo.delete_file("fts7")

        # Should no longer be searchable
        result2 = repo.search_files_by_query("deletable")
        assert result2.is_ok
        assert len(result2.value) == 0

    def test_fts5_update_refreshes_index(self, repo: FileRepository) -> None:
        """Saving an updated file refreshes the FTS5 index."""
        file = _a_file(id="fts8", path="/tmp/old_name.txt")
        repo.save_file(file)

        # Search for old name
        result = repo.search_files_by_query("old_name")
        assert result.is_ok
        assert len(result.value) == 1

        # Update with new path
        updated = _a_file(id="fts8", path="/tmp/new_name.txt")
        repo.save_file(updated)

        # Old name no longer matches
        result2 = repo.search_files_by_query("old_name")
        assert result2.is_ok
        assert len(result2.value) == 0

        # New name matches
        result3 = repo.search_files_by_query("new_name")
        assert result3.is_ok
        assert len(result3.value) == 1


# ---------------------------------------------------------------------------
# Upsert preserves child rows (INSERT OR REPLACE bug fix)
# ---------------------------------------------------------------------------


class TestSaveFilePreservesChunks:
    """save_file upsert must NOT trigger ON DELETE CASCADE on file_chunks.

    The old INSERT OR REPLACE first deletes the row (triggering CASCADE on
    file_chunks FK) then inserts a new one, losing all associated chunks.
    The fix uses INSERT ... ON CONFLICT(id) DO UPDATE SET ... instead.
    """

    def test_update_file_preserves_associated_chunks(
        self,
        repo: FileRepository,
        manager: FileMetadataConnectionManager,
    ) -> None:
        """Updating an existing file via save_file must NOT delete file_chunks."""
        from src.domain.file_chunk_entity import FileChunk
        from src.infrastructure.storage.sqlite.file_chunk_repository import (
            FileChunkRepository,
        )

        # Create a file
        file = _a_file(id="uc1", path="/tmp/chunk_preserve.py")
        repo.save_file(file)

        # Add chunks directly via chunk repo
        chunk_repo = FileChunkRepository(manager)
        chunk_repo.save_chunk(
            FileChunk.of(
                {
                    "id": "fc_uc1_c1",
                    "file_id": "uc1",
                    "memory_id": "mem_c1",
                    "chunk_index": 0,
                    "start_line": 1,
                    "end_line": 50,
                }
            ).value
        )
        chunk_repo.save_chunk(
            FileChunk.of(
                {
                    "id": "fc_uc1_c2",
                    "file_id": "uc1",
                    "memory_id": "mem_c2",
                    "chunk_index": 1,
                    "start_line": 51,
                    "end_line": 100,
                }
            ).value
        )

        # Verify chunks exist
        chunks_before = chunk_repo.get_chunks_by_file_id("uc1")
        assert chunks_before.is_ok
        assert len(chunks_before.value) == 2

        # Update the file (this is where INSERT OR REPLACE would lose chunks)
        updated_file = _a_file(id="uc1", path="/tmp/chunk_preserve_updated.py")
        save_result = repo.save_file(updated_file)
        assert save_result.is_ok

        # File was updated
        find_result = repo.get_file_by_id("uc1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/chunk_preserve_updated.py"

        # Chunks must still exist — this is the key assertion
        chunks_after = chunk_repo.get_chunks_by_file_id("uc1")
        assert chunks_after.is_ok
        assert len(chunks_after.value) == 2
        assert chunks_after.value[0].memory_id == "mem_c1"
        assert chunks_after.value[1].memory_id == "mem_c2"

    def test_update_file_preserves_all_chunk_data(
        self,
        repo: FileRepository,
        manager: FileMetadataConnectionManager,
    ) -> None:
        """Chunk data (start_line, end_line, etc.) survives file update."""
        from src.domain.file_chunk_entity import FileChunk
        from src.infrastructure.storage.sqlite.file_chunk_repository import (
            FileChunkRepository,
        )

        file = _a_file(id="uc2", path="/tmp/data_preserve.py")
        repo.save_file(file)

        chunk_repo = FileChunkRepository(manager)
        chunk_repo.save_chunk(
            FileChunk.of(
                {
                    "id": "fc_uc2_c1",
                    "file_id": "uc2",
                    "memory_id": "mem_data",
                    "chunk_index": 0,
                    "start_line": 10,
                    "end_line": 99,
                }
            ).value
        )

        # Update file
        updated = _a_file(id="uc2", path="/tmp/data_preserve_v2.py")
        repo.save_file(updated)

        # Chunk data intact
        chunk = chunk_repo.get_chunk_by_id("fc_uc2_c1")
        assert chunk.is_ok
        assert chunk.value is not None
        assert chunk.value.start_line == 10
        assert chunk.value.end_line == 99
        assert chunk.value.chunk_index == 0

    def test_update_file_preserves_associated_relations(
        self,
        repo: FileRepository,
        manager: FileMetadataConnectionManager,
    ) -> None:
        """Updating a file must NOT delete file_relations (ON DELETE CASCADE)."""
        from src.domain.file_relation_entity import FileRelation, RelationType
        from src.infrastructure.storage.sqlite.file_relation_repository import (
            FileRelationRepository,
        )

        file1 = _a_file(id="uc3", path="/tmp/rel_preserve.py")
        file2 = _a_file(id="uc3b", path="/tmp/rel_target.py")
        repo.save_file(file1)
        repo.save_file(file2)

        rel_repo = FileRelationRepository(manager)
        rel_repo.save_relation(
            FileRelation.of(
                {
                    "id": "fr_uc3_uc3b",
                    "source_file_id": "uc3",
                    "target_file_id": "uc3b",
                    "relation_type": RelationType.SIBLING,
                    "strength": 0.9,
                }
            ).value
        )

        # Update file1
        updated = _a_file(id="uc3", path="/tmp/rel_preserve_updated.py")
        repo.save_file(updated)

        # Relation must still exist
        rels = rel_repo.get_relations_by_file_id("uc3")
        assert rels.is_ok
        assert len(rels.value) == 1
        assert rels.value[0].target_file_id == "uc3b"
