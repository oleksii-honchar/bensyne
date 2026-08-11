"""FileChunkRepository interface contract tests.

Verifies that the FileChunkRepository abstract interface defines the correct
method signatures and that an in-memory implementation satisfies the
Result pattern for all operations.
"""

from datetime import datetime
from typing import List, Optional

import pytest

from src.domain.entities.file_chunk import ContentType, FileChunk
from src.domain.interfaces import FileChunkRepository
from src.domain.result import Result

VALID_CONTENT_HASH = "b" * 64

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
) -> FileChunk:
    """Create a valid FileChunk instance with sensible defaults."""
    result = FileChunk.of({
        "id": id,
        "file_id": file_id,
        "memory_id": memory_id,
        "chunk_index": chunk_index,
        "start_line": start_line,
        "end_line": end_line,
        "content_hash": content_hash,
        "content_type": content_type,
        "is_partial": is_partial,
    })
    assert result.is_ok, f"Failed to create test chunk: {result.errors}"
    return result.value

# ---------------------------------------------------------------------------
# Tests against the abstract interface (no implementation required)
# ---------------------------------------------------------------------------

class TestFileChunkRepositoryInterface:
    """FileChunkRepository defines the correct abstract interface."""

    def test_file_chunk_repository_is_abstract(self):
        # Instantiation should fail because it's abstract
        with pytest.raises(TypeError):
            FileChunkRepository()  # type: ignore

    def test_file_chunk_repository_has_save_chunk_method(self):
        assert hasattr(FileChunkRepository, "save_chunk")
        assert callable(getattr(FileChunkRepository, "save_chunk"))

    def test_file_chunk_repository_has_get_chunk_by_id_method(self):
        assert hasattr(FileChunkRepository, "get_chunk_by_id")
        assert callable(getattr(FileChunkRepository, "get_chunk_by_id"))

    def test_file_chunk_repository_has_get_chunks_by_file_id_method(self):
        assert hasattr(FileChunkRepository, "get_chunks_by_file_id")
        assert callable(getattr(FileChunkRepository, "get_chunks_by_file_id"))

    def test_file_chunk_repository_has_get_chunk_by_memory_id_method(self):
        assert hasattr(FileChunkRepository, "get_chunk_by_memory_id")
        assert callable(getattr(FileChunkRepository, "get_chunk_by_memory_id"))

    def test_file_chunk_repository_has_delete_chunk_method(self):
        assert hasattr(FileChunkRepository, "delete_chunk")
        assert callable(getattr(FileChunkRepository, "delete_chunk"))

    def test_save_chunk_is_abstract(self):
        method = getattr(FileChunkRepository, "save_chunk")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_chunk_by_id_is_abstract(self):
        method = getattr(FileChunkRepository, "get_chunk_by_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_chunks_by_file_id_is_abstract(self):
        method = getattr(FileChunkRepository, "get_chunks_by_file_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_chunk_by_memory_id_is_abstract(self):
        method = getattr(FileChunkRepository, "get_chunk_by_memory_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_delete_chunk_is_abstract(self):
        method = getattr(FileChunkRepository, "delete_chunk")
        assert getattr(method, "__isabstractmethod__", False) is True

# ---------------------------------------------------------------------------
# In-memory implementation for contract verification
# ---------------------------------------------------------------------------

class InMemoryFileChunkRepository(FileChunkRepository):
    """Minimal in-memory FileChunkRepository for contract testing."""

    def __init__(self, data: Optional[List[FileChunk]] = None) -> None:
        self._store: dict[str, FileChunk] = {}
        if data:
            for c in data:
                self._store[c.id] = c

    def save_chunk(self, chunk: FileChunk) -> Result[FileChunk]:
        self._store[chunk.id] = chunk
        return Result.ok(chunk)

    def get_chunk_by_id(self, chunk_id: str) -> Result[Optional[FileChunk]]:
        return Result.ok(self._store.get(chunk_id))

    def get_chunks_by_file_id(self, file_id: str) -> Result[List[FileChunk]]:
        chunks = [c for c in self._store.values() if c.file_id == file_id]
        chunks.sort(key=lambda c: c.chunk_index)
        return Result.ok(chunks)

    def get_chunk_by_memory_id(self, memory_id: str) -> Result[Optional[FileChunk]]:
        for c in self._store.values():
            if c.memory_id == memory_id:
                return Result.ok(c)
        return Result.ok(None)

    def get_chunks_by_memory_id(self, memory_id: str) -> Result[List[FileChunk]]:
        chunks = [c for c in self._store.values() if c.memory_id == memory_id]
        return Result.ok(chunks)

    def delete_chunk(self, chunk_id: str) -> Result[bool]:
        if chunk_id in self._store:
            del self._store[chunk_id]
            return Result.ok(True)
        return Result.ok(False)

def a_chunk_repository(data: Optional[List[FileChunk]] = None) -> InMemoryFileChunkRepository:
    return InMemoryFileChunkRepository(data)

# ---------------------------------------------------------------------------
# Contract tests against in-memory implementation
# ---------------------------------------------------------------------------

class TestFileChunkRepositoryContract:
    """In-memory FileChunkRepository satisfies the Result contract for all operations."""

    def test_implementation_is_instance_of_file_chunk_repository(self):
        repo = a_chunk_repository()
        assert isinstance(repo, FileChunkRepository)

    # --- save_chunk ---

    def test_save_chunk_returns_result_ok_with_chunk(self):
        chunk = _a_chunk(id="s1")
        repo = a_chunk_repository()
        result = repo.save_chunk(chunk)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "s1"

    def test_save_chunk_overwrites_existing(self):
        chunk1 = _a_chunk(id="s2", chunk_index=0)
        chunk2 = _a_chunk(id="s2", chunk_index=5)
        repo = a_chunk_repository()
        repo.save_chunk(chunk1)
        result = repo.save_chunk(chunk2)
        assert result.is_ok is True
        assert result.value.chunk_index == 5
        find_result = repo.get_chunk_by_id("s2")
        assert find_result.is_ok is True
        assert find_result.value is not None
        assert find_result.value.chunk_index == 5

    # --- get_chunk_by_id ---

    def test_get_chunk_by_id_returns_result_ok_with_chunk(self):
        chunk = _a_chunk(id="g1")
        repo = a_chunk_repository(data=[chunk])
        result = repo.get_chunk_by_id("g1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "g1"

    def test_get_chunk_by_id_returns_none_when_not_found(self):
        repo = a_chunk_repository()
        result = repo.get_chunk_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    # --- get_chunks_by_file_id ---

    def test_get_chunks_by_file_id_returns_all_chunks_for_file(self):
        c1 = _a_chunk(id="f1c1", file_id="f1", chunk_index=0)
        c2 = _a_chunk(id="f1c2", file_id="f1", chunk_index=1)
        c3 = _a_chunk(id="f2c1", file_id="f2", chunk_index=0)
        repo = a_chunk_repository(data=[c1, c2, c3])
        result = repo.get_chunks_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {c.id for c in result.value}
        assert ids == {"f1c1", "f1c2"}

    def test_get_chunks_by_file_id_returns_empty_when_no_chunks(self):
        c1 = _a_chunk(id="f2c1", file_id="f2", chunk_index=0)
        repo = a_chunk_repository(data=[c1])
        result = repo.get_chunks_by_file_id("nonexistent")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

    def test_get_chunks_by_file_id_returns_ordered_by_chunk_index(self):
        c1 = _a_chunk(id="o2", file_id="f1", chunk_index=2)
        c0 = _a_chunk(id="o0", file_id="f1", chunk_index=0)
        c1b = _a_chunk(id="o1", file_id="f1", chunk_index=1)
        repo = a_chunk_repository(data=[c1, c0, c1b])
        result = repo.get_chunks_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert [c.chunk_index for c in result.value] == [0, 1, 2]

    # --- get_chunk_by_memory_id ---

    def test_get_chunk_by_memory_id_returns_result_ok_with_chunk(self):
        chunk = _a_chunk(id="m1c", memory_id="mem1")
        repo = a_chunk_repository(data=[chunk])
        result = repo.get_chunk_by_memory_id("mem1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1c"

    def test_get_chunk_by_memory_id_returns_none_when_not_found(self):
        chunk = _a_chunk(id="m1c", memory_id="mem1")
        repo = a_chunk_repository(data=[chunk])
        result = repo.get_chunk_by_memory_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_get_chunk_by_memory_id_returns_first_match(self):
        c1 = _a_chunk(id="m1c1", memory_id="mem1")
        c2 = _a_chunk(id="m1c2", memory_id="mem2")
        repo = a_chunk_repository(data=[c1, c2])
        result = repo.get_chunk_by_memory_id("mem1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1c1"

    # --- delete_chunk ---

    def test_delete_chunk_returns_true_when_found(self):
        chunk = _a_chunk(id="d1")
        repo = a_chunk_repository(data=[chunk])
        result = repo.delete_chunk("d1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_chunk_returns_false_when_not_found(self):
        repo = a_chunk_repository()
        result = repo.delete_chunk("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_delete_chunk_removes_from_store(self):
        chunk = _a_chunk(id="d2")
        repo = a_chunk_repository(data=[chunk])
        repo.delete_chunk("d2")
        find_result = repo.get_chunk_by_id("d2")
        assert find_result.is_ok is True
        assert find_result.value is None

    # --- round-trip ---

    def test_round_trip_save_and_get_by_id(self):
        chunk = _a_chunk(id="rt1", file_id="f1", memory_id="m1")
        repo = a_chunk_repository()
        save_result = repo.save_chunk(chunk)
        assert save_result.is_ok
        find_result = repo.get_chunk_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.file_id == "f1"
        assert find_result.value.memory_id == "m1"

    def test_round_trip_save_and_get_by_file_id(self):
        chunk = _a_chunk(id="rt2", file_id="f1", memory_id="m1")
        repo = a_chunk_repository()
        repo.save_chunk(chunk)
        find_result = repo.get_chunks_by_file_id("f1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt2"

    def test_round_trip_save_and_get_by_memory_id(self):
        chunk = _a_chunk(id="rt3", file_id="f1", memory_id="m1")
        repo = a_chunk_repository()
        repo.save_chunk(chunk)
        find_result = repo.get_chunk_by_memory_id("m1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.id == "rt3"
