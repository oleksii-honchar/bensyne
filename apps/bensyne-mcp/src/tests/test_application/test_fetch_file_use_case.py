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
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk, ContentType
from src.utils.result import ErrorWithDetails, Result

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
    hash: str | None = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=None,
        hash=hash,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=FileStatus.INDEXED,
        summary=summary,
        total_chunks=0,
        average_importance=0.5,
        metadata={},
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
    section_header: str | None = None,
    content_hash: str | None = "abc",
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        content_hash=content_hash,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=section_header,
        parent_unit_ref=None,
        parent_unit_summary=None,
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

        result = use_case.execute(
            {
                "file_id": "f1",
                "memory_bank": "bank",
                "include_metadata": True,
            }
        )
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

        result = use_case.execute(
            {
                "file_id": "f1",
                "memory_bank": "bank",
                "include_metadata": True,
            }
        )
        assert result.is_ok is True

        val = result.value
        assert val["file"]["total_chunks"] == 3


# ---------------------------------------------------------------------------
# Dual-hash wire contract (D15) — chunk_hash on chunk entries, file_hash on
# the include_metadata file block (null-tolerant for legacy NULLs — S7)
# ---------------------------------------------------------------------------


class TestFetchFileHashSurfacing:
    def test_chunk_entries_carry_content_hash(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Default mode: each chunk entry carries the chunk row's content_hash."""
        file = _a_file(id="f1")
        hash_1 = "1" * 64
        hash_2 = "2" * 64
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1", chunk_index=0, content_hash=hash_1),
            _a_chunk(id="c2", memory_id="mem_2", chunk_index=1, content_hash=hash_2),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert [c["chunk_hash"] for c in val["chunks"]] == [hash_1, hash_2]

    def test_chunk_hash_null_tolerant_when_content_hash_absent(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Legacy chunk row with NULL content_hash ⇒ chunk_hash is null, not an error."""
        file = _a_file(id="f1")
        chunk = _a_chunk(id="c1", memory_id="mem_1", chunk_index=0, content_hash=None)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        assert result.value["chunks"][0]["chunk_hash"] is None

    def test_neighbor_mode_chunk_entries_carry_content_hash(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """Neighbor mode: window chunk entries also carry their content_hash."""
        file = _a_file(id="f1")
        hash_2 = "2" * 64
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1", chunk_index=1, content_hash="1" * 64),
            _a_chunk(id="c2", memory_id="mem_2", chunk_index=2, content_hash=hash_2),
        ]

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne = _mnemosyne_for(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 1, "adjacent_chunks": 1}
        )
        assert result.is_ok is True

        val = result.value
        assert [c["chunk_index"] for c in val["chunks"]] == [1, 2]
        assert val["chunks"][0]["chunk_hash"] == "1" * 64
        assert val["chunks"][1]["chunk_hash"] == hash_2

    def test_include_metadata_file_block_carries_file_hash(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """include_metadata file block carries file_hash = File.hash entity value."""
        file_hash = "f" * 64
        file = _a_file(id="f1", path="/tmp/test.py", hash=file_hash)
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"content": "Hello world"}

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "include_metadata": True}
        )
        assert result.is_ok is True

        f = result.value["file"]
        assert f["file_hash"] == file_hash

    def test_include_metadata_file_hash_null_tolerant(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Legacy File row with NULL hash ⇒ file_hash is null, not an error."""
        file = _a_file(id="f1", hash=None)
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = {"content": "Hello world"}

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "include_metadata": True}
        )
        assert result.is_ok is True

        assert result.value["file"]["file_hash"] is None

    def test_chunk_hash_present_on_missing_memory_chunks_too(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Chunk entries for MISSING memories (gap indicators) still carry their
        chunk_hash — the hash is a property of the chunk row, not the content."""
        file = _a_file(id="f1")
        hash_1 = "1" * 64
        chunk = _a_chunk(id="c1", memory_id="mem_1", chunk_index=0, content_hash=hash_1)

        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk])
        mnemosyne_client.get.return_value = None

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert val["reconstruction_status"] == "partial"
        assert val["chunks"][0]["chunk_hash"] == hash_1


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


# ---------------------------------------------------------------------------
# Neighbor-chunk mode (center_chunk_index + adjacent_chunks)
# ---------------------------------------------------------------------------


def _five_chunks(file_id: str = "f1") -> list[FileChunk]:
    """Five chunks with distinct memory_ids, lines 1..50, section headers."""
    return [
        _a_chunk(
            id=f"c{i}",
            file_id=file_id,
            memory_id=f"mem_{i}",
            chunk_index=i,
            start_line=i * 10 + 1,
            end_line=(i + 1) * 10,
            section_header=f"Section {i}" if i % 2 == 0 else None,
        )
        for i in range(5)
    ]


def _mnemosyne_for(chunks: list[FileChunk]) -> MagicMock:
    """Mnemosyne mock returning per-chunk content keyed by memory_id."""
    client = MagicMock()
    contents = {c.memory_id: f"content of {c.memory_id}" for c in chunks}
    client.get.side_effect = lambda mid: {"content": contents[mid]} if mid in contents else None
    return client


class TestFetchFileNeighborMode:
    def test_returns_window_of_center_plus_adjacent_in_ascending_order(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """center=2, N=1 on 5-chunk file ⇒ exactly chunks [1,2,3] with full per-chunk shape."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.side_effect = lambda mid: {"content": f"content of {mid}"}

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 2, "adjacent_chunks": 1}
        )
        assert result.is_ok is True

        val = result.value
        assert [c["chunk_index"] for c in val["chunks"]] == [1, 2, 3]
        # Full per-chunk shape: content + position + section_header
        expected = {
            1: ("mem_1", 11, 20, "content of mem_1", None),
            2: ("mem_2", 21, 30, "content of mem_2", "Section 2"),
            3: ("mem_3", 31, 40, "content of mem_3", None),
        }
        for c in val["chunks"]:
            memory_id, start_line, end_line, content, header = expected[c["chunk_index"]]
            assert set(c.keys()) == {
                "memory_id",
                "chunk_index",
                "start_line",
                "end_line",
                "content",
                "section_header",
                "chunk_hash",
            }
            assert c["memory_id"] == memory_id
            assert c["start_line"] == start_line
            assert c["end_line"] == end_line
            assert c["content"] == content
            assert c["section_header"] == header

    def test_clamps_window_at_start_of_file(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """center=0, N=2 ⇒ chunks [0,1,2] (clamped at 0)."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne = _mnemosyne_for(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 0, "adjacent_chunks": 2}
        )
        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [0, 1, 2]

    def test_clamps_window_at_end_of_file(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """center=4, N=2 ⇒ chunks [2,3,4] (clamped at total-1)."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne = _mnemosyne_for(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 4, "adjacent_chunks": 2}
        )
        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [2, 3, 4]

    def test_zero_adjacent_returns_center_only(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """center=2, N=0 ⇒ exactly chunk [2]."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne = _mnemosyne_for(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 2, "adjacent_chunks": 0}
        )
        assert result.is_ok is True
        val = result.value
        assert [c["chunk_index"] for c in val["chunks"]] == [2]
        assert val["chunks"][0]["memory_id"] == "mem_2"

    def test_neighbor_mode_does_not_reconstruct_full_content(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Neighbor mode returns the window instead of whole-file reconstruction."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.side_effect = lambda mid: {"content": f"content of {mid}"}

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 2, "adjacent_chunks": 1}
        )
        assert result.is_ok is True
        val = result.value
        # Only the window's memories are fetched — not all 5
        fetched = {call.args[0] for call in mnemosyne_client.get.call_args_list}
        assert fetched == {"mem_1", "mem_2", "mem_3"}


class TestFetchFileNeighborModeValidation:
    def test_adjacent_chunks_above_max_is_error(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """adjacent_chunks=6 ⇒ error result, no exception."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 2, "adjacent_chunks": 6}
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "ADJACENT_CHUNKS_OUT_OF_RANGE"

    def test_adjacent_chunks_negative_is_error(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """adjacent_chunks=-1 ⇒ error result, no exception."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 2, "adjacent_chunks": -1}
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "ADJACENT_CHUNKS_OUT_OF_RANGE"

    def test_center_below_zero_is_error(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """center_chunk_index=-1 ⇒ error result (documented decision: error over clamp)."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": -1, "adjacent_chunks": 1}
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "CENTER_CHUNK_INDEX_OUT_OF_RANGE"

    def test_center_at_total_chunks_is_error(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """center_chunk_index=5 on 5-chunk file ⇒ error result (documented decision)."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 5, "adjacent_chunks": 1}
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "CENTER_CHUNK_INDEX_OUT_OF_RANGE"

    def test_center_out_of_range_does_not_touch_mnemosyne(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Out-of-range center ⇒ no partial output — mnemosyne never queried."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = use_case.execute(
            {"file_id": "f1", "memory_bank": "bank", "center_chunk_index": 99, "adjacent_chunks": 1}
        )
        assert result.is_ko is True
        mnemosyne_client.get.assert_not_called()


class TestFetchFileDefaultModeUnchanged:
    def test_shape_stable_without_center_param(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Without center_chunk_index the response shape is identical to whole-file reconstruction."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.side_effect = lambda mid: {"content": f"content of {mid}"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert set(val.keys()) == {"file", "content", "chunks", "reconstruction_status", "missing_chunks"}
        # Whole-file reconstruction: all 5 chunks, full content joined
        assert [c["chunk_index"] for c in val["chunks"]] == [0, 1, 2, 3, 4]
        for c in val["chunks"]:
            assert set(c.keys()) == {
                "memory_id",
                "chunk_index",
                "start_line",
                "end_line",
                "content",
                "chunk_hash",
            }
        assert val["content"] == "\n".join(f"content of mem_{i}" for i in range(5))
        assert val["reconstruction_status"] == "complete"

    def test_adjacent_chunks_alone_without_center_is_ignored(
        self,
        use_case: FetchFileUseCase,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """adjacent_chunks without center_chunk_index ⇒ default whole-file behavior."""
        file = _a_file(id="f1")
        chunks = _five_chunks()
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.side_effect = lambda mid: {"content": f"content of {mid}"}

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank", "adjacent_chunks": 3})
        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [0, 1, 2, 3, 4]
