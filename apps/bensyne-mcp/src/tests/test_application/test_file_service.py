"""Unit tests for FileService application service.

FileService orchestrates file operations using the FileMetadata
and repository pattern. It emits domain events on state changes and uses
the Result pattern for error handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation, RelationType, Direction
from src.domain.events.file_events import (
    FileDeletedEvent,
)
from src.utils.result import ErrorWithDetails, Result
from src.domain.models.file_chunk_model import ContentType as ChunkContentType
from src.utils.structured_logging import LoggerMock

NOW = datetime(2026, 1, 1, 0, 0, 0)
VALID_HASH = "a" * 64

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.AGENT_SESSIONS,
    status: FileStatus = FileStatus.PENDING,
    summary: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=None,
        hash=VALID_HASH,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=status,
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
    start_line: int = 0,
    end_line: int = 0,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        content_hash="abc",
        content_type=ChunkContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.SIBLING,
    strength: float = 1.0,
    direction: Direction = Direction.UNIDIRECTIONAL,
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type,
        strength=strength,
        direction=direction,
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def file_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def chunk_repo() -> MagicMock:
    repo = MagicMock()
    # Default stub for the keep-set prune call in the persist contract.
    repo.delete_chunks_by_file_id.return_value = Result.ok(True)
    return repo


@pytest.fixture
def relation_repo() -> MagicMock:
    repo = MagicMock()
    # Default stub for the forget-symmetry cleanup call (delete_file path).
    repo.delete_relations_by_file_id.return_value = Result.ok(True)
    return repo


# ---------------------------------------------------------------------------
# Import the service — will fail until implemented
# ---------------------------------------------------------------------------

from src.application.services.file_service import FileService  # noqa: E402


@pytest.fixture
def logger_mock() -> LoggerMock:
    return LoggerMock()


@pytest.fixture
def service(
    file_repo: MagicMock,
    chunk_repo: MagicMock,
    relation_repo: MagicMock,
    logger_mock: LoggerMock,
) -> FileService:
    return FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=logger_mock,
    )


# ===================================================================
# update_file
# ===================================================================


class TestUpdateFile:
    """update_file(bank, file_id, props) — typed partial update of an existing file."""

    def test_returns_updated_file(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1", path="/tmp/old.txt")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        updated = _a_file(id="f1", path="/tmp/old.txt", keywords=["new_kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        result = service.update_file("bank1", "f1", {"hash": "b" * 64})

        assert result.is_ok is True
        file_repo.save_file.assert_called_once()

    def test_returns_ko_when_file_not_found(self, service: FileService, file_repo: MagicMock) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.update_file("bank1", "nonexistent", {"hash": "b" * 64})

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_returns_ko_when_file_is_deleted(self, service: FileService, file_repo: MagicMock) -> None:
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.get_file_by_id.return_value = Result.ok(deleted)

        result = service.update_file("bank1", "f1", {"hash": "b" * 64})

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_emits_file_updated_event(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        updated = _a_file(id="f1", keywords=["kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        result = service.update_file("bank1", "f1", {"hash": "b" * 64})

        assert result.is_ok is True
        # update_metadata emits FileUpdatedEvent
        assert result.has_events() is True

    def test_partial_update_updates_only_supplied_fields(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        """Only the keys present in props are changed; everything else is kept."""
        existing = _a_file(id="f1", summary="old summary")
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        file_repo.save_file.return_value = Result.ok(existing)

        result = service.update_file("bank1", "f1", {"summary": "new summary"})

        assert result.is_ok is True
        saved = file_repo.save_file.call_args.args[0]
        # Supplied field changed...
        assert saved.summary == "new summary"
        # ...unsupplied fields preserved from the loaded file.
        assert saved.hash == VALID_HASH
        assert saved.path == existing.path
        assert saved.file_type is None
        assert saved.size is None

    def test_invalid_value_returns_ko_and_writes_nothing(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        """Invalid value (size < 0, per FileSchema ge=0) → ko, no write issued."""
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        result = service.update_file("bank1", "f1", {"size": -1})

        assert result.is_ko is True
        # The stored row is untouched — no save is issued on the invalid path.
        file_repo.save_file.assert_not_called()

    def test_update_file_can_set_source_type_via_props(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        """A newly-updatable field (source_type) is set via props destructuring."""
        existing = _a_file(id="f1")  # default source_type = AGENT_SESSIONS
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        file_repo.save_file.return_value = Result.ok(existing)

        result = service.update_file("bank1", "f1", {"source_type": SourceType.VAULT})

        assert result.is_ok is True
        saved = file_repo.save_file.call_args.args[0]
        assert saved.source_type == SourceType.VAULT


# ===================================================================
# delete_file
# ===================================================================


class TestDeleteFile:
    """delete_file marks file as deleted via mark_deleted() and saves."""

    def test_returns_deleted_file(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted_file)

        result = service.delete_file("f1")

        assert result.is_ok is True
        assert result.value.status == FileStatus.DELETED
        file_repo.save_file.assert_called_once()

    def test_returns_ko_when_file_not_found(self, service: FileService, file_repo: MagicMock) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.delete_file("nonexistent")

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_emits_file_deleted_event(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted_file)

        result = service.delete_file("f1")

        assert result.is_ok is True
        assert result.has_events() is True
        assert any(isinstance(e, FileDeletedEvent) for e in result.get_events())

    def test_returns_ko_when_already_deleted(self, service: FileService, file_repo: MagicMock) -> None:
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.get_file_by_id.return_value = Result.ok(deleted)

        result = service.delete_file("f1")

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_deletes_relation_rows_on_delete(self, service: FileService, file_repo: MagicMock) -> None:
        """delete_file removes the file's relation rows (forget symmetry)."""
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted_file)

        result = service.delete_file("f1")

        assert result.is_ok is True
        service.relation_repository.delete_relations_by_file_id.assert_called_once_with("f1")

    def test_relation_delete_failure_does_not_fail_delete(self, service: FileService, file_repo: MagicMock) -> None:
        """A relation-delete error degrades the delete to ko — no silent dangling rows."""
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted_file)
        service.relation_repository.delete_relations_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("RELATION_DELETE_BY_FILE_ID_ERROR", {"error": "boom"})]
        )

        result = service.delete_file("f1")

        assert result.is_ko is True
        assert result.errors[0].error_code == "RELATION_DELETE_BY_FILE_ID_ERROR"


# ===================================================================
# get_file (unified)
# ===================================================================


class TestGetFile:
    """get_file returns a FileMetadata with configurable chunks and relations."""

    def test_returns_aggregate_with_both_chunks_and_relations_by_default(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Default: include_chunks=True, include_relations=True."""
        file = _a_file(id="f1")
        chunks = [_a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)]
        relations = [_a_relation(id="r1", source_file_id="f1", target_file_id="f2")]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        relation_repo.get_relations_by_file_id.return_value = Result.ok(relations)

        result = service.get_file("f1")

        assert result.is_ok is True
        agg = result.value
        assert isinstance(agg, FileMetadata)
        assert agg.file.id == "f1"
        assert len(agg.chunks) == 1
        assert agg.chunks[0].memory_id == "mem_1"
        assert len(agg.relations) == 1
        assert agg.relations[0].target_file_id == "f2"

    def test_returns_ko_when_file_not_found(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.get_file("nonexistent")

        assert result.is_ko is True

    def test_excludes_chunks_when_include_chunks_false(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When include_chunks=False, chunks repo should NOT be called."""
        file = _a_file(id="f1")
        relations = [_a_relation(id="r1", source_file_id="f1", target_file_id="f2")]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok(relations)

        result = service.get_file("f1", include_chunks=False)

        assert result.is_ok is True
        agg = result.value
        assert len(agg.chunks) == 0
        assert len(agg.relations) == 1
        # Chunks repo should NOT have been called
        chunk_repo.get_chunks_by_file_id.assert_not_called()

    def test_excludes_relations_when_include_relations_false(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When include_relations=False, relations repo should NOT be called."""
        file = _a_file(id="f1")
        chunks = [_a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)]
        relations = [_a_relation(id="r1", source_file_id="f1", target_file_id="f2")]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        relation_repo.get_relations_by_file_id.return_value = Result.ok(relations)

        result = service.get_file("f1", include_relations=False)

        assert result.is_ok is True
        agg = result.value
        assert len(agg.chunks) == 1
        assert len(agg.relations) == 0
        # Relations repo should NOT have been called
        relation_repo.get_relations_by_file_id.assert_not_called()

    def test_filters_relations_by_relation_types(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """relation_types filters relations when include_relations=True."""
        file = _a_file(id="f1")
        sibling = _a_relation(id="r1", source_file_id="f1", target_file_id="f2", relation_type=RelationType.SIBLING)
        parent = _a_relation(id="r2", source_file_id="f1", target_file_id="f3", relation_type=RelationType.PARENT_CHILD)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([sibling, parent])

        result = service.get_file("f1", relation_types=[RelationType.SIBLING])

        assert result.is_ok is True
        agg = result.value
        assert len(agg.relations) == 1
        assert agg.relations[0].relation_type == RelationType.SIBLING

    def test_excludes_both_chunks_and_relations(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When both flags are False, only the file is loaded."""
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = service.get_file("f1", include_chunks=False, include_relations=False)

        assert result.is_ok is True
        agg = result.value
        assert agg.file.id == "f1"
        assert len(agg.chunks) == 0
        assert len(agg.relations) == 0
        chunk_repo.get_chunks_by_file_id.assert_not_called()
        relation_repo.get_relations_by_file_id.assert_not_called()

    def test_relation_types_ignored_when_include_relations_false(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """relation_types has no effect when include_relations=False."""
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = service.get_file(
            "f1",
            include_relations=False,
            relation_types=[RelationType.SIBLING],
        )

        assert result.is_ok is True
        agg = result.value
        assert len(agg.relations) == 0
        relation_repo.get_relations_by_file_id.assert_not_called()


# ===================================================================
# Read passthroughs (enrichment consumers — D11)
# ===================================================================


class TestReadPassthroughs:
    """Additive read passthroughs used by FileEnrichmentService."""

    def test_get_file_by_id_delegates_to_file_repository(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)

        result = service.get_file_by_id("f1")

        assert result.is_ok is True
        assert result.value is file
        file_repo.get_file_by_id.assert_called_once_with("f1")

    def test_get_file_by_id_returns_none_when_missing(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.get_file_by_id("missing")

        assert result.is_ok is True
        assert result.value is None

    def test_get_chunks_by_file_id_delegates_to_chunk_repository(
        self, service: FileService, chunk_repo: MagicMock
    ) -> None:
        chunks = [_a_chunk(id="c1", memory_id="mem_1"), _a_chunk(id="c2", file_id="f1", memory_id="mem_2")]
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)

        result = service.get_chunks_by_file_id("f1")

        assert result.is_ok is True
        assert result.value == chunks
        chunk_repo.get_chunks_by_file_id.assert_called_once_with("f1")

    def test_get_chunk_by_memory_id_delegates_to_chunk_repository(
        self, service: FileService, chunk_repo: MagicMock
    ) -> None:
        chunk = _a_chunk(id="c1", memory_id="mem_1")
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)

        result = service.get_chunk_by_memory_id("mem_1")

        assert result.is_ok is True
        assert result.value is chunk
        chunk_repo.get_chunk_by_memory_id.assert_called_once_with("mem_1")

    def test_get_chunks_by_memory_id_delegates_to_chunk_repository(
        self, service: FileService, chunk_repo: MagicMock
    ) -> None:
        chunks = [
            _a_chunk(id="c1", file_id="f1", memory_id="mem_1"),
            _a_chunk(id="c2", file_id="f2", memory_id="mem_1"),
        ]
        chunk_repo.get_chunks_by_memory_id.return_value = Result.ok(chunks)

        result = service.get_chunks_by_memory_id("mem_1")

        assert result.is_ok is True
        assert result.value == chunks
        chunk_repo.get_chunks_by_memory_id.assert_called_once_with("mem_1")

    def test_get_related_file_by_id_resolves_via_file_repository(
        self, service: FileService, file_repo: MagicMock
    ) -> None:
        related = _a_file(id="f2", path="/vault/notes/b.md")
        file_repo.get_file_by_id.return_value = Result.ok(related)

        result = service.get_related_file_by_id("f2")

        assert result.is_ok is True
        assert result.value is related
        file_repo.get_file_by_id.assert_called_once_with("f2")


# ===================================================================
# Structured logging — each method emits info at entry, debug for
# complex operations, with service="file_service", method="...", key
# params (file_id, memory_id, etc.)
# ===================================================================


class TestStructuredLogging:
    """FileService emits structured JSONL log entries via LoggerMock."""

    def test_update_file_logs_info_with_file_id(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """update_file emits info log with file_id at entry."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            logger=logger_mock,
        )
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        updated = _a_file(id="f1", keywords=["kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        service.update_file("bank1", "f1", {"hash": "b" * 64})

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "update_file"
        assert entry.get("file_id") == "f1"
        assert entry.get("bank") == "bank1"

    def test_delete_file_logs_info_with_file_id(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """delete_file emits info log with file_id at entry."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            logger=logger_mock,
        )
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted)

        service.delete_file("f1")

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "delete_file"
        assert entry.get("file_id") == "f1"

    def test_get_file_logs_info_with_file_id(
        self,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """get_file emits info log with file_id."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=logger_mock,
        )
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        service.get_file("f1")

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "get_file"
        assert entry.get("file_id") == "f1"

    def test_get_file_logs_debug_on_aggregate_build(
        self,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """get_file emits debug log with chunk and relation counts."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=logger_mock,
        )
        file = _a_file(id="f1")
        chunks = [_a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)]
        relations = [_a_relation(id="r1", source_file_id="f1", target_file_id="f2")]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        relation_repo.get_relations_by_file_id.return_value = Result.ok(relations)

        service.get_file("f1")

        debug_entries = [e for e in logger_mock.entries if e.get("level") == "debug"]
        assert len(debug_entries) >= 1
        entry = debug_entries[0]
        assert entry.get("method") == "get_file"
        assert entry.get("event") == "Aggregate built"
        assert entry.get("file_id") == "f1"
        assert entry.get("chunk_count") == 1
        assert entry.get("relation_count") == 1

    def test_log_entries_include_service_name(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """All log entries include service='file_service'."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            logger=logger_mock,
        )
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        updated = _a_file(id="f1", keywords=["kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        service.update_file("bank1", "f1", {"hash": "b" * 64})

        for entry in logger_mock.entries:
            assert entry.get("service") == "file_service", f"Log entry missing service='file_service': {entry}"


# ===================================================================
# Task 5 — persistence contract (spec §3.2 / §6.1 / §6.2)
# _load_aggregate + _persist chokepoint, get_by_pair convergence,
# single-event-per-fact on the service write path.
# ===================================================================


class TestLoadAggregate:
    """_load_aggregate: one repository query per requested collection."""

    def test_runs_one_query_per_requested_collection(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        chunks = [_a_chunk(id="c1", file_id="f1", memory_id="mem_1")]
        relations = [_a_relation(id="r1")]
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok(chunks)
        relation_repo.get_relations_by_file_id.return_value = Result.ok(relations)

        result = service._load_aggregate("f1", include_chunks=True, include_relations=True)

        assert result.is_ok is True
        agg = result.value
        assert isinstance(agg, FileMetadata)
        assert agg.file.id == "f1"
        assert len(agg.chunks) == 1
        assert len(agg.relations) == 1
        file_repo.get_file_by_id.assert_called_once_with("f1")
        chunk_repo.get_chunks_by_file_id.assert_called_once_with("f1")
        relation_repo.get_relations_by_file_id.assert_called_once_with("f1")

    def test_file_only_load_skips_collection_queries(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)

        result = service._load_aggregate("f1", include_chunks=False, include_relations=False)

        assert result.is_ok is True
        assert result.value.file.id == "f1"
        assert result.value.chunks == []
        assert result.value.relations == []
        chunk_repo.get_chunks_by_file_id.assert_not_called()
        relation_repo.get_relations_by_file_id.assert_not_called()

    def test_returns_ko_when_file_not_found(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service._load_aggregate("missing", include_chunks=False, include_relations=False)

        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"


class TestPersist:
    """_persist: single write chokepoint, FK-safe order, flag-mirrored writes."""

    def test_writes_file_then_chunks_then_relations_in_fk_safe_order(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        order: list[str] = []
        file = _a_file(id="f1")
        chunk = _a_chunk(id="fc_f1_mem_1", file_id="f1", memory_id="mem_1")
        relation = _a_relation(id="fr_f1_f2_sibling", source_file_id="f1", target_file_id="f2")
        file_repo.save_file.side_effect = lambda f: (order.append("file"), Result.ok(f))[1]
        chunk_repo.save_chunk.side_effect = lambda c: (order.append("chunk"), Result.ok(c))[1]
        relation_repo.save_relation.side_effect = lambda r: (order.append("relation"), Result.ok(r))[1]

        aggregate = FileMetadata(file=file, chunks=[chunk], relations=[relation])
        result = service._persist(aggregate, write_chunks=True, write_relations=True)

        assert result.is_ok is True
        assert order == ["file", "chunk", "relation"]

    def test_write_flags_false_skip_chunk_and_relation_writes(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """A file-only persist never touches chunk or relation rows."""
        file = _a_file(id="f1")
        chunk = _a_chunk(id="fc_f1_mem_1", file_id="f1", memory_id="mem_1")
        relation = _a_relation(id="fr_f1_f2_sibling", source_file_id="f1", target_file_id="f2")
        file_repo.save_file.return_value = Result.ok(file)

        aggregate = FileMetadata(file=file, chunks=[chunk], relations=[relation])
        result = service._persist(aggregate, write_chunks=False, write_relations=False)

        assert result.is_ok is True
        file_repo.save_file.assert_called_once()
        chunk_repo.save_chunk.assert_not_called()
        chunk_repo.delete_chunk.assert_not_called()
        chunk_repo.delete_chunks_by_file_id.assert_not_called()
        relation_repo.save_relation.assert_not_called()
        relation_repo.delete_relation.assert_not_called()
        relation_repo.delete_relations_by_file_id.assert_not_called()

    def test_deleted_file_with_write_relations_prunes_relation_rows(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """DELETED file + write_relations=True → prune this file's relation rows."""
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        relation_repo.delete_relations_by_file_id.return_value = Result.ok(True)
        file_repo.save_file.return_value = Result.ok(deleted)

        aggregate = FileMetadata(file=deleted, chunks=[], relations=[])
        result = service._persist(aggregate, write_chunks=False, write_relations=True)

        assert result.is_ok is True
        relation_repo.delete_relations_by_file_id.assert_called_once_with("f1")
        relation_repo.save_relation.assert_not_called()

    def test_deleted_file_prune_failure_propagates(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted)
        relation_repo.delete_relations_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("RELATION_DELETE_BY_FILE_ID_ERROR", {"error": "boom"})]
        )

        aggregate = FileMetadata(file=deleted, chunks=[], relations=[])
        result = service._persist(aggregate, write_chunks=False, write_relations=True)

        assert result.is_ko is True
        assert result.errors[0].error_code == "RELATION_DELETE_BY_FILE_ID_ERROR"

    def test_non_deleted_file_does_not_delete_relations(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Non-DELETED persist: the keep-set prune covers every loaded chunk
        (nothing dropped), no relation row is deleted, rows are re-saved in place."""
        file = _a_file(id="f1")
        chunk = _a_chunk(id="fc_f1_mem_1", file_id="f1", memory_id="mem_1")
        relation = _a_relation(id="fr_f1_f2_sibling", source_file_id="f1", target_file_id="f2")
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.save_chunk.return_value = Result.ok(chunk)
        relation_repo.save_relation.return_value = Result.ok(relation)

        aggregate = FileMetadata(file=file, chunks=[chunk], relations=[relation])
        result = service._persist(aggregate, write_chunks=True, write_relations=True)

        assert result.is_ok is True
        chunk_repo.delete_chunk.assert_not_called()
        # Keep-set prune: all loaded chunks kept → no chunk row dropped.
        chunk_repo.delete_chunks_by_file_id.assert_called_once_with("f1", {"mem_1"})
        relation_repo.delete_relation.assert_not_called()
        relation_repo.delete_relations_by_file_id.assert_not_called()
        chunk_repo.save_chunk.assert_called_once()
        relation_repo.save_relation.assert_called_once()

    def test_deleted_persist_cascade_prunes_both_sides_and_saves_tombstone(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """D20: a DELETED persist prunes chunk rows AND relation rows (both
        sides) and then saves the tombstone — status-driven, independent of the
        write flags (all-false here proves the flags do not gate the cascade)."""
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted)
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        relation_repo.delete_relations_by_file_id.return_value = Result.ok(True)

        aggregate = FileMetadata(file=deleted, chunks=[], relations=[])
        result = service._persist(aggregate, write_chunks=False, write_relations=False)

        assert result.is_ok is True
        # Chunk rows pruned with an empty keep-set (delete everything).
        chunk_repo.delete_chunks_by_file_id.assert_called_once_with("f1", set())
        # Relation rows pruned (covers source OR target in the repository).
        relation_repo.delete_relations_by_file_id.assert_called_once_with("f1")
        # Tombstone saved; no child row is re-saved.
        file_repo.save_file.assert_called_once_with(deleted)
        chunk_repo.save_chunk.assert_not_called()
        relation_repo.save_relation.assert_not_called()

    def test_deleted_persist_cascade_order_prune_before_tombstone(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """D20 order: child rows are pruned BEFORE the tombstone is saved."""
        order: list[str] = []
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.side_effect = lambda f: (order.append("file_save"), Result.ok(f))[1]
        chunk_repo.delete_chunks_by_file_id.side_effect = (
            lambda fid, keep: (order.append("chunk_prune"), Result.ok(True))[1]
        )
        relation_repo.delete_relations_by_file_id.side_effect = (
            lambda fid: (order.append("relation_prune"), Result.ok(True))[1]
        )

        aggregate = FileMetadata(file=deleted, chunks=[], relations=[])
        result = service._persist(aggregate, write_chunks=False, write_relations=True)

        assert result.is_ok is True
        assert order == ["chunk_prune", "relation_prune", "file_save"]

    def test_persist_file_save_failure_propagates_without_writing_children(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        chunk = _a_chunk(id="fc_f1_mem_1", file_id="f1", memory_id="mem_1")
        file_repo.save_file.return_value = Result.ko([ErrorWithDetails("FILE_SAVE_ERROR", {"error": "boom"})])

        aggregate = FileMetadata(file=file, chunks=[chunk], relations=[])
        result = service._persist(aggregate, write_chunks=True, write_relations=False)

        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_SAVE_ERROR"
        chunk_repo.save_chunk.assert_not_called()
        relation_repo.save_relation.assert_not_called()


class TestPersistConvergence:
    """Legacy relation ids converge to fr_{source}_{target}_{type} at persist time."""

    def test_legacy_id_row_converges_to_canonical_id(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """A stored legacy fr_{s}_{t} row is deleted and re-saved under the canonical id."""
        file = _a_file(id="f1")
        legacy = _a_relation(id="fr_f1_f2", source_file_id="f1", target_file_id="f2")
        # Loaded from the DB: the legacy row sits in the aggregate.
        aggregate = FileMetadata(file=file, chunks=[], relations=[legacy])
        file_repo.save_file.return_value = Result.ok(file)
        relation_repo.get_by_pair.return_value = Result.ok(legacy)
        relation_repo.delete_relation.return_value = Result.ok(True)
        relation_repo.save_relation.return_value = Result.ok(
            _a_relation(id="fr_f1_f2_sibling", source_file_id="f1", target_file_id="f2")
        )

        result = service._persist(aggregate, write_chunks=False, write_relations=True)

        assert result.is_ok is True
        relation_repo.delete_relation.assert_called_once_with("fr_f1_f2")
        saved = relation_repo.save_relation.call_args[0][0]
        assert saved.id == "fr_f1_f2_sibling"

    def test_canonical_id_row_saves_without_convergence_query(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """A relation already under its canonical id saves directly."""
        file = _a_file(id="f1")
        relation = _a_relation(id="fr_f1_f2_sibling", source_file_id="f1", target_file_id="f2")
        aggregate = FileMetadata(file=file, chunks=[], relations=[relation])
        file_repo.save_file.return_value = Result.ok(file)
        relation_repo.save_relation.return_value = Result.ok(relation)

        result = service._persist(aggregate, write_chunks=False, write_relations=True)

        assert result.is_ok is True
        relation_repo.get_by_pair.assert_not_called()
        relation_repo.delete_relation.assert_not_called()
        saved = relation_repo.save_relation.call_args[0][0]
        assert saved.id == "fr_f1_f2_sibling"


class TestServicePathContract:
    """Write methods route through _load_aggregate + _persist with flag-mirrored writes."""

    def test_update_file_does_not_touch_chunk_or_relation_rows(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """File-only flow: no collection queries, no child row writes."""
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        file_repo.save_file.return_value = Result.ok(file)

        result = service.update_file("bank1", "f1", {"hash": "b" * 64})

        assert result.is_ok is True
        chunk_repo.get_chunks_by_file_id.assert_not_called()
        relation_repo.get_relations_by_file_id.assert_not_called()
        chunk_repo.save_chunk.assert_not_called()
        chunk_repo.delete_chunks_by_file_id.assert_not_called()
        relation_repo.save_relation.assert_not_called()
        relation_repo.delete_relations_by_file_id.assert_not_called()

    def test_delete_file_does_not_load_chunks_or_relations(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """File-only flow: the DELETED cascade prunes chunk + relation rows by
        file_id (both sides) without loading the collections (D20)."""
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.save_file.return_value = Result.ok(deleted)
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        relation_repo.delete_relations_by_file_id.return_value = Result.ok(True)

        result = service.delete_file("f1")

        assert result.is_ok is True
        chunk_repo.get_chunks_by_file_id.assert_not_called()
        relation_repo.get_relations_by_file_id.assert_not_called()
        # Cascade prunes both child-row families by file_id before the tombstone.
        chunk_repo.delete_chunks_by_file_id.assert_called_once_with("f1", set())
        relation_repo.delete_relations_by_file_id.assert_called_once_with("f1")
        chunk_repo.save_chunk.assert_not_called()
        relation_repo.save_relation.assert_not_called()

    def test_remove_chunk_prunes_removed_chunk_row_via_keep_set(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """remove_chunk re-persists remaining chunks and prunes the removed row by keep-set."""
        file = _a_file(id="f1")
        chunk_a = _a_chunk(id="fc_f1_mem_a", file_id="f1", memory_id="mem_a", chunk_index=0)
        chunk_b = _a_chunk(id="fc_f1_mem_b", file_id="f1", memory_id="mem_b", chunk_index=1)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([chunk_a, chunk_b])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        chunk_repo.save_chunk.return_value = Result.ok(chunk_b)

        result = service.remove_chunk("f1", "mem_a")

        assert result.is_ok is True
        chunk_repo.delete_chunks_by_file_id.assert_called_once_with("f1", {"mem_b"})
        # The surviving chunk is re-persisted so its row survives the prune.
        chunk_repo.save_chunk.assert_called_once_with(chunk_b)
