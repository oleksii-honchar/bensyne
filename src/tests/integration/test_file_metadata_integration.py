"""Integration tests for the File Metadata Layer.

Verifies end-to-end flows using real SQLite repositories and FileService
with a temporary on-disk SQLite database (not in-memory, since
FileMetadataConnectionManager requires a bank_dir path).

Tests cover:
- File creation with chunks and relations
- File content reconstruction
- File search with metadata enrichment
- Relation expansion
- Error cases: missing file, missing chunk, invalid relation
- Domain event emission through the full stack
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator, List
from unittest.mock import MagicMock

import pytest

from src.application.services.file_service import FileService
from src.domain.file_metadata_aggregate import FileMetadataAggregate
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation, RelationType
from src.domain.events.file_events import (
    FileChunkAddedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileRelationCreatedEvent,
    FileUpdatedEvent,
)
from src.utils.result import Result
from src.infrastructure.storage.sqlite.file_chunk_repository import (
    FileChunkRepository,
)
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import (
    FileRelationRepository,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.structured_logging import LoggerMock

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_HASH = "a" * 64
NOW = datetime(2026, 1, 1, 0, 0, 0)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bank_dir(tmp_path: Path) -> Path:
    """Temporary directory simulating a memory bank's data dir."""
    return tmp_path / "test_bank"


@pytest.fixture
def conn_manager(bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Create a FileMetadataConnectionManager with a temporary database."""
    mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
    yield mgr
    mgr.close()


@pytest.fixture
def file_repo(conn_manager: FileMetadataConnectionManager) -> FileRepository:
    """SQLite-backed FileRepository."""
    return FileRepository(conn_manager)


@pytest.fixture
def chunk_repo(conn_manager: FileMetadataConnectionManager) -> FileChunkRepository:
    """SQLite-backed FileChunkRepository."""
    return FileChunkRepository(conn_manager)


@pytest.fixture
def relation_repo(conn_manager: FileMetadataConnectionManager) -> FileRelationRepository:
    """SQLite-backed FileRelationRepository."""
    return FileRelationRepository(conn_manager)


@pytest.fixture
def service(
    file_repo: FileRepository,
    chunk_repo: FileChunkRepository,
    relation_repo: FileRelationRepository,
) -> FileService:
    """FileService wired with real SQLite repositories (no memory_client)."""
    return FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=LoggerMock(),
        memory_client=None,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_data(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    hash: str = VALID_HASH,
    file_type: str | None = None,
    size: int | None = None,
    language: str | None = None,
    keywords: List[str] | None = None,
    tags: List[str] | None = None,
    status: FileStatus = FileStatus.PENDING,
) -> dict:
    """Build a dict suitable for File.of() / service.create_file()."""
    return {
        "id": id,
        "path": path,
        "source_type": source_type,
        "hash": hash,
        "file_type": file_type,
        "size": size,
        "language": language,
        "aggregated_keywords": keywords or [],
        "aggregated_tags": tags or [],
        "status": status,
        "created_at": NOW,
    }

# ===================================================================
# Test 1: File creation with chunks and relations
# ===================================================================

class TestFileCreationWithChunksAndRelations:
    """Integration: create file, add chunks, add relations — full flow."""

    def test_create_file_persists_and_retrievable(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """File created via service is persisted and retrievable from DB."""
        data = _file_data(id="f1", path="/tmp/integration_test.py", language="python")
        result = service.create_file(data)

        assert result.is_ok is True
        assert result.value.id == "f1"
        assert result.value.path == "/tmp/integration_test.py"

        # Verify persistence via repository
        db_result = file_repo.get_file_by_id("f1")
        assert db_result.is_ok is True
        assert db_result.value is not None
        assert db_result.value.path == "/tmp/integration_test.py"

    def test_create_file_emits_file_created_event(
        self,
        service: FileService,
    ) -> None:
        """create_file propagates FileCreatedEvent through the Result."""
        data = _file_data(id="f10", path="/tmp/event_test.txt")
        result = service.create_file(data)

        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert any(isinstance(e, FileCreatedEvent) for e in events)

    def test_create_file_then_add_chunk(
        self,
        service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
    ) -> None:
        """Create file, then add chunk — chunk persisted and linked to file."""
        # Create file
        data = _file_data(id="f11", path="/tmp/chunk_test.py")
        create_result = service.create_file(data)
        assert create_result.is_ok is True

        # Add chunk
        chunk_result = service.link_chunk(
            file_id="f11",
            memory_id="mem_alpha",
            chunk_index=0,
            start_line=1,
            end_line=50,
        )
        assert chunk_result.is_ok is True
        assert chunk_result.value.memory_id == "mem_alpha"
        assert chunk_result.value.chunk_index == 0

        # Verify chunk persisted
        db_chunk = chunk_repo.get_chunk_by_id(f"fc_f11_mem_alpha")
        assert db_chunk.is_ok is True
        assert db_chunk.value is not None
        assert db_chunk.value.file_id == "f11"
        assert db_chunk.value.memory_id == "mem_alpha"

    def test_create_file_add_multiple_chunks(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
    ) -> None:
        """Create file with multiple ordered chunks — all survive via service."""
        data = _file_data(id="f12", path="/tmp/multi_chunk.py")
        service.create_file(data)

        # Add chunks via the service
        service.link_chunk("f12", "mem_c1", chunk_index=0, start_line=1, end_line=30)
        service.link_chunk("f12", "mem_c2", chunk_index=1, start_line=31, end_line=60)
        service.link_chunk("f12", "mem_c3", chunk_index=2, start_line=61, end_line=90)

        # All three chunks survive — save_file uses INSERT ... ON CONFLICT(id)
        # DO UPDATE SET, which does NOT trigger ON DELETE CASCADE on file_chunks.
        chunks_result = chunk_repo.get_chunks_by_file_id("f12")
        assert chunks_result.is_ok is True
        assert len(chunks_result.value) == 3

        # Verify ordering
        indices = [c.chunk_index for c in chunks_result.value]
        assert indices == [0, 1, 2]

        # Verify each chunk's data
        assert chunks_result.value[0].memory_id == "mem_c1"
        assert chunks_result.value[0].start_line == 1
        assert chunks_result.value[0].end_line == 30
        assert chunks_result.value[1].memory_id == "mem_c2"
        assert chunks_result.value[1].start_line == 31
        assert chunks_result.value[1].end_line == 60
        assert chunks_result.value[2].memory_id == "mem_c3"
        assert chunks_result.value[2].start_line == 61
        assert chunks_result.value[2].end_line == 90

    def test_add_chunk_emits_chunk_added_event(
        self,
        service: FileService,
    ) -> None:
        """Adding a chunk emits FileChunkAddedEvent."""
        data = _file_data(id="f13", path="/tmp/event_chunk.py")
        service.create_file(data)

        chunk_result = service.link_chunk("f13", "mem_ev", chunk_index=0)
        assert chunk_result.is_ok is True
        assert chunk_result.has_events() is True
        events = chunk_result.get_events()
        assert any(isinstance(e, FileChunkAddedEvent) for e in events)

    def test_add_chunk_rejects_duplicate_memory_id(
        self,
        service: FileService,
    ) -> None:
        """Adding a chunk with same memory_id is rejected by aggregate invariant."""
        data = _file_data(id="f14", path="/tmp/dup_chunk.py")
        service.create_file(data)

        service.link_chunk("f14", "mem_dup", chunk_index=0)
        dup_result = service.link_chunk("f14", "mem_dup", chunk_index=1)

        assert dup_result.is_ko is True
        assert dup_result.errors[0].error_code == "CHUNK_ALREADY_EXISTS"

    def test_create_file_then_add_relation(
        self,
        service: FileService,
        relation_repo: FileRelationRepository,
    ) -> None:
        """Create two files, then create a relation between them."""
        service.create_file(_file_data(id="f20", path="/tmp/parent.py"))
        service.create_file(_file_data(id="f21", path="/tmp/child.py"))

        rel_result = service.create_relation(
            source_file_id="f20",
            target_file_id="f21",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.9,
            description="Parent-child relationship",
        )
        assert rel_result.is_ok is True
        assert rel_result.value.source_file_id == "f20"
        assert rel_result.value.target_file_id == "f21"
        assert rel_result.value.relation_type == RelationType.PARENT_CHILD
        assert rel_result.value.strength == 0.9

        # Verify relation persisted
        db_rel = relation_repo.get_relation_by_id("fr_f20_f21")
        assert db_rel.is_ok is True
        assert db_rel.value is not None
        assert db_rel.value.relation_type == RelationType.PARENT_CHILD

    def test_add_relation_emits_relation_created_event(
        self,
        service: FileService,
    ) -> None:
        """Adding a relation emits FileRelationCreatedEvent."""
        service.create_file(_file_data(id="f22", path="/tmp/rel_src.py"))
        service.create_file(_file_data(id="f23", path="/tmp/rel_tgt.py"))

        rel_result = service.create_relation(
            source_file_id="f22",
            target_file_id="f23",
            relation_type=RelationType.SIBLING,
        )
        assert rel_result.is_ok is True
        assert rel_result.has_events() is True
        events = rel_result.get_events()
        assert any(isinstance(e, FileRelationCreatedEvent) for e in events)

    def test_add_relation_rejects_missing_source_file(
        self,
        service: FileService,
    ) -> None:
        """Relation creation fails when source file doesn't exist."""
        service.create_file(_file_data(id="f24", path="/tmp/exists.py"))

        rel_result = service.create_relation(
            source_file_id="nonexistent",
            target_file_id="f24",
            relation_type=RelationType.SIBLING,
        )
        assert rel_result.is_ko is True

    def test_full_lifecycle_create_chunks_and_relations(
        self,
        service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        """End-to-end: create files, add chunks, add relations, verify all persisted."""
        # Create files
        service.create_file(_file_data(id="f100", path="/tmp/full_a.py", keywords=["domain", "entity"]))
        service.create_file(_file_data(id="f101", path="/tmp/full_b.py", keywords=["infra", "repo"]))

        # Add chunks via repository directly to avoid INSERT OR REPLACE cascade
        from src.domain.file_chunk_entity import FileChunk
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f100_mem_a1",
                "file_id": "f100",
                "memory_id": "mem_a1",
                "chunk_index": 0,
                "start_line": 1,
                "end_line": 100,
            }).value
        )
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f100_mem_a2",
                "file_id": "f100",
                "memory_id": "mem_a2",
                "chunk_index": 1,
                "start_line": 101,
                "end_line": 200,
            }).value
        )
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f101_mem_b1",
                "file_id": "f101",
                "memory_id": "mem_b1",
                "chunk_index": 0,
                "start_line": 1,
                "end_line": 50,
            }).value
        )

        # Add relation
        service.create_relation(
            source_file_id="f100",
            target_file_id="f101",
            relation_type=RelationType.CROSS_REFERENCE,
            strength=0.7,
        )

        # Verify file
        file_result = file_repo.get_file_by_id("f100")
        assert file_result.is_ok is True
        assert file_result.value is not None
        assert file_result.value.aggregated_keywords == ["domain", "entity"]

        # Verify chunks
        chunks_result = chunk_repo.get_chunks_by_file_id("f100")
        assert chunks_result.is_ok is True
        assert len(chunks_result.value) == 2

        # Verify relation
        rels_result = relation_repo.get_relations_by_file_id("f100")
        assert rels_result.is_ok is True
        assert len(rels_result.value) == 1
        assert rels_result.value[0].relation_type == RelationType.CROSS_REFERENCE

# ===================================================================
# Test 3: File search with metadata enrichment
# ===================================================================

class TestFileSearchWithMetadataEnrichment:
    """Integration: search files and verify metadata is enriched from DB."""

    def test_search_by_path(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Search finds file by path content."""
        service.create_file(_file_data(id="f300", path="/tmp/searchable_file.py"))
        service.create_file(_file_data(id="f301", path="/tmp/other.txt"))

        result = file_repo.search_files_by_query("searchable")
        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].id == "f300"

    def test_search_by_keywords(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Search finds file by aggregated keywords."""
        service.create_file(_file_data(id="f302", path="/tmp/x.py", keywords=["architecture", "patterns"]))
        service.create_file(_file_data(id="f303", path="/tmp/y.py", keywords=["utils"]))

        result = file_repo.search_files_by_query("patterns")
        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].id == "f302"

    def test_search_by_tags(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Search finds file by aggregated tags."""
        service.create_file(_file_data(id="f304", path="/tmp/a.py", tags=["core", "critical"]))
        service.create_file(_file_data(id="f305", path="/tmp/b.py", tags=["util"]))

        result = file_repo.search_files_by_query("critical")
        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].id == "f304"

    def test_search_returns_empty_for_no_matches(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Search returns empty list when no files match."""
        service.create_file(_file_data(id="f306", path="/tmp/no_match.py"))

        result = file_repo.search_files_by_query("nonexistent")
        assert result.is_ok is True
        assert len(result.value) == 0

    def test_search_with_metadata_enrichment(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Search returns files with full metadata (type, size, language, etc.)."""
        service.create_file(_file_data(
            id="f307",
            path="/tmp/enriched.py",
            file_type="python",
            size=4096,
            language="python",
            keywords=["domain"],
            tags=["core"],
        ))

        result = file_repo.search_files_by_query("enriched")
        assert result.is_ok is True
        assert len(result.value) == 1
        f = result.value[0]
        assert f.id == "f307"
        assert f.file_type == "python"
        assert f.size == 4096
        assert f.language == "python"
        assert f.aggregated_keywords == ["domain"]
        assert f.aggregated_tags == ["core"]

    def test_get_file_with_chunks_aggregate(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
    ) -> None:
        """get_file returns aggregate with file, chunks, and relations."""
        service.create_file(_file_data(id="f308", path="/tmp/agg.py"))

        # Add chunks directly to avoid INSERT OR REPLACE cascade
        from src.domain.file_chunk_entity import FileChunk
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f308_mem_agg1",
                "file_id": "f308",
                "memory_id": "mem_agg1",
                "chunk_index": 0,
            }).value
        )
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f308_mem_agg2",
                "file_id": "f308",
                "memory_id": "mem_agg2",
                "chunk_index": 1,
            }).value
        )

        result = service.get_file("f308")

        assert result.is_ok is True
        agg = result.value
        assert isinstance(agg, FileMetadataAggregate)
        assert agg.file.id == "f308"
        assert len(agg.chunks) == 2
        assert agg.chunks[0].chunk_index == 0
        assert agg.chunks[1].chunk_index == 1

    def test_get_file_not_found(
        self,
        service: FileService,
    ) -> None:
        """get_file returns ko for nonexistent file."""
        result = service.get_file("nonexistent")
        assert result.is_ko is True

# ===================================================================
# Test 4: Relation expansion
# ===================================================================

class TestRelationExpansion:
    """Integration: expand file relations and verify connected files."""

    def test_get_file_with_relations(
        self,
        service: FileService,
    ) -> None:
        """get_file returns aggregate with relations."""
        service.create_file(_file_data(id="f400", path="/tmp/rel_src.py"))
        service.create_file(_file_data(id="f401", path="/tmp/rel_tgt.py"))
        service.create_relation(
            source_file_id="f400",
            target_file_id="f401",
            relation_type=RelationType.SIBLING,
        )

        result = service.get_file("f400")

        assert result.is_ok is True
        agg = result.value
        assert isinstance(agg, FileMetadataAggregate)
        assert len(agg.relations) == 1
        assert agg.relations[0].target_file_id == "f401"

    def test_get_file_with_relations_filtered(
        self,
        service: FileService,
    ) -> None:
        """get_file filters by relation type via relation_types."""
        service.create_file(_file_data(id="f402", path="/tmp/filter_src.py"))
        service.create_file(_file_data(id="f403", path="/tmp/filter_tgt1.py"))
        service.create_file(_file_data(id="f404", path="/tmp/filter_tgt2.py"))

        service.create_relation("f402", "f403", RelationType.SIBLING)
        service.create_relation("f402", "f404", RelationType.PARENT_CHILD)

        result = service.get_file(
            "f402",
            relation_types=[RelationType.SIBLING],
        )

        assert result.is_ok is True
        agg = result.value
        assert len(agg.relations) == 1
        assert agg.relations[0].relation_type == RelationType.SIBLING

    def test_get_file_with_relations_not_found(
        self,
        service: FileService,
    ) -> None:
        """get_file returns ko for nonexistent file."""
        result = service.get_file("nonexistent")
        assert result.is_ko is True

    def test_relation_expansion_with_chunks(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
    ) -> None:
        """Full aggregate: file with chunks and relations."""
        service.create_file(_file_data(id="f410", path="/tmp/full_rel.py", keywords=["expand"]))
        service.create_file(_file_data(id="f411", path="/tmp/related.py"))

        # Add chunks directly to avoid INSERT OR REPLACE cascade
        from src.domain.file_chunk_entity import FileChunk
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f410_mem_fr1",
                "file_id": "f410",
                "memory_id": "mem_fr1",
                "chunk_index": 0,
                "start_line": 1,
                "end_line": 50,
            }).value
        )
        chunk_repo.save_chunk(
            FileChunk.of({
                "id": "fc_f410_mem_fr2",
                "file_id": "f410",
                "memory_id": "mem_fr2",
                "chunk_index": 1,
                "start_line": 51,
                "end_line": 100,
            }).value
        )

        # Add relation
        service.create_relation("f410", "f411", RelationType.CROSS_REFERENCE, strength=0.8)

        # Get full aggregate
        result = service.get_file("f410")
        assert result.is_ok is True
        agg = result.value

        # Verify file
        assert agg.file.id == "f410"
        assert agg.file.aggregated_keywords == ["expand"]

        # Verify chunks
        assert len(agg.chunks) == 2
        assert agg.chunks[0].chunk_index == 0
        assert agg.chunks[1].chunk_index == 1

        # Verify relations
        assert len(agg.relations) == 1
        assert agg.relations[0].relation_type == RelationType.CROSS_REFERENCE
        assert agg.relations[0].strength == 0.8

    def test_relation_found_by_target_file_id(
        self,
        service: FileService,
        relation_repo: FileRelationRepository,
    ) -> None:
        """Relations are found when querying by target file_id (bidirectional lookup)."""
        service.create_file(_file_data(id="f420", path="/tmp/target_rel.py"))
        service.create_file(_file_data(id="f421", path="/tmp/source_rel.py"))
        service.create_relation("f421", "f420", RelationType.BACKLINK)

        # Query by target file — should find the relation
        result = relation_repo.get_relations_by_file_id("f420")
        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].target_file_id == "f420"

# ===================================================================
# Test 5: Error cases
# ===================================================================

class TestErrorCases:
    """Integration: error handling with real repositories."""

    def test_link_chunk_on_missing_file(
        self,
        service: FileService,
    ) -> None:
        """Creating a chunk for a nonexistent file returns ko."""
        result = service.link_chunk("nonexistent", "mem_err1", chunk_index=0)
        assert result.is_ko is True

    def test_create_relation_on_missing_source(
        self,
        service: FileService,
    ) -> None:
        """Creating a relation with missing source file returns ko."""
        service.create_file(_file_data(id="f500", path="/tmp/exists.py"))
        result = service.create_relation("nonexistent", "f500", RelationType.SIBLING)
        assert result.is_ko is True

    def test_update_missing_file(
        self,
        service: FileService,
    ) -> None:
        """Updating a nonexistent file returns ko."""
        result = service.update_file("nonexistent", hash="b" * 64)
        assert result.is_ko is True

    def test_delete_missing_file(
        self,
        service: FileService,
    ) -> None:
        """Deleting a nonexistent file returns ko."""
        result = service.delete_file("nonexistent")
        assert result.is_ko is True

    def test_delete_file_emits_deleted_event(
        self,
        service: FileService,
    ) -> None:
        """Deleting a file emits FileDeletedEvent."""
        service.create_file(_file_data(id="f501", path="/tmp/delete_me.py"))

        result = service.delete_file("f501")

        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert any(isinstance(e, FileDeletedEvent) for e in events)

    def test_delete_file_removes_from_db(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Deleting a file marks it as DELETED in the DB."""
        service.create_file(_file_data(id="f502", path="/tmp/delete_verify.py"))

        service.delete_file("f502")

        db_result = file_repo.get_file_by_id("f502")
        assert db_result.is_ok is True
        assert db_result.value is not None
        assert db_result.value.status == FileStatus.DELETED

    def test_cannot_update_deleted_file(
        self,
        service: FileService,
    ) -> None:
        """Updating a deleted file returns ko."""
        service.create_file(_file_data(id="f503", path="/tmp/deleted.py"))
        service.delete_file("f503")

        result = service.update_file("f503", hash="b" * 64)
        assert result.is_ko is True

    def test_cannot_delete_already_deleted_file(
        self,
        service: FileService,
    ) -> None:
        """Deleting an already deleted file returns ko."""
        service.create_file(_file_data(id="f504", path="/tmp/double_delete.py"))
        service.delete_file("f504")

        result = service.delete_file("f504")
        assert result.is_ko is True

    def test_find_files_by_memory_with_chunk(
        self,
        service: FileService,
    ) -> None:
        """find_files_by_memory returns file when chunk links to it."""
        service.create_file(_file_data(id="f505", path="/tmp/memory_link.py"))
        service.link_chunk("f505", "mem_link", chunk_index=0)

        result = service.find_files_by_memory("mem_link")

        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].id == "f505"

    def test_find_files_by_memory_empty_for_orphan(
        self,
        service: FileService,
    ) -> None:
        """find_files_by_memory returns empty list for orphan memory."""
        result = service.find_files_by_memory("orphan_mem")
        assert result.is_ok is True
        assert result.value == []

# ===================================================================
# Test 6: Upsert operations
# ===================================================================

class TestUpsertOperations:
    """Integration: upsert file creates or updates."""

    def test_upsert_creates_new_file(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Upsert creates a new file when path doesn't exist."""
        data = _file_data(id="f600", path="/tmp/upsert_new.py")
        result = service.upsert_file(data)

        assert result.is_ok is True
        assert result.value.id == "f600"

        # Verify in DB
        db_result = file_repo.get_file_by_path("/tmp/upsert_new.py")
        assert db_result.is_ok is True
        assert db_result.value is not None
        assert db_result.value.id == "f600"

    def test_upsert_updates_existing_file(
        self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """Upsert updates an existing file by path."""
        # Create initial file
        service.create_file(_file_data(id="f601", path="/tmp/upsert_existing.py", keywords=["old"]))

        # Upsert with new keywords
        data = _file_data(id="f601", path="/tmp/upsert_existing.py", keywords=["new"])
        result = service.upsert_file(data)

        assert result.is_ok is True
        assert result.value.id == "f601"
        assert result.value.aggregated_keywords == ["new"]

        # Verify in DB
        db_result = file_repo.get_file_by_id("f601")
        assert db_result.is_ok is True
        assert db_result.value is not None
        assert db_result.value.aggregated_keywords == ["new"]

# ===================================================================
# Test 7: Event emission through full stack
# ===================================================================

class TestEventEmissionFullStack:
    """Integration: domain events propagate through real repositories."""

    def test_file_created_event_has_correct_data(
        self,
        service: FileService,
    ) -> None:
        """FileCreatedEvent contains correct file_id and path."""
        data = _file_data(id="f700", path="/tmp/event_data.py")
        result = service.create_file(data)

        assert result.is_ok is True
        events = result.get_events()
        created_event = next((e for e in events if isinstance(e, FileCreatedEvent)), None)
        assert created_event is not None
        assert created_event.file_id == "f700"
        assert created_event.path == "/tmp/event_data.py"

    def test_chunk_added_event_has_correct_data(
        self,
        service: FileService,
    ) -> None:
        """FileChunkAddedEvent contains correct file_id, memory_id, chunk_index."""
        service.create_file(_file_data(id="f701", path="/tmp/chunk_event.py"))

        result = service.link_chunk("f701", "mem_ce", chunk_index=42)

        assert result.is_ok is True
        events = result.get_events()
        chunk_event = next((e for e in events if isinstance(e, FileChunkAddedEvent)), None)
        assert chunk_event is not None
        assert chunk_event.file_id == "f701"
        assert chunk_event.memory_id == "mem_ce"
        assert chunk_event.chunk_index == 42

    def test_relation_created_event_has_correct_data(
        self,
        service: FileService,
    ) -> None:
        """FileRelationCreatedEvent contains correct source, target, and type."""
        service.create_file(_file_data(id="f702", path="/tmp/rel_event_src.py"))
        service.create_file(_file_data(id="f703", path="/tmp/rel_event_tgt.py"))

        result = service.create_relation(
            source_file_id="f702",
            target_file_id="f703",
            relation_type=RelationType.DEPENDENCY,
        )

        assert result.is_ok is True
        events = result.get_events()
        rel_event = next((e for e in events if isinstance(e, FileRelationCreatedEvent)), None)
        assert rel_event is not None
        assert rel_event.source_file_id == "f702"
        assert rel_event.target_file_id == "f703"
        assert rel_event.relation_type == "dependency"

    def test_update_file_emits_updated_event(
        self,
        service: FileService,
    ) -> None:
        """Updating file metadata emits FileUpdatedEvent."""
        service.create_file(_file_data(id="f704", path="/tmp/update_event.py"))

        result = service.update_file("f704", hash="b" * 64)

        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        updated_event = next((e for e in events if isinstance(e, FileUpdatedEvent)), None)
        assert updated_event is not None
        assert updated_event.file_id == "f704"
        assert "hash" in updated_event.changed_fields

# ===================================================================
# Integration: ForgetMemoryUseCase — chunk and file cleanup
# ===================================================================

class TestForgetMemoryUseCaseIntegration:
    """Integration: ForgetMemoryUseCase cleans up chunks and empty files via SQLite."""

    @pytest.fixture
    def service(
        self,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> FileService:
        """FileService wired with real SQLite repositories."""
        return FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
            memory_client=None,
        )

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def hash_index_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    def test_forget_removes_chunk_and_deletes_empty_file(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
        file_repo: FileRepository,
        mnemosyne_client: MagicMock,
        hash_index_service: MagicMock,
        logger: LoggerMock,
    ) -> None:
        """Full flow: forget memory → chunk removed → file deleted (no remaining chunks)."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        # Create a file with a single chunk
        service.create_file(_file_data(id="f_int_1", path="/tmp/forget_test.py"))
        chunk_result = service.link_chunk(
            file_id="f_int_1",
            memory_id="mem_int_1",
            chunk_index=0,
            start_line=0,
            end_line=10,
        )
        assert chunk_result.is_ok is True

        # Verify chunk exists
        chunks = chunk_repo.get_chunks_by_file_id("f_int_1")
        assert chunks.is_ok is True
        assert len(chunks.value) == 1

        # Verify file exists
        file_before = file_repo.get_file_by_id("f_int_1")
        assert file_before.is_ok is True
        assert file_before.value.status != FileStatus.DELETED

        # Set up use case
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_int_1"}

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=service,
            chunk_repository=chunk_repo,
            bank_type_checker=lambda bank: "pure_memories",
        )

        result = use_case.execute({
            "memory_id": "mem_int_1",
            "memory_bank": "test_bank",
        })

        assert result.is_ok is True
        assert result.value["status"] == "deleted"

        # Chunk should be removed
        chunks_after = chunk_repo.get_chunks_by_file_id("f_int_1")
        assert chunks_after.is_ok is True
        assert len(chunks_after.value) == 0

        # File should be deleted (no remaining chunks)
        file_after = file_repo.get_file_by_id("f_int_1")
        assert file_after.is_ok is True
        assert file_after.value.status == FileStatus.DELETED

        # Hash index should be cleaned
        hash_index_service.remove.assert_called_once_with("mem_int_1")

    def test_forget_removes_chunk_but_keeps_file_with_remaining_chunks(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
        file_repo: FileRepository,
        mnemosyne_client: MagicMock,
        hash_index_service: MagicMock,
        logger: LoggerMock,
    ) -> None:
        """When file has multiple chunks, forget removes one but keeps the file."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        # Create a file with two chunks
        service.create_file(_file_data(id="f_int_2", path="/tmp/forget_multi.py"))
        service.link_chunk(file_id="f_int_2", memory_id="mem_int_2a", chunk_index=0)
        service.link_chunk(file_id="f_int_2", memory_id="mem_int_2b", chunk_index=1)

        # Verify two chunks
        chunks_before = chunk_repo.get_chunks_by_file_id("f_int_2")
        assert len(chunks_before.value) == 2

        # Forget one memory
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_int_2a"}

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=service,
            chunk_repository=chunk_repo,
            bank_type_checker=lambda bank: "pure_memories",
        )

        result = use_case.execute({
            "memory_id": "mem_int_2a",
            "memory_bank": "test_bank",
        })

        assert result.is_ok is True

        # One chunk should remain
        chunks_after = chunk_repo.get_chunks_by_file_id("f_int_2")
        assert len(chunks_after.value) == 1
        assert chunks_after.value[0].memory_id == "mem_int_2b"

        # File should NOT be deleted
        file_after = file_repo.get_file_by_id("f_int_2")
        assert file_after.value.status != FileStatus.DELETED

    def test_forget_rejects_file_metadata_bank(
        self,
        service: FileService,
        mnemosyne_client: MagicMock,
        hash_index_service: MagicMock,
        logger: LoggerMock,
    ) -> None:
        """ForgetMemoryUseCase rejects banks that are not pure_memories."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=service,
            chunk_repository=MagicMock(),
            bank_type_checker=lambda bank: "file_metadata",
        )

        result = use_case.execute({
            "memory_id": "mem_int_3",
            "memory_bank": "test_bank",
        })

        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_BANK_NOT_SUPPORTED"
        mnemosyne_client.forget.assert_not_called()

    def test_forget_no_chunk_cleanup_when_memory_not_found(
        self,
        service: FileService,
        chunk_repo: FileChunkRepository,
        mnemosyne_client: MagicMock,
        hash_index_service: MagicMock,
        logger: LoggerMock,
    ) -> None:
        """When memory not found, no chunk cleanup should occur."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        # Create a file with a chunk
        service.create_file(_file_data(id="f_int_4", path="/tmp/forget_notfound.py"))
        service.link_chunk(file_id="f_int_4", memory_id="mem_int_4", chunk_index=0)

        mnemosyne_client.forget.return_value = {"status": "not_found", "memory_id": "mem_int_4"}

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=service,
            chunk_repository=chunk_repo,
            bank_type_checker=lambda bank: "pure_memories",
        )

        result = use_case.execute({
            "memory_id": "mem_int_4",
            "memory_bank": "test_bank",
        })

        assert result.is_ok is True
        assert result.value["status"] == "not_found"

        # Chunk should still exist
        chunks_after = chunk_repo.get_chunks_by_file_id("f_int_4")
        assert len(chunks_after.value) == 1

        # Hash index should not be cleaned
        hash_index_service.remove.assert_not_called()
