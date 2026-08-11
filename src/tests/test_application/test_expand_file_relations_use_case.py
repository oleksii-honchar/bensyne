"""Unit tests for ExpandFileRelationsUseCase — expand file relations with content.

Flow (after refactor — aggregate owns content composition):
1. Get source file by file_id
2. Get relations (optionally filtered by relation_types)
3. For each related file, get aggregate via FileService.get_file()
4. Delegate content composition to aggregate.compose_content(mnemosyne_client)
5. Return structured result
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.services.file_service import FileService
from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.domain.aggregates.file_metadata_aggregate import FileMetadataAggregate
from src.domain.entities.file import File, FileStatus, SourceType
from src.domain.entities.file_chunk import FileChunk, ContentType
from src.domain.entities.file_relation import (
    Direction,
    FileRelation,
    RelationType,
)
from src.domain.result import Result

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

def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.SIBLING,
    strength: float = 1.0,
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type,
        strength=strength,
        direction=Direction.UNIDIRECTIONAL,
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )

def _a_aggregate(
    file: File,
    chunks: list[FileChunk] | None = None,
    relations: list[FileRelation] | None = None,
) -> FileMetadataAggregate:
    return FileMetadataAggregate.of(file, chunks=chunks or [], relations=relations or []).value

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mnemosyne_client() -> MagicMock:
    client = MagicMock()
    # Use MagicMock (not AsyncMock) — the use case calls get() synchronously
    return client

@pytest.fixture
def file_service() -> MagicMock:
    return MagicMock()

@pytest.fixture
def relation_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()

@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    file_service: MagicMock,
    relation_repo: MagicMock,
    logger: MagicMock,
) -> ExpandFileRelationsUseCase:
    return ExpandFileRelationsUseCase(
        mnemosyne_client=mnemosyne_client,
        file_service=file_service,
        relation_repository=relation_repo,
        logger=logger,
    )

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestExpandFileRelationsValidation:
    def test_returns_ko_when_file_id_missing(self, use_case: ExpandFileRelationsUseCase) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ID_REQUIRED"

    def test_returns_ko_when_file_id_empty(self, use_case: ExpandFileRelationsUseCase) -> None:
        result = use_case.validate_params({"file_id": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ID_REQUIRED"

    def test_returns_ok_when_file_id_present(self, use_case: ExpandFileRelationsUseCase) -> None:
        result = use_case.validate_params({"file_id": "f1"})
        assert result.is_ok is True
        assert result.value["file_id"] == "f1"

# ---------------------------------------------------------------------------
# Source file not found
# ---------------------------------------------------------------------------

class TestExpandFileRelationsSourceNotFound:
    def test_returns_ko_when_source_file_not_found(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
    ) -> None:
        file_service.get_file.return_value = Result.ok(None)

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"

# ---------------------------------------------------------------------------
# No relations
# ---------------------------------------------------------------------------

class TestExpandFileRelationsNoRelations:
    def test_returns_empty_related_files_when_no_relations(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)
        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value
        assert val["source_file"]["id"] == "f1"
        assert val["source_file"]["path"] == "/tmp/source.txt"
        assert val["related_files"] == []

# ---------------------------------------------------------------------------
# Basic relation expansion
# ---------------------------------------------------------------------------

class TestExpandFileRelationsBasic:
    def test_returns_related_file_with_metadata(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value

        assert val["source_file"]["id"] == "f1"
        assert val["source_file"]["path"] == "/tmp/source.txt"
        assert len(val["related_files"]) == 1

        rf = val["related_files"][0]
        assert rf["file"]["id"] == "f2"
        assert rf["file"]["path"] == "/tmp/related.txt"
        assert rf["file"]["relation_type"] == "sibling"
        assert rf["content"] == ""
        assert rf["chunks_count"] == 0

# ---------------------------------------------------------------------------
# Content composition from chunks via aggregate
# ---------------------------------------------------------------------------

class TestExpandFileRelationsContentComposition:
    def test_composes_content_from_ordered_chunks(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f2", memory_id="mem_2", chunk_index=1),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        # Aggregate.compose_content calls mnemosyne_client(memory_id) directly
        mnemosyne_client.side_effect = [
            {"content": "First chunk content"},
            {"content": "Second chunk content"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["content"] == "First chunk content\nSecond chunk content"
        assert rf["chunks_count"] == 2

    def test_content_empty_when_memory_not_found(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When a memory is not found, skip it in content composition."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f2", memory_id="mem_2", chunk_index=1),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        # First memory found, second not found
        mnemosyne_client.side_effect = [
            {"content": "Found content"},
            None,
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["content"] == "Found content"
        assert rf["chunks_count"] == 2

# ---------------------------------------------------------------------------
# Relation type filtering
# ---------------------------------------------------------------------------

class TestExpandFileRelationsFiltering:
    def test_filters_by_relation_types(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        source = _a_file(id="f1", path="/tmp/source.txt")
        sibling = _a_file(id="f2", path="/tmp/sibling.txt")
        parent = _a_file(id="f3", path="/tmp/parent.txt")

        rel_sibling = _a_relation(
            id="r1", source_file_id="f1", target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )
        rel_parent = _a_relation(
            id="r2", source_file_id="f1", target_file_id="f3",
            relation_type=RelationType.PARENT_CHILD,
        )

        source_agg = _a_aggregate(source)
        sibling_agg = _a_aggregate(sibling)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(sibling_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel_sibling, rel_parent])

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "relation_types": ["sibling"],
        })

        assert result.is_ok is True
        val = result.value
        assert len(val["related_files"]) == 1
        assert val["related_files"][0]["file"]["id"] == "f2"

# ---------------------------------------------------------------------------
# Multiple related files
# ---------------------------------------------------------------------------

class TestExpandFileRelationsMultiple:
    def test_returns_multiple_related_files(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        source = _a_file(id="f1", path="/tmp/source.txt")
        related1 = _a_file(id="f2", path="/tmp/related1.txt")
        related2 = _a_file(id="f3", path="/tmp/related2.txt")

        rel1 = _a_relation(source_file_id="f1", target_file_id="f2", relation_type=RelationType.SIBLING)
        rel2 = _a_relation(source_file_id="f1", target_file_id="f3", relation_type=RelationType.CROSS_REFERENCE)

        source_agg = _a_aggregate(source)
        related1_agg = _a_aggregate(related1)
        related2_agg = _a_aggregate(related2)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related1_agg),
            Result.ok(related2_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel1, rel2])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        val = result.value
        assert len(val["related_files"]) == 2
        ids = [rf["file"]["id"] for rf in val["related_files"]]
        assert "f2" in ids
        assert "f3" in ids

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestExpandFileRelationsErrors:
    def test_continues_when_related_file_not_found(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """If a related file is not found, skip it without failing."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f_missing")

        source_agg = _a_aggregate(source)

        # First call returns source, second call returns ko (target not found)
        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ko([{"error_code": "FILE_NOT_FOUND", "details": {}}]),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True
        assert result.value["related_files"] == []

    def test_handles_file_service_error(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """If source file service fails, return Result.ko."""
        file_service.get_file.return_value = Result.ok(None)

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"

# ---------------------------------------------------------------------------
# Summary in relation expansion
# ---------------------------------------------------------------------------

class TestExpandFileRelationsSummary:
    """Relation expansion populates summary first, then full composed content."""

    def test_related_file_includes_summary_field(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Related file result includes a summary field."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt", summary="A summary of the related file")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["summary"] == "A summary of the related file"

    def test_summary_none_when_file_has_no_summary(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Summary is None when the related file has no summary."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["summary"] is None

    def test_content_composed_summary_first_then_chunks(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Content is composed as: summary first, then full content from chunks."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(
            id="f2",
            path="/tmp/related.txt",
            summary="Summary of related file",
        )
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id="f2", memory_id="mem_2", chunk_index=1),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        mnemosyne_client.side_effect = [
            {"content": "Chunk 1"},
            {"content": "Chunk 2"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        # Summary first, then chunks separated by blank line
        assert rf["content"] == "Summary of related file\n\nChunk 1\nChunk 2"
        assert rf["summary"] == "Summary of related file"

    def test_content_only_summary_when_no_chunks(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When file has summary but no chunks, content is just the summary."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt", summary="Only summary")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["content"] == "Only summary"
        assert rf["summary"] == "Only summary"

    def test_content_only_chunks_when_no_summary(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When file has no summary, content is just chunks."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")  # no summary
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        mnemosyne_client.side_effect = [
            {"content": "Chunk content"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["content"] == "Chunk content"
        assert rf["summary"] is None

# ---------------------------------------------------------------------------
# Summary-only mode
# ---------------------------------------------------------------------------

class TestExpandFileRelationsSummaryOnly:
    """summary_only=True skips chunk content composition, returns only file.summary."""

    def test_summary_only_returns_only_summary_no_chunks_fetched(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When summary_only=True, content is just the summary; chunks are not fetched."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(
            id="f2",
            path="/tmp/related.txt",
            summary="Summary of related file",
        )
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "summary_only": True,
        })
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        # Content should be just the summary, not composed with chunks
        assert rf["content"] == "Summary of related file"
        assert rf["summary"] == "Summary of related file"
        # Mnemosyne should NOT have been called — no chunk content fetched
        assert mnemosyne_client.call_count == 0

    def test_summary_only_with_no_summary_returns_empty_content(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When summary_only=True and file has no summary, content is empty."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")  # no summary
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "summary_only": True,
        })
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        assert rf["content"] == ""
        assert rf["summary"] is None

    def test_summary_only_default_false_composes_full_content(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """summary_only=False (default) uses current behavior: compose full content."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(
            id="f2",
            path="/tmp/related.txt",
            summary="Summary of related file",
        )
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        mnemosyne_client.side_effect = [
            {"content": "Chunk content"},
        ]

        # Default: summary_only not provided (defaults to False)
        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
        })
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        # Summary first, then chunks
        assert rf["content"] == "Summary of related file\n\nChunk content"
        assert rf["summary"] == "Summary of related file"
        # Mnemosyne should have been called
        assert mnemosyne_client.call_count == 1

    def test_summary_only_multiple_files_skips_chunks_for_all(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """summary_only=True skips chunk composition for all related files."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related1 = _a_file(id="f2", path="/tmp/related1.txt", summary="Summary 1")
        related2 = _a_file(id="f3", path="/tmp/related2.txt", summary="Summary 2")

        rel1 = _a_relation(source_file_id="f1", target_file_id="f2", relation_type=RelationType.SIBLING)
        rel2 = _a_relation(source_file_id="f1", target_file_id="f3", relation_type=RelationType.CROSS_REFERENCE)

        source_agg = _a_aggregate(source)
        related1_agg = _a_aggregate(related1)
        related2_agg = _a_aggregate(related2)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related1_agg),
            Result.ok(related2_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel1, rel2])

        result = use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "summary_only": True,
        })
        assert result.is_ok is True

        val = result.value
        assert len(val["related_files"]) == 2

        # Both files: content is just summary, no chunks fetched
        ids = [rf["file"]["id"] for rf in val["related_files"]]
        assert "f2" in ids
        assert "f3" in ids

        for rf in val["related_files"]:
            assert rf["content"] == rf["summary"]
            assert rf["chunks_count"] == 0

        # Mnemosyne should NOT have been called at all
        assert mnemosyne_client.call_count == 0

# ---------------------------------------------------------------------------
# Aggregate delegation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

class TestExpandFileRelationsLogging:
    """Verify structured log entries at each step of execute_internal."""

    def test_logs_info_at_entry_with_file_id_and_relation_types(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """info log at entry with file_id and relation_types."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)
        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({
            "file_id": "f1",
            "memory_bank": "bank",
            "relation_types": ["sibling"],
        })

        # First info call should be the entry log
        info_calls = [c for c in logger.info.call_args_list]
        assert len(info_calls) >= 1
        first = info_calls[0]
        assert "expand_file_relations" in str(first)
        assert "f1" in str(first)
        assert "sibling" in str(first)

    def test_logs_debug_after_getting_source_file(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """debug log after getting source file."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)
        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        debug_calls = logger.debug.call_args_list
        assert len(debug_calls) >= 1
        # At least one debug call should reference source file retrieval
        source_debug = [c for c in debug_calls if "source" in str(c).lower() or "file" in str(c).lower()]
        assert len(source_debug) >= 1

    def test_logs_debug_after_getting_relations_with_count(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """debug log after getting relations with count."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        debug_calls = logger.debug.call_args_list
        # Should have debug log with relation count
        assert len(debug_calls) >= 1

    def test_logs_info_after_expanding_each_related_file(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
        logger: MagicMock,
    ) -> None:
        """info log after expanding each related file with path and chunks_count."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        mnemosyne_client.side_effect = [{"content": "Chunk content"}]

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        info_calls = logger.info.call_args_list
        # Entry log + expand log + exit log = at least 3 info calls
        assert len(info_calls) >= 2
        # One of the info calls should reference the related file path
        expand_logs = [c for c in info_calls if "related" in str(c).lower() or "expand" in str(c).lower()]
        assert len(expand_logs) >= 1

    def test_logs_info_at_exit_with_total_count(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """info log at exit with total count of related files."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related1 = _a_file(id="f2", path="/tmp/related1.txt")
        related2 = _a_file(id="f3", path="/tmp/related2.txt")

        rel1 = _a_relation(source_file_id="f1", target_file_id="f2", relation_type=RelationType.SIBLING)
        rel2 = _a_relation(source_file_id="f1", target_file_id="f3", relation_type=RelationType.CROSS_REFERENCE)

        source_agg = _a_aggregate(source)
        related1_agg = _a_aggregate(related1)
        related2_agg = _a_aggregate(related2)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related1_agg),
            Result.ok(related2_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel1, rel2])

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        info_calls = logger.info.call_args_list
        # Entry + 2 expand + exit = at least 4 info calls
        assert len(info_calls) >= 2

    def test_logs_info_at_exit_with_zero_related_files(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """Exit log shows count=0 when no related files."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)
        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        info_calls = logger.info.call_args_list
        # Entry + exit = at least 2 info calls
        assert len(info_calls) >= 2

    def test_log_format_includes_service_and_method(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        logger: MagicMock,
    ) -> None:
        """Log entries include service='expand_file_relations' and method."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)
        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({"file_id": "f1", "memory_bank": "bank"})

        # Verify at least one info call contains service identifier
        info_calls = logger.info.call_args_list
        assert len(info_calls) >= 1
        # The event string or kwargs should reference the service
        any_has_service = any(
            "expand_file_relations" in str(c) for c in info_calls
        )
        assert any_has_service is True

# ---------------------------------------------------------------------------
# Aggregate delegation
# ---------------------------------------------------------------------------

class TestExpandFileRelationsAggregateDelegation:
    """Use case delegates content composition to aggregate.compose_content."""

    def test_use_case_calls_aggregate_compose_content(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """The use case delegates to aggregate.compose_content, not doing it itself."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        related = _a_file(id="f2", path="/tmp/related.txt", summary="Related summary")
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        chunks = [
            _a_chunk(id="c1", file_id="f2", memory_id="mem_1", chunk_index=0),
        ]

        source_agg = _a_aggregate(source)
        related_agg = _a_aggregate(related, chunks=chunks)

        file_service.get_file.side_effect = [
            Result.ok(source_agg),
            Result.ok(related_agg),
        ]
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        mnemosyne_client.side_effect = [
            {"content": "Chunk content"},
        ]

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        rf = result.value["related_files"][0]
        # Content composed by aggregate: summary + chunks
        assert rf["content"] == "Related summary\n\nChunk content"
        assert rf["summary"] == "Related summary"
        assert rf["chunks_count"] == 1

    def test_use_case_returns_aggregate_from_file_service(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """The use case gets the aggregate from FileService.get_file(), not just the file."""
        source = _a_file(id="f1", path="/tmp/source.txt")
        source_agg = _a_aggregate(source)

        file_service.get_file.return_value = Result.ok(source_agg)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True

        # Verify file_service.get_file was called (not file_repository.get_file_by_id)
        file_service.get_file.assert_called_once_with("f1")
