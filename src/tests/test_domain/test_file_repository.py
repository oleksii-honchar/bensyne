"""FileRepository interface contract tests.

Verifies that the FileRepository abstract interface defines the correct
method signatures and that an in-memory implementation satisfies the
Result pattern for all operations.
"""

from datetime import datetime
from typing import List, Optional

import pytest

from src.domain.entities.file import File, FileStatus, SourceType
from src.domain.interfaces import FileRepository
from src.domain.result import Result

VALID_HASH = "a" * 64

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    hash: Optional[str] = None,
    file_type: Optional[str] = None,
    size: Optional[int] = None,
    language: Optional[str] = None,
    aggregated_keywords: Optional[List[str]] = None,
    aggregated_tags: Optional[List[str]] = None,
    status: FileStatus = FileStatus.PENDING,
) -> File:
    """Create a valid File instance with sensible defaults."""
    result = File.of({
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
    })
    assert result.is_ok, f"Failed to create test file: {result.errors}"
    return result.value

# ---------------------------------------------------------------------------
# Tests against the abstract interface (no implementation required)
# ---------------------------------------------------------------------------

class TestFileRepositoryInterface:
    """FileRepository defines the correct abstract interface."""

    def test_file_repository_is_abstract(self):
        from src.domain.interfaces import FileRepository
        # Instantiation should fail because it's abstract
        with pytest.raises(TypeError):
            FileRepository()  # type: ignore

    def test_file_repository_has_save_file_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "save_file")
        assert callable(getattr(FileRepository, "save_file"))

    def test_file_repository_has_get_file_by_id_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "get_file_by_id")
        assert callable(getattr(FileRepository, "get_file_by_id"))

    def test_file_repository_has_get_file_by_path_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "get_file_by_path")
        assert callable(getattr(FileRepository, "get_file_by_path"))

    def test_file_repository_has_list_files_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "list_files")
        assert callable(getattr(FileRepository, "list_files"))

    def test_file_repository_has_search_files_by_query_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "search_files_by_query")
        assert callable(getattr(FileRepository, "search_files_by_query"))

    def test_file_repository_has_delete_file_method(self):
        from src.domain.interfaces import FileRepository
        assert hasattr(FileRepository, "delete_file")
        assert callable(getattr(FileRepository, "delete_file"))

    def test_save_file_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "save_file")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_file_by_id_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "get_file_by_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_file_by_path_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "get_file_by_path")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_list_files_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "list_files")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_search_files_by_query_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "search_files_by_query")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_delete_file_is_abstract(self):
        from src.domain.interfaces import FileRepository
        method = getattr(FileRepository, "delete_file")
        assert getattr(method, "__isabstractmethod__", False) is True

# ---------------------------------------------------------------------------
# In-memory implementation for contract verification
# ---------------------------------------------------------------------------

class InMemoryFileRepository(FileRepository):
    """Minimal in-memory FileRepository for contract testing."""

    def __init__(self, data: Optional[List[File]] = None) -> None:
        self._store: dict[str, File] = {}
        if data:
            for f in data:
                self._store[f.id] = f

    def save_file(self, file: File) -> Result[File]:
        self._store[file.id] = file
        return Result.ok(file)

    def get_file_by_id(self, file_id: str) -> Result[Optional[File]]:
        return Result.ok(self._store.get(file_id))

    def get_file_by_path(self, path: str) -> Result[Optional[File]]:
        for f in self._store.values():
            if f.path == path:
                return Result.ok(f)
        return Result.ok(None)

    def list_files(self) -> Result[List[File]]:
        return Result.ok(list(self._store.values()))

    def search_files_by_query(self, query: str) -> Result[List[File]]:
        query_lower = query.lower()
        matches = [
            f for f in self._store.values()
            if query_lower in f.path.lower()
            or any(query_lower in kw.lower() for kw in f.aggregated_keywords)
            or any(query_lower in tag.lower() for tag in f.aggregated_tags)
        ]
        return Result.ok(matches)

    def delete_file(self, file_id: str) -> Result[bool]:
        if file_id in self._store:
            del self._store[file_id]
            return Result.ok(True)
        return Result.ok(False)

def a_file_repository(data: Optional[List[File]] = None) -> InMemoryFileRepository:
    return InMemoryFileRepository(data)

# ---------------------------------------------------------------------------
# Contract tests against in-memory implementation
# ---------------------------------------------------------------------------

class TestFileRepositoryContract:
    """In-memory FileRepository satisfies the Result contract for all operations."""

    def test_implementation_is_instance_of_file_repository(self):
        from src.domain.interfaces import FileRepository
        repo = a_file_repository()
        assert isinstance(repo, FileRepository)

    # --- save_file ---

    def test_save_file_returns_result_ok_with_file(self):
        file = _a_file(id="s1")
        repo = a_file_repository()
        result = repo.save_file(file)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "s1"

    def test_save_file_overwrites_existing(self):
        file1 = _a_file(id="s2", path="/tmp/first.txt")
        file2 = _a_file(id="s2", path="/tmp/second.txt")
        repo = a_file_repository()
        repo.save_file(file1)
        result = repo.save_file(file2)
        assert result.is_ok is True
        assert result.value.path == "/tmp/second.txt"
        find_result = repo.get_file_by_id("s2")
        assert find_result.is_ok is True
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/second.txt"

    # --- get_file_by_id ---

    def test_get_file_by_id_returns_result_ok_with_file(self):
        file = _a_file(id="g1")
        repo = a_file_repository(data=[file])
        result = repo.get_file_by_id("g1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "g1"

    def test_get_file_by_id_returns_none_when_not_found(self):
        repo = a_file_repository()
        result = repo.get_file_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    # --- get_file_by_path ---

    def test_get_file_by_path_returns_result_ok_with_file(self):
        file = _a_file(id="p1", path="/tmp/unique.txt")
        repo = a_file_repository(data=[file])
        result = repo.get_file_by_path("/tmp/unique.txt")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "p1"

    def test_get_file_by_path_returns_none_when_not_found(self):
        repo = a_file_repository()
        result = repo.get_file_by_path("/tmp/notfound.txt")
        assert result.is_ok is True
        assert result.value is None

    # --- list_files ---

    def test_list_files_returns_empty_list_when_no_files(self):
        repo = a_file_repository()
        result = repo.list_files()
        assert result.is_ok is True
        assert result.value == []

    def test_list_files_returns_all_saved_files(self):
        f1 = _a_file(id="l1", path="/tmp/a.txt")
        f2 = _a_file(id="l2", path="/tmp/b.txt")
        repo = a_file_repository(data=[f1, f2])
        result = repo.list_files()
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {f.id for f in result.value}
        assert ids == {"l1", "l2"}

    # --- search_files_by_query ---

    def test_search_files_by_query_matches_path(self):
        f1 = _a_file(id="q1", path="/tmp/test.txt")
        f2 = _a_file(id="q2", path="/tmp/other.txt")
        repo = a_file_repository(data=[f1, f2])
        result = repo.search_files_by_query("test")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q1"

    def test_search_files_by_query_matches_keywords(self):
        f1 = _a_file(id="q3", path="/tmp/x.txt", aggregated_keywords=["domain"])
        f2 = _a_file(id="q4", path="/tmp/y.txt", aggregated_keywords=["infra"])
        repo = a_file_repository(data=[f1, f2])
        result = repo.search_files_by_query("domain")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q3"

    def test_search_files_by_query_matches_tags(self):
        f1 = _a_file(id="q5", path="/tmp/a.txt", aggregated_tags=["core"])
        f2 = _a_file(id="q6", path="/tmp/b.txt", aggregated_tags=["util"])
        repo = a_file_repository(data=[f1, f2])
        result = repo.search_files_by_query("core")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "q5"

    def test_search_files_by_query_returns_empty_when_no_matches(self):
        f1 = _a_file(id="q7", path="/tmp/a.txt")
        repo = a_file_repository(data=[f1])
        result = repo.search_files_by_query("nonexistent")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

    def test_search_files_by_query_is_case_insensitive(self):
        f1 = _a_file(id="q8", path="/tmp/Test.txt")
        repo = a_file_repository(data=[f1])
        result = repo.search_files_by_query("test")
        assert result.is_ok is True
        assert len(result.value) == 1

    # --- delete_file ---

    def test_delete_file_returns_true_when_found(self):
        file = _a_file(id="d1")
        repo = a_file_repository(data=[file])
        result = repo.delete_file("d1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_file_returns_false_when_not_found(self):
        repo = a_file_repository()
        result = repo.delete_file("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_delete_file_removes_from_store(self):
        file = _a_file(id="d2")
        repo = a_file_repository(data=[file])
        repo.delete_file("d2")
        find_result = repo.get_file_by_id("d2")
        assert find_result.is_ok is True
        assert find_result.value is None

    # --- round-trip ---

    def test_round_trip_save_and_get_by_id(self):
        file = _a_file(id="rt1", path="/tmp/roundtrip.txt")
        repo = a_file_repository()
        save_result = repo.save_file(file)
        assert save_result.is_ok
        find_result = repo.get_file_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.path == "/tmp/roundtrip.txt"

    def test_round_trip_save_and_get_by_path(self):
        file = _a_file(id="rt2", path="/tmp/by_path.txt")
        repo = a_file_repository()
        repo.save_file(file)
        find_result = repo.get_file_by_path("/tmp/by_path.txt")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.id == "rt2"
