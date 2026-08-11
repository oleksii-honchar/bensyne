"""Unit tests for FetchFileUseCase — reconstruct file content from chunks.

Flow:
1. Look up file by file_id
2. Retrieve all chunks via file_chunks table
3. Order by chunk_index (primary), start_line (secondary)
4. Reconstruct content with line continuity
5. Return with file metadata
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.domain.entities.file import File, FileStatus, SourceType
from src.domain.entities.file_chunk import FileChunk, ContentType
from src.domain.result import ErrorWithDetails, Result

NOW = datetime(2026, 1, 1, 0, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.AGENT_SESSION,
    summary: str | None = None,
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        hash=None,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=FileStatus.INDEXED,
        summary=summary,
        created_at=NOW,
        updated_at=NOW,
    )

def _a_chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
    start_line: int = 1,
    end_line: int = 10,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        content_hash="abc",
        content_type=ContentType.TEXT,
        is_partial=False,
        created_at=NOW,
        updated_at=NOW,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mnemosyne_client() -> MagicMock:
    return MagicMock()

@pytest.fixture
def chunk_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def file_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()

@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    chunk_repo: MagicMock,
    file_repo: MagicMock,
    logger: MagicMock,
) -> FetchFileUseCase:
    return FetchFileUseCase(
        mnemosyne_client=mnemosyne_client,
        chunk_repository=chunk_repo,
        file_repository=file_repo,
        logger=logger,
    )

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestFetchFileValidation:
    def test_returns_ko_when_file_id_missing(self, use_case: FetchFileUseCase) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ID_REQUIRED"

    def test_returns_ko_when_file_id_empty(self, use_case: FetchFileUseCase) -> None:
        result = use_case.validate_params({"file_id": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ID_REQUIRED"

    def test_returns_ok_when_file_id_present(self, use_case: FetchFileUseCase) -> None:
        result = use_case.validate_params({"file_id": "f1"})
        assert result.is_ok is True
        assert result.value["file_id"] == "f1"

# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------

class TestFetchFileNotFound:
    def test_returns_ko_when_file_not_found(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"

# ---------------------------------------------------------------------------
# No chunks
# ---------------------------------------------------------------------------

class TestFetchFileNoChunks:
    def test_returns_empty_content_when_no_chunks(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1", path="/tmp/empty.txt")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["content"] == ""
        assert val["chunks"] == []
        assert val["reconstruction_status"] == "partial"

# ---------------------------------------------------------------------------
# Basic content reconstruction
# ---------------------------------------------------------------------------

class TestFetchFileBasicReconstruction:
    def test_reconstructs_content_from_ordered_chunks(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0, start_line=1, end_line=10),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1, start_line=11, end_line=20),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        mnemosyne_client.get.side_effect = [
            {"content": "Line 1 to 10"},
            {"content": "Line 11 to 20"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["content"] == "Line 1 to 10\nLine 11 to 20"
        assert val["reconstruction_status"] == "complete"
        assert len(val["chunks"]) == 2

    def test_chunk_details_included_in_response(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0, start_line=1, end_line=10)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"content": "Some content"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert len(val["chunks"]) == 1
        c = val["chunks"][0]
        assert c["memory_id"] == "mem_1"
        assert c["chunk_index"] == 0
        assert c["start_line"] == 1
        assert c["end_line"] == 10
        assert c["content"] == "Some content"

# ---------------------------------------------------------------------------
# Chunk ordering
# ---------------------------------------------------------------------------

class TestFetchFileChunkOrdering:
    def test_orders_by_chunk_index_not_insertion_order(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Chunks returned out of order should be sorted by chunk_index."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        # Chunks returned in wrong order
        chunks = [
            _a_chunk(id="c3", file_id="f1", memory_id="mem_3", chunk_index=2, start_line=21, end_line=30),
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0, start_line=1, end_line=10),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1, start_line=11, end_line=20),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        mnemosyne_client.get.side_effect = [
            {"content": "Chunk 0"},
            {"content": "Chunk 1"},
            {"content": "Chunk 2"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        # Content should be in correct order
        assert val["content"] == "Chunk 0\nChunk 1\nChunk 2"
        # Chunk list should also be ordered
        assert val["chunks"][0]["chunk_index"] == 0
        assert val["chunks"][1]["chunk_index"] == 1
        assert val["chunks"][2]["chunk_index"] == 2

    def test_fallback_to_start_line_when_chunk_index_tied(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When chunk_index is the same, fall back to start_line ordering."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c_b", file_id="f1", memory_id="mem_b", chunk_index=0, start_line=11, end_line=20),
            _a_chunk(id="c_a", file_id="f1", memory_id="mem_a", chunk_index=0, start_line=1, end_line=10),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        mnemosyne_client.get.side_effect = [
            {"content": "Lines 1-10"},
            {"content": "Lines 11-20"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["content"] == "Lines 1-10\nLines 11-20"
        assert val["chunks"][0]["start_line"] == 1
        assert val["chunks"][1]["start_line"] == 11

# ---------------------------------------------------------------------------
# Missing chunks (partial reconstruction)
# ---------------------------------------------------------------------------

class TestFetchFileMissingChunks:
    def test_marks_partial_when_memory_content_missing(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When a chunk's memory is missing, mark as partial with gap indicator."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1),
            _a_chunk(id="c3", file_id="f1", memory_id="mem_3", chunk_index=2),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        # mem_2 is missing
        mnemosyne_client.get.side_effect = [
            {"content": "Chunk 0"},
            None,
            {"content": "Chunk 2"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["reconstruction_status"] == "partial"
        assert len(val["missing_chunks"]) == 1
        assert val["missing_chunks"][0] == "mem_2"
        # Content should include gap indicator
        assert "<< missing chunk" in val["content"]

    def test_missing_chunks_list_contains_memory_ids(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Missing chunks list should contain the memory_ids of missing chunks."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_5", chunk_index=1),
            _a_chunk(id="c3", file_id="f1", memory_id="mem_9", chunk_index=2),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        # All memories missing
        mnemosyne_client.get.return_value = None

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["reconstruction_status"] == "partial"
        assert set(val["missing_chunks"]) == {"mem_1", "mem_5", "mem_9"}

# ---------------------------------------------------------------------------
# Duplicate chunks
# ---------------------------------------------------------------------------

class TestFetchFileDuplicateChunks:
    def test_deduplicates_by_memory_id(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Duplicate chunks (same memory_id) should be deduplicated."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_1", chunk_index=1),  # duplicate memory_id
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "Deduplicated content"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        # Only one chunk should appear
        assert len(val["chunks"]) == 1
        assert val["chunks"][0]["memory_id"] == "mem_1"
        # Content should only contain one copy
        assert val["content"] == "Deduplicated content"

# ---------------------------------------------------------------------------
# File metadata
# ---------------------------------------------------------------------------

class TestFetchFileMetadata:
    def test_includes_file_metadata_when_requested(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """File metadata should be included in response."""
        file = _a_file(
            id="f1",
            path="/tmp/test.py",
            keywords=["python", "test"],
            tags=["production"],
        )
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"content": "Hello world"}

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "include_metadata": True,
        })
        assert result.is_ok is True

        val = result.value
        assert "file" in val
        f = val["file"]
        assert f["id"] == "f1"
        assert f["path"] == "/tmp/test.py"
        assert f["source_type"] == "agent_session"
        assert f["keywords"] == ["python", "test"]
        assert f["tags"] == ["production"]
        assert f["total_chunks"] == 1

    def test_total_chunks_reflects_chunk_count(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """total_chunks in metadata should equal number of chunks."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1),
            _a_chunk(id="c3", file_id="f1", memory_id="mem_3", chunk_index=2),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "include_metadata": True,
        })
        assert result.is_ok is True

        val = result.value
        assert val["file"]["total_chunks"] == 3

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestFetchFileErrors:
    def test_handles_chunk_repo_error(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """If chunk repo fails, return partial with empty content."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ko([ErrorWithDetails("DB_ERROR", {})])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["content"] == ""
        assert val["chunks"] == []
        assert val["reconstruction_status"] == "partial"

    def test_memory_content_empty_string_treated_as_missing(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When memory has no 'content' key, treat as missing."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"id": "mem_1"}  # no content key

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["reconstruction_status"] == "partial"
        assert val["missing_chunks"] == ["mem_1"]
