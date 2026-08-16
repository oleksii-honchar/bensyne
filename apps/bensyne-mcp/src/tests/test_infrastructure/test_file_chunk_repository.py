"""FileChunkRepository tests — SQLite-backed FileChunkRepository implementation.

Tests all repository operations using an in-memory SQLite database via
FileMetadataConnectionManager.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

import pytest

from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.utils.result import Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_chunk_repository import (
    FileChunkRepository,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository

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
def repo(manager: FileMetadataConnectionManager) -> Generator[FileChunkRepository, None, None]:
    """Create a FileChunkRepository backed by a temporary database."""
    r = FileChunkRepository(manager)
    yield r


@pytest.fixture
def file_repo(manager: FileMetadataConnectionManager) -> FileRepository:
    """Create a FileRepository for seeding files (FK constraints)."""
    return FileRepository(manager)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    status: FileStatus = FileStatus.PENDING,
    created_at: Optional[datetime] = None,
) -> File:
    """Create a valid File instance with sensible defaults."""
    result = File.of(
        {
            "id": id,
            "path": path,
            "source_type": source_type,
            "status": status,
            "created_at": created_at or datetime.now(),
        }
    )
    assert result.is_ok, f"Failed to create test file: {result.errors}"
    return result.value


def _seed_file(file_repo: FileRepository, file_id: str = "f1") -> File:
    """Save a file to satisfy FK constraints for file_chunks tests."""
    f = _a_file(id=file_id)
    result = file_repo.save_file(f)
    assert result.is_ok, f"Failed to seed file: {result.errors}"
    return result.value


def _a_chunk(
    id: str = "fc1",
    file_id: str = "f1",
    memory_id: str = "m1",
    chunk_index: int = 0,
    start_line: int = 0,
    end_line: int = 10,
    content_hash: Optional[str] = None,
    content_type: ContentType = ContentType.UNKNOWN,
    is_partial: bool = False,
    created_at: Optional[datetime] = None,
) -> FileChunk:
    """Create a valid FileChunk instance with sensible defaults."""
    result = FileChunk.of(
        {
            "id": id,
            "file_id": file_id,
            "memory_id": memory_id,
            "chunk_index": chunk_index,
            "start_line": start_line,
            "end_line": end_line,
            "content_hash": content_hash,
            "content_type": content_type,
            "is_partial": is_partial,
            "created_at": created_at or datetime.now(),
        }
    )
    assert result.is_ok, f"Failed to create test chunk: {result.errors}"
    return result.value


# ---------------------------------------------------------------------------
# save_chunk
# ---------------------------------------------------------------------------


class TestSaveChunk:
    """FileChunkRepository.save_chunk operations."""

    def test_save_chunk_returns_result_ok_with_chunk(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="sc1")
        result = repo.save_chunk(chunk)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "sc1"

    def test_save_chunk_persists_to_database(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="sc2", file_id="f1", memory_id="m1", chunk_index=5)
        save_result = repo.save_chunk(chunk)
        assert save_result.is_ok

        find_result = repo.get_chunk_by_id("sc2")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.chunk_index == 5

    def test_save_chunk_overwrites_existing(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk1 = _a_chunk(id="sc3", chunk_index=0)
        chunk2 = _a_chunk(id="sc3", chunk_index=99)
        repo.save_chunk(chunk1)
        result = repo.save_chunk(chunk2)
        assert result.is_ok is True
        assert result.value.chunk_index == 99

        find_result = repo.get_chunk_by_id("sc3")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.chunk_index == 99

    def test_save_chunk_stores_all_fields(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f4")
        chunk = _a_chunk(
            id="sc4",
            file_id="f4",
            memory_id="m4",
            chunk_index=3,
            start_line=10,
            end_line=20,
            content_hash="c" * 64,
            content_type=ContentType.CODE,
            is_partial=True,
        )
        save_result = repo.save_chunk(chunk)
        assert save_result.is_ok

        find_result = repo.get_chunk_by_id("sc4")
        assert find_result.is_ok
        assert find_result.value is not None
        f = find_result.value
        assert f.file_id == "f4"
        assert f.memory_id == "m4"
        assert f.chunk_index == 3
        assert f.start_line == 10
        assert f.end_line == 20
        assert f.content_hash == "c" * 64
        assert f.content_type == ContentType.CODE
        assert f.is_partial is True

    def test_save_chunk_with_none_content_hash(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="sc5", content_hash=None)
        save_result = repo.save_chunk(chunk)
        assert save_result.is_ok

        find_result = repo.get_chunk_by_id("sc5")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.content_hash is None


# ---------------------------------------------------------------------------
# get_chunk_by_id
# ---------------------------------------------------------------------------


class TestGetChunkById:
    """FileChunkRepository.get_chunk_by_id operations."""

    def test_get_chunk_by_id_returns_chunk(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="gc1", file_id="f1", memory_id="m1")
        repo.save_chunk(chunk)
        result = repo.get_chunk_by_id("gc1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "gc1"
        assert result.value.file_id == "f1"
        assert result.value.memory_id == "m1"

    def test_get_chunk_by_id_returns_none_when_not_found(self, repo: FileChunkRepository) -> None:
        result = repo.get_chunk_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None


# ---------------------------------------------------------------------------
# get_chunks_by_file_id
# ---------------------------------------------------------------------------


class TestGetChunksByFileId:
    """FileChunkRepository.get_chunks_by_file_id operations."""

    def test_get_chunks_by_file_id_returns_all_chunks(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        c1 = _a_chunk(id="fc1", file_id="f1", memory_id="m1", chunk_index=0)
        c2 = _a_chunk(id="fc2", file_id="f1", memory_id="m2", chunk_index=1)
        c3 = _a_chunk(id="fc3", file_id="f2", memory_id="m3", chunk_index=0)
        repo.save_chunk(c1)
        repo.save_chunk(c2)
        repo.save_chunk(c3)

        result = repo.get_chunks_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {c.id for c in result.value}
        assert ids == {"fc1", "fc2"}

    def test_get_chunks_by_file_id_returns_empty_when_no_chunks(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f2")
        c1 = _a_chunk(id="fc4", file_id="f2", chunk_index=0)
        repo.save_chunk(c1)

        result = repo.get_chunks_by_file_id("nonexistent")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

    def test_get_chunks_by_file_id_returns_ordered_by_chunk_index(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f1")
        # Save in reverse order to test ordering
        c2 = _a_chunk(id="fo2", file_id="f1", memory_id="mo2", chunk_index=2)
        c0 = _a_chunk(id="fo0", file_id="f1", memory_id="mo0", chunk_index=0)
        c1 = _a_chunk(id="fo1", file_id="f1", memory_id="mo1", chunk_index=1)
        repo.save_chunk(c2)
        repo.save_chunk(c0)
        repo.save_chunk(c1)

        result = repo.get_chunks_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        indices = [c.chunk_index for c in result.value]
        assert indices == [0, 1, 2]

    def test_get_chunks_by_file_id_returns_all_fields(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f5")
        chunk = _a_chunk(
            id="fc5",
            file_id="f5",
            memory_id="m5",
            chunk_index=7,
            start_line=50,
            end_line=100,
            content_hash="e" * 64,
            content_type=ContentType.TEXT,
            is_partial=False,
        )
        repo.save_chunk(chunk)

        result = repo.get_chunks_by_file_id("f5")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 1
        f = result.value[0]
        assert f.id == "fc5"
        assert f.chunk_index == 7
        assert f.start_line == 50
        assert f.end_line == 100
        assert f.content_hash == "e" * 64
        assert f.content_type == ContentType.TEXT
        assert f.is_partial is False


# ---------------------------------------------------------------------------
# get_chunk_by_memory_id
# ---------------------------------------------------------------------------


class TestGetChunkByMemoryId:
    """FileChunkRepository.get_chunk_by_memory_id operations."""

    def test_get_chunk_by_memory_id_returns_chunk(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="mc1", memory_id="mem1")
        repo.save_chunk(chunk)
        result = repo.get_chunk_by_memory_id("mem1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "mc1"

    def test_get_chunk_by_memory_id_returns_none_when_not_found(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="mc2", memory_id="mem2")
        repo.save_chunk(chunk)
        result = repo.get_chunk_by_memory_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_get_chunk_by_memory_id_returns_first_match(
        self, repo: FileChunkRepository, file_repo: FileRepository
    ) -> None:
        _seed_file(file_repo, "f1")
        c1 = _a_chunk(id="mc3", memory_id="mem3")
        c2 = _a_chunk(id="mc4", memory_id="mem4")
        repo.save_chunk(c1)
        repo.save_chunk(c2)
        result = repo.get_chunk_by_memory_id("mem3")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "mc3"


# ---------------------------------------------------------------------------
# delete_chunk
# ---------------------------------------------------------------------------


class TestDeleteChunk:
    """FileChunkRepository.delete_chunk operations."""

    def test_delete_chunk_returns_true_when_found(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="dc1")
        repo.save_chunk(chunk)
        result = repo.delete_chunk("dc1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_chunk_returns_false_when_not_found(self, repo: FileChunkRepository) -> None:
        result = repo.delete_chunk("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_delete_chunk_removes_from_store(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="dc2")
        repo.save_chunk(chunk)
        repo.delete_chunk("dc2")
        find_result = repo.get_chunk_by_id("dc2")
        assert find_result.is_ok is True
        assert find_result.value is None


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """End-to-end round-trip tests for FileChunkRepository."""

    def test_round_trip_save_and_get_by_id(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="rt1", file_id="f1", memory_id="m1")
        save_result = repo.save_chunk(chunk)
        assert save_result.is_ok
        find_result = repo.get_chunk_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.file_id == "f1"
        assert find_result.value.memory_id == "m1"

    def test_round_trip_save_and_get_by_file_id(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="rt2", file_id="f1", memory_id="m1")
        repo.save_chunk(chunk)
        find_result = repo.get_chunks_by_file_id("f1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt2"

    def test_round_trip_save_and_get_by_memory_id(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="rt3", file_id="f1", memory_id="m1")
        repo.save_chunk(chunk)
        find_result = repo.get_chunk_by_memory_id("m1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.id == "rt3"

    def test_round_trip_save_update_and_get(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        chunk = _a_chunk(id="rt4", chunk_index=0)
        repo.save_chunk(chunk)

        # update_metadata only accepts metadata fields, not chunk_index
        updated_result = chunk.update_metadata(content_type=ContentType.CODE)
        assert updated_result.is_ok
        repo.save_chunk(updated_result.value)

        find_result = repo.get_chunk_by_id("rt4")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.content_type == ContentType.CODE

    def test_round_trip_save_delete_and_verify(self, repo: FileChunkRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f5")
        chunk = _a_chunk(id="rt5", file_id="f5", memory_id="m5")
        repo.save_chunk(chunk)

        # Verify it exists
        find_result = repo.get_chunk_by_id("rt5")
        assert find_result.is_ok
        assert find_result.value is not None

        # Delete it
        delete_result = repo.delete_chunk("rt5")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify it's gone
        after_delete = repo.get_chunk_by_id("rt5")
        assert after_delete.is_ok
        assert after_delete.value is None

        # Verify it's gone from file_id query too
        after_file = repo.get_chunks_by_file_id("f5")
        assert after_file.is_ok
        assert after_file.value is not None
        assert len(after_file.value) == 0
