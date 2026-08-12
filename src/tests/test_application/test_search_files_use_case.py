"""Unit tests for SearchFilesUseCase — two-phase file search.

Phase 1: query memories via mnemosyne client.
Phase 2: enrich with file metadata from SQLite repositories.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk, ContentType
from src.domain.file_relation_entity import FileRelation, RelationType, Direction
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock

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
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=0,
        content_hash="abc",
        content_type=ContentType.TEXT,
        is_partial=False,
        created_at=NOW,
        updated_at=NOW,
    )

def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.SIBLING,
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type,
        strength=1.0,
        direction=Direction.UNIDIRECTIONAL,
        description="",
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
def relation_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def logger() -> LoggerMock:
    return LoggerMock()

@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    chunk_repo: MagicMock,
    file_repo: MagicMock,
    relation_repo: MagicMock,
    logger: LoggerMock,
) -> SearchFilesUseCase:
    return SearchFilesUseCase(
        mnemosyne_client=mnemosyne_client,
        chunk_repository=chunk_repo,
        file_repository=file_repo,
        relation_repository=relation_repo,
        logger=logger,
    )

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseValidation:
    def test_returns_ko_when_query_empty(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({"query": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_returns_ko_when_query_missing(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_returns_ok_when_query_present(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({"query": "search term"})
        assert result.is_ok is True
        assert result.value["query"] == "search term"

# ---------------------------------------------------------------------------
# Phase 1 — No memories recalled
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseNoMemories:
    def test_returns_empty_results_when_no_memories(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        mnemosyne_client.recall.return_value = []

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["results"] == []
        assert result.value["total_count"] == 0

# ---------------------------------------------------------------------------
# Phase 2 — Memories with no file context (non-file memories)
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseNonFileMemories:
    def test_returns_non_file_memory_when_no_chunk(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """Memory without file context should appear as non-file result."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Some memory", "importance": 0.8, "relevance_score": 0.9},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(None)

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1
        # Non-file memory: no file context
        r = results[0]
        assert r["memory_id"] == "mem_1"
        assert r["file"] is None
        assert r["matched_memories"] == []

# ---------------------------------------------------------------------------
# Phase 2 — Memories with file context (enriched)
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseFileMemories:
    def test_returns_enriched_file_result(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Memory with file context should be enriched with file metadata."""
        file = _a_file(id="f1", path="/tmp/test.txt", keywords=["test"], tags=["docs"])
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "File content preview", "importance": 0.7, "relevance_score": 0.85},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1
        r = results[0]
        assert r["file"] is not None
        assert r["file"]["id"] == "f1"
        assert r["file"]["path"] == "/tmp/test.txt"
        assert r["file"]["keywords"] == ["test"]
        assert r["file"]["tags"] == ["docs"]
        assert len(r["matched_memories"]) == 1
        assert r["matched_memories"][0]["id"] == "mem_1"
        assert r["related_files_count"] == 0

    def test_groups_memories_by_file(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Multiple memories from same file should be grouped."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        chunk2 = _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "First chunk", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Second chunk", "importance": 0.6, "relevance_score": 0.8},
        ]

        # Both memories map to same file
        chunk_repo.get_chunk_by_memory_id.side_effect = [
            Result.ok(chunk1),
            Result.ok(chunk2),
        ]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1  # Grouped into single file result
        r = results[0]
        assert r["file"]["id"] == "f1"
        assert len(r["matched_memories"]) == 2

    def test_matched_memories_include_chunk_info(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Matched memories should include chunk_index and section_header."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=2)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content preview here", "importance": 0.7, "relevance_score": 0.85},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        r = result.value["results"][0]
        matched = r["matched_memories"]
        assert len(matched) == 1
        m = matched[0]
        assert m["id"] == "mem_1"
        assert m["chunk_index"] == 2
        assert m["importance"] == 0.7
        assert m["relevance_score"] == 0.85

# ---------------------------------------------------------------------------
# Phase 2 — Relations inclusion
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseRelations:
    def test_related_files_count_without_relations_flag(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When include_relations is False (default), still count relations."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([relation])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
            "include_relations": False,
        })

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["related_files_count"] == 1
        # Relations not expanded
        assert "related_files" not in r or r.get("related_files") is None

    def test_related_files_included_when_flag_true(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When include_relations is True, include related file details."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2")
        related_file = _a_file(id="f2", path="/tmp/related.txt")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([relation])

        # When resolving related file, return the related file
        def file_by_id_side_effect(file_id: str) -> Result[File]:
            if file_id == "f2":
                return Result.ok(related_file)
            return Result.ok(file)

        file_repo.get_file_by_id.side_effect = file_by_id_side_effect

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
            "include_relations": True,
        })

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["related_files_count"] == 1
        assert "related_files" in r
        assert len(r["related_files"]) == 1
        rf = r["related_files"][0]
        assert rf["id"] == "f2"
        assert rf["path"] == "/tmp/related.txt"

# ---------------------------------------------------------------------------
# Phase 2 — Mixed results (file + non-file memories)
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseMixedResults:
    def test_returns_both_file_and_non_file_memories(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Results should contain both file-backed and non-file memories."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "File content", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Standalone memory", "importance": 0.5, "relevance_score": 0.6},
        ]
        # mem_1 has file context, mem_2 does not
        chunk_repo.get_chunk_by_memory_id.side_effect = [
            Result.ok(chunk),
            Result.ok(None),
        ]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 2

        # Non-file memory comes first (added to all_results before file results)
        r_non_file = [r for r in results if r["file"] is None]
        r_file = [r for r in results if r["file"] is not None]
        assert len(r_non_file) == 1
        assert len(r_file) == 1

        assert r_non_file[0]["memory_id"] == "mem_2"
        assert r_file[0]["file"]["id"] == "f1"

# ---------------------------------------------------------------------------
# Limit enforcement
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseLimit:
    def test_respects_limit_parameter(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Limit should be passed to mnemosyne recall."""
        mnemosyne_client.recall.return_value = []

        use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
            "limit": 3,
        })

        mnemosyne_client.recall.assert_called_once_with("search term", 3)

    def test_uses_default_limit(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Default limit of 10 should be used when not specified."""
        mnemosyne_client.recall.return_value = []

        use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        mnemosyne_client.recall.assert_called_once_with("search term", 10)

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestSearchFilesUseCaseErrors:
    def test_handles_recall_failure(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When mnemosyne recall fails, return Result.ko."""
        mnemosyne_client.recall.return_value = Result.ko([ErrorWithDetails("DATABASE_ERROR", {})])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ko is True
        assert result.errors[0].error_code == "DATABASE_ERROR"

    def test_continues_when_chunk_lookup_fails(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """If chunk lookup fails, treat memory as non-file (don't crash)."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ko([ErrorWithDetails("DB_ERROR", {})])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        # Should still return ok — treat as non-file memory
        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["file"] is None

    def test_continues_when_file_lookup_fails(self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
    ) -> None:
        """If file lookup fails, treat memory as non-file."""
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {})])

        result = use_case.execute({
            "query": "search term",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["file"] is None
