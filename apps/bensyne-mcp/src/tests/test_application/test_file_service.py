"""Unit tests for FileService application service.

FileService orchestrates file operations using the FileMetadataAggregate
and repository pattern. It emits domain events on state changes and uses
the Result pattern for error handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from src.domain.file_metadata_aggregate import FileMetadataAggregate
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk, ContentType
from src.domain.file_relation_entity import FileRelation, RelationType, Direction
from src.domain.events.file_events import (
    FileChunkAddedEvent,
    FileChunkRemovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileRelationCreatedEvent,
    FileUpdatedEvent,
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
    source_type: SourceType = SourceType.AGENT_SESSION,
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
    return MagicMock()


@pytest.fixture
def relation_repo() -> MagicMock:
    repo = MagicMock()
    # Default stub for the forget-symmetry cleanup call (delete_file path).
    repo.delete_relations_by_file_id.return_value = Result.ok(True)
    return repo


@pytest.fixture
def memory_repo() -> MagicMock:
    return MagicMock()


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
    memory_repo: MagicMock,
    logger_mock: LoggerMock,
) -> FileService:
    return FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        memory_client=memory_repo,
        logger=logger_mock,
    )


# ===================================================================
# create_file
# ===================================================================


class TestCreateFile:
    """create_file creates a new file via File.of() and saves via repository."""

    def test_returns_created_file(self, service: FileService, file_repo: MagicMock) -> None:
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        expected_file = _a_file(id="f1", path="/tmp/test.txt", source_type=SourceType.FILE_SYSTEM)
        file_repo.save_file.return_value = Result.ok(expected_file)

        result = service.create_file(file_data)

        assert result.is_ok is True
        assert result.value.id == "f1"
        assert result.value.path == "/tmp/test.txt"
        file_repo.save_file.assert_called_once()

    def test_returns_created_file_with_events(self, service: FileService, file_repo: MagicMock) -> None:
        """File.of emits FileCreatedEvent; service should propagate it."""
        file_data = {
            "id": "f1",
            "path": "/tmp/new.txt",
            "source_type": SourceType.AGENT_SESSION,
            "hash": VALID_HASH,
        }
        created_file = _a_file(id="f1", path="/tmp/new.txt")
        file_repo.save_file.return_value = Result.ok(created_file)

        result = service.create_file(file_data)

        assert result.is_ok is True
        # File.of() emits FileCreatedEvent, which should be in the Result events
        assert result.has_events() is True
        assert any(isinstance(e, FileCreatedEvent) for e in result.get_events())

    def test_returns_ko_when_file_of_fails(self, service: FileService, file_repo: MagicMock) -> None:
        """If File.of validation fails, return ko without calling repository."""
        file_data = {
            "id": "",  # empty id should fail validation
            "path": "",
            "source_type": SourceType.AGENT_SESSION,
        }

        result = service.create_file(file_data)

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_returns_ko_when_repo_save_fails(self, service: FileService, file_repo: MagicMock) -> None:
        """If repository save fails, propagate the error."""
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        file_repo.save_file.return_value = Result.ko([ErrorWithDetails("DB_ERROR", {})])

        result = service.create_file(file_data)

        assert result.is_ko is True
        assert result.errors[0].error_code == "DB_ERROR"


# ===================================================================
# update_file
# ===================================================================


class TestUpdateFile:
    """update_file finds existing file and updates its metadata."""

    def test_returns_updated_file(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1", path="/tmp/old.txt")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        updated = _a_file(id="f1", path="/tmp/old.txt", keywords=["new_kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        result = service.update_file("f1", hash="b" * 64)

        assert result.is_ok is True
        file_repo.save_file.assert_called_once()

    def test_returns_ko_when_file_not_found(self, service: FileService, file_repo: MagicMock) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.update_file("nonexistent", hash="b" * 64)

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_returns_ko_when_file_is_deleted(self, service: FileService, file_repo: MagicMock) -> None:
        deleted = _a_file(id="f1", status=FileStatus.DELETED)
        file_repo.get_file_by_id.return_value = Result.ok(deleted)

        result = service.update_file("f1", hash="b" * 64)

        assert result.is_ko is True
        file_repo.save_file.assert_not_called()

    def test_emits_file_updated_event(self, service: FileService, file_repo: MagicMock) -> None:
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        updated = _a_file(id="f1", keywords=["kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        result = service.update_file("f1", hash="b" * 64)

        assert result.is_ok is True
        # update_metadata emits FileUpdatedEvent
        assert result.has_events() is True


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
# link_chunk
# ===================================================================


class TestCreateChunk:
    """link_chunk uses the aggregate to add a chunk, then persists."""

    def test_returns_created_chunk(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])

        saved_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.save_chunk.return_value = Result.ok(saved_chunk)

        result = service.link_chunk(
            file_id="f1",
            memory_id="mem_1",
            chunk_index=0,
        )

        assert result.is_ok is True
        assert result.value.memory_id == "mem_1"
        chunk_repo.save_chunk.assert_called_once()

    def test_returns_ko_when_file_not_found(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.link_chunk(file_id="nonexistent", memory_id="mem_1", chunk_index=0)

        assert result.is_ko is True

    def test_emits_chunk_added_event(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])

        saved_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.save_chunk.return_value = Result.ok(saved_chunk)

        result = service.link_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        assert result.is_ok is True
        assert result.has_events() is True
        assert any(isinstance(e, FileChunkAddedEvent) for e in result.get_events())

    def test_rejects_duplicate_memory_id(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """If a chunk with same memory_id already exists, aggregate rejects it."""
        file = _a_file(id="f1")
        existing_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([existing_chunk])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])

        result = service.link_chunk(file_id="f1", memory_id="mem_1", chunk_index=1)

        assert result.is_ko is True
        assert result.errors[0].error_code == "CHUNK_ALREADY_EXISTS"

    def test_updates_file_metadata_via_aggregate(
        self,
        service: FileService,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
    ) -> None:
        """After adding chunk, file metadata should be updated and saved."""
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])

        saved_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        chunk_repo.save_chunk.return_value = Result.ok(saved_chunk)
        file_repo.save_file.return_value = Result.ok(file)

        result = service.link_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        assert result.is_ok is True
        # File should be saved after aggregate updates it
        file_repo.save_file.assert_called_once()


# ===================================================================
# create_relation
# ===================================================================


class TestCreateRelation:
    """create_relation uses the aggregate to add a relation, then persists."""

    def test_returns_created_relation(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        service.chunk_repository.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        saved_relation = _a_relation(id="r1", source_file_id="f1", target_file_id="f2")
        relation_repo.save_relation.return_value = Result.ok(saved_relation)

        result = service.create_relation(
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )

        assert result.is_ok is True
        assert result.value.source_file_id == "f1"
        assert result.value.target_file_id == "f2"
        relation_repo.save_relation.assert_called_once()

    def test_returns_ko_when_source_file_not_found(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_id.return_value = Result.ok(None)

        result = service.create_relation(
            source_file_id="nonexistent",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )

        assert result.is_ko is True

    def test_emits_relation_created_event(
        self,
        service: FileService,
        file_repo: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        service.chunk_repository.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        saved_relation = _a_relation(id="r1", source_file_id="f1", target_file_id="f2")
        relation_repo.save_relation.return_value = Result.ok(saved_relation)

        result = service.create_relation(
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )

        assert result.is_ok is True
        assert result.has_events() is True
        assert any(isinstance(e, FileRelationCreatedEvent) for e in result.get_events())


# ===================================================================
# get_file (unified)
# ===================================================================


class TestGetFile:
    """get_file returns a FileMetadataAggregate with configurable chunks and relations."""

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
        assert isinstance(agg, FileMetadataAggregate)
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
# upsert_file
# ===================================================================


class TestUpsertFile:
    """upsert_file creates new or updates existing file by path."""

    def test_creates_new_file_when_not_exists(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        file_repo.get_file_by_path.return_value = Result.ok(None)
        created = _a_file(id="f1", path="/tmp/new.txt")
        file_repo.save_file.return_value = Result.ok(created)

        file_data = {
            "id": "f1",
            "path": "/tmp/new.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }

        result = service.upsert_file(file_data)

        assert result.is_ok is True
        assert result.value.id == "f1"
        file_repo.save_file.assert_called_once()

    def test_updates_existing_file(
        self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        existing = _a_file(id="f1", path="/tmp/existing.txt")
        file_repo.get_file_by_path.return_value = Result.ok(existing)

        updated = _a_file(id="f1", path="/tmp/existing.txt", keywords=["new_kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        file_data = {
            "id": "f1",
            "path": "/tmp/existing.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
            "aggregated_keywords": ["new_kw"],
        }

        result = service.upsert_file(file_data)

        assert result.is_ok is True
        file_repo.save_file.assert_called_once()


# ===================================================================
# find_files_by_memory
# ===================================================================


class TestFindFilesByMemory:
    """find_files_by_memory finds files associated with a memory."""

    def test_returns_files_for_memory(
        self,
        service: FileService,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
    ) -> None:
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        file = _a_file(id="f1")

        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)

        result = service.find_files_by_memory("mem_1")

        assert result.is_ok is True
        files = result.value
        assert len(files) == 1
        assert files[0].id == "f1"

    def test_returns_empty_when_no_chunk_for_memory(
        self,
        service: FileService,
        chunk_repo: MagicMock,
    ) -> None:
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(None)

        result = service.find_files_by_memory("orphan_mem")

        assert result.is_ok is True
        assert result.value == []


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

    def test_create_file_logs_info_at_entry(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """create_file emits an info log with file_id at entry."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        created = _a_file(id="f1", path="/tmp/test.txt", source_type=SourceType.FILE_SYSTEM)
        file_repo.save_file.return_value = Result.ok(created)

        service.create_file(file_data)

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("service") == "file_service"
        assert entry.get("method") == "create_file"
        assert entry.get("event") == "Creating file"
        assert entry.get("file_id") == "f1"

    def test_create_file_logs_debug_on_save(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """create_file emits a debug log after save."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        created = _a_file(id="f1", path="/tmp/test.txt", source_type=SourceType.FILE_SYSTEM)
        file_repo.save_file.return_value = Result.ok(created)

        service.create_file(file_data)

        debug_entries = [e for e in logger_mock.entries if e.get("level") == "debug"]
        assert len(debug_entries) >= 1
        entry = debug_entries[0]
        assert entry.get("method") == "create_file"
        assert entry.get("event") == "File saved to repository"
        assert entry.get("file_id") == "f1"

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
            memory_client=None,
            logger=logger_mock,
        )
        existing = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(existing)
        updated = _a_file(id="f1", keywords=["kw"])
        file_repo.save_file.return_value = Result.ok(updated)

        service.update_file("f1", hash="b" * 64)

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "update_file"
        assert entry.get("file_id") == "f1"

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
            memory_client=None,
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

    def test_link_chunk_logs_info_with_file_id_and_memory_id(
        self,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """link_chunk emits info log with file_id and memory_id."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])
        saved_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.save_chunk.return_value = Result.ok(saved_chunk)

        service.link_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "link_chunk"
        assert entry.get("file_id") == "f1"
        assert entry.get("memory_id") == "mem_1"

    def test_link_chunk_logs_debug_on_aggregate_load(
        self,
        file_repo: MagicMock,
        chunk_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """link_chunk emits debug log when loading aggregate."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        chunk_repo.get_chunks_by_file_id.return_value = Result.ok([])
        service.relation_repository.get_relations_by_file_id.return_value = Result.ok([])
        saved_chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        file_repo.save_file.return_value = Result.ok(file)
        chunk_repo.save_chunk.return_value = Result.ok(saved_chunk)

        service.link_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        debug_entries = [e for e in logger_mock.entries if e.get("level") == "debug"]
        assert len(debug_entries) >= 2, f"Expected at least 2 debug entries, got {len(debug_entries)}"
        # Find the "Aggregate loaded" entry (from _with_aggregate)
        loaded_entries = [e for e in debug_entries if e.get("event") == "Aggregate loaded"]
        assert len(loaded_entries) >= 1
        entry = loaded_entries[0]
        assert entry.get("method") == "link_chunk"
        assert entry.get("file_id") == "f1"

    def test_create_relation_logs_info_with_source_and_target(
        self,
        file_repo: MagicMock,
        relation_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """create_relation emits info log with source and target file_ids."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=relation_repo,
            memory_client=None,
            logger=logger_mock,
        )
        file = _a_file(id="f1")
        file_repo.get_file_by_id.return_value = Result.ok(file)
        service.chunk_repository.get_chunks_by_file_id.return_value = Result.ok([])
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])
        saved_relation = _a_relation(id="r1", source_file_id="f1", target_file_id="f2")
        relation_repo.save_relation.return_value = Result.ok(saved_relation)

        service.create_relation(
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "create_relation"
        assert entry.get("source_file_id") == "f1"
        assert entry.get("target_file_id") == "f2"

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
            memory_client=None,
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
            memory_client=None,
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

    def test_upsert_file_logs_info_with_file_id(
        self,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """upsert_file emits info log with file_id."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=MagicMock(),
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        file_repo.get_file_by_path.return_value = Result.ok(None)
        created = _a_file(id="f1", path="/tmp/new.txt")
        file_repo.save_file.return_value = Result.ok(created)

        file_data = {
            "id": "f1",
            "path": "/tmp/new.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        service.upsert_file(file_data)

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "upsert_file"
        assert entry.get("file_id") == "f1"

    def test_find_files_by_memory_logs_info_with_memory_id(
        self,
        chunk_repo: MagicMock,
        file_repo: MagicMock,
        logger_mock: LoggerMock,
    ) -> None:
        """find_files_by_memory emits info log with memory_id."""
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=MagicMock(),
            memory_client=None,
            logger=logger_mock,
        )
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        file = _a_file(id="f1")
        chunk_repo.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_repo.get_file_by_id.return_value = Result.ok(file)

        service.find_files_by_memory("mem_1")

        info_entries = [e for e in logger_mock.entries if e.get("level") == "info"]
        assert len(info_entries) >= 1
        entry = info_entries[0]
        assert entry.get("method") == "find_files_by_memory"
        assert entry.get("memory_id") == "mem_1"

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
            memory_client=None,
            logger=logger_mock,
        )
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        created = _a_file(id="f1", path="/tmp/test.txt", source_type=SourceType.FILE_SYSTEM)
        file_repo.save_file.return_value = Result.ok(created)

        service.create_file(file_data)

        for entry in logger_mock.entries:
            assert entry.get("service") == "file_service", f"Log entry missing service='file_service': {entry}"
