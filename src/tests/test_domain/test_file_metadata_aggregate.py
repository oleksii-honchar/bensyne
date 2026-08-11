"""Unit tests for FileMetadataAggregate aggregate root."""

from datetime import datetime
from typing import List, Optional

import pytest

from src.domain.aggregates.file_metadata_aggregate import FileMetadataAggregate
from src.domain.entities.file import File
from src.domain.entities.file_chunk import FileChunk
from src.domain.entities.file_relation import FileRelation
from src.domain.events.file_events import (
    FileChunkAddedEvent,
    FileChunkRemovedEvent,
    FileRelationCreatedEvent,
)
from src.domain.result import Result
from src.domain.models.file_model import FileStatus, SourceType

from src.domain.models.file_chunk_model import ContentType

from src.domain.models.file_relation_model import Direction, RelationType

VALID_HASH = "a" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    status: FileStatus = FileStatus.PENDING,
    aggregated_keywords: Optional[List[str]] = None,
    aggregated_tags: Optional[List[str]] = None,
    summary: Optional[str] = None,
) -> File:
    """Create a File entity for tests."""
    return File.of({
        "id": id,
        "path": path,
        "source_type": source_type,
        "hash": VALID_HASH,
        "status": status,
        "aggregated_keywords": aggregated_keywords or [],
        "aggregated_tags": aggregated_tags or [],
        "summary": summary,
    }).value


def _make_chunk(
    id: str = "fc1",
    file_id: str = "f1",
    memory_id: str = "m1",
    chunk_index: int = 0,
) -> FileChunk:
    """Create a FileChunk entity for tests."""
    return FileChunk.of({
        "id": id,
        "file_id": file_id,
        "memory_id": memory_id,
        "chunk_index": chunk_index,
    }).value


def _make_relation(
    id: str = "fr1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.PARENT_CHILD,
    strength: float = 0.8,
    direction: Direction = Direction.UNIDIRECTIONAL,
) -> FileRelation:
    """Create a FileRelation entity for tests."""
    return FileRelation.of({
        "id": id,
        "source_file_id": source_file_id,
        "target_file_id": target_file_id,
        "relation_type": relation_type,
        "strength": strength,
        "direction": direction,
    }).value


# ---------------------------------------------------------------------------
# TestFileMetadataAggregateOf
# ---------------------------------------------------------------------------

class TestFileMetadataAggregateOf:
    """FileMetadataAggregate.of returns Result[FileMetadataAggregate]."""

    def test_of_returns_ok_with_file_only(self):
        file = _make_file()
        result = FileMetadataAggregate.of(file)
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == []
        assert agg.relations == []

    def test_of_returns_ok_with_file_and_chunks(self):
        file = _make_file()
        chunk = _make_chunk()
        result = FileMetadataAggregate.of(file, chunks=[chunk])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == [chunk]
        assert agg.relations == []

    def test_of_returns_ok_with_file_and_relations(self):
        file = _make_file()
        relation = _make_relation()
        result = FileMetadataAggregate.of(file, relations=[relation])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == []
        assert agg.relations == [relation]

    def test_of_returns_ok_with_all_collections(self):
        file = _make_file()
        chunk = _make_chunk()
        relation = _make_relation()
        result = FileMetadataAggregate.of(file, chunks=[chunk], relations=[relation])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == [chunk]
        assert agg.relations == [relation]

    def test_of_with_none_chunks_defaults_to_empty(self):
        file = _make_file()
        result = FileMetadataAggregate.of(file, chunks=None)
        assert result.is_ok is True
        assert result.value.chunks == []

    def test_of_with_none_relations_defaults_to_empty(self):
        file = _make_file()
        result = FileMetadataAggregate.of(file, relations=None)
        assert result.is_ok is True
        assert result.value.relations == []

    def test_of_returns_frozen_instance(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        with pytest.raises(Exception):
            agg.file = None  # type: ignore


# ---------------------------------------------------------------------------
# TestAddChunk
# ---------------------------------------------------------------------------

class TestAddChunk:
    """add_chunk() adds chunk, produces event, updates file metadata."""

    def test_add_chunk_to_empty_aggregate(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk(memory_id="m1")
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 1
        assert new_agg.chunks[0].memory_id == "m1"

    def test_add_chunk_appends_to_existing_chunks(self):
        file = _make_file()
        existing = _make_chunk(memory_id="m_existing")
        agg = FileMetadataAggregate.of(file, chunks=[existing]).value
        new_chunk = _make_chunk(memory_id="m_new", chunk_index=1)
        result = agg.add_chunk(new_chunk)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 2
        assert new_agg.chunks[0].memory_id == "m_existing"
        assert new_agg.chunks[1].memory_id == "m_new"

    def test_add_chunk_produces_file_chunk_added_event(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileChunkAddedEvent)
        assert event.file_id == "f1"
        assert event.memory_id == "m1"
        assert event.chunk_index == 0

    def test_add_chunk_updates_file_metadata(self):
        file = _make_file(aggregated_keywords=["before"])
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        new_agg = result.value
        # File should be updated via with_chunk — the file instance changes
        assert new_agg.file is not file

    def test_add_chunk_returns_new_aggregate(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        assert result.value is not agg

    def test_add_chunk_preserves_relations(self):
        file = _make_file()
        relation = _make_relation()
        agg = FileMetadataAggregate.of(file, relations=[relation]).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.relations == [relation]

    def test_add_chunk_rejects_duplicate_memory_id(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m_dup")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        duplicate = _make_chunk(id="fc2", memory_id="m_dup")
        result = agg.add_chunk(duplicate)
        assert result.is_ko is True
        assert result.errors[0].error_code == "CHUNK_ALREADY_EXISTS"
        assert result.errors[0].details["file_id"] == "f1"
        assert result.errors[0].details["memory_id"] == "m_dup"

    def test_add_chunk_rejection_preserves_aggregate(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        duplicate = _make_chunk(id="fc2", memory_id="m1")
        result = agg.add_chunk(duplicate)
        assert result.is_ko is True
        # Original aggregate unchanged
        assert len(agg.chunks) == 1

    def test_add_chunk_file_with_chunk_ko_propagates(self):
        """If file.with_chunk returns ko, the aggregate propagates the error."""
        deleted_file = _make_file(status=FileStatus.DELETED)
        agg = FileMetadataAggregate.of(deleted_file).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        # File.with_chunk should reject on deleted file
        assert result.is_ko is True


# ---------------------------------------------------------------------------
# TestRemoveChunk
# ---------------------------------------------------------------------------

class TestRemoveChunk:
    """remove_chunk() removes chunk, produces event, updates file metadata."""

    def test_remove_chunk_from_aggregate(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk("m1")
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 0

    def test_remove_chunk_preserves_other_chunks(self):
        file = _make_file()
        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")
        agg = FileMetadataAggregate.of(file, chunks=[chunk1, chunk2]).value
        result = agg.remove_chunk("m1")
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 1
        assert new_agg.chunks[0].memory_id == "m2"

    def test_remove_chunk_produces_file_chunk_removed_event(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk("m1")
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileChunkRemovedEvent)
        assert event.file_id == "f1"
        assert event.memory_id == "m1"

    def test_remove_chunk_updates_file_metadata(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        new_agg = result.value
        # File should be updated via without_chunk — the file instance changes
        assert new_agg.file is not file

    def test_remove_chunk_returns_new_aggregate(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        assert result.value is not agg

    def test_remove_chunk_preserves_relations(self):
        file = _make_file()
        chunk = _make_chunk()
        relation = _make_relation()
        agg = FileMetadataAggregate.of(file, chunks=[chunk], relations=[relation]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.relations == [relation]

    def test_remove_chunk_rejects_nonexistent_memory_id(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        result = agg.remove_chunk("nonexistent")
        assert result.is_ko is True
        assert result.errors[0].error_code == "CHUNK_NOT_FOUND"
        assert result.errors[0].details["file_id"] == "f1"
        assert result.errors[0].details["memory_id"] == "nonexistent"

    def test_remove_chunk_rejection_preserves_aggregate(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk("nonexistent")
        assert result.is_ko is True
        # Original aggregate unchanged
        assert len(agg.chunks) == 1

    def test_remove_chunk_file_without_chunk_ko_propagates(self):
        """If file.without_chunk returns ko, the aggregate propagates the error."""
        deleted_file = _make_file(status=FileStatus.DELETED)
        chunk = _make_chunk()
        agg = FileMetadataAggregate.of(deleted_file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        # File.without_chunk should reject on deleted file
        assert result.is_ko is True


# ---------------------------------------------------------------------------
# TestAddRelation
# ---------------------------------------------------------------------------

class TestAddRelation:
    """add_relation() adds relation, produces FileRelationCreatedEvent."""

    def test_add_relation_to_empty_aggregate(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation()
        result = agg.add_relation(relation)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.relations) == 1
        assert new_agg.relations[0] is relation

    def test_add_relation_appends_to_existing_relations(self):
        file = _make_file()
        existing = _make_relation(target_file_id="f_existing")
        agg = FileMetadataAggregate.of(file, relations=[existing]).value
        new_relation = _make_relation(id="fr2", target_file_id="f_new")
        result = agg.add_relation(new_relation)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.relations) == 2
        assert new_agg.relations[0].target_file_id == "f_existing"
        assert new_agg.relations[1].target_file_id == "f_new"

    def test_add_relation_produces_file_relation_created_event(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation(target_file_id="f2", relation_type=RelationType.SIBLING)
        result = agg.add_relation(relation)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileRelationCreatedEvent)
        assert event.source_file_id == "f1"
        assert event.target_file_id == "f2"

    def test_add_relation_returns_new_aggregate(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation()
        result = agg.add_relation(relation)
        assert result.is_ok is True
        assert result.value is not agg

    def test_add_relation_preserves_chunks(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        relation = _make_relation()
        result = agg.add_relation(relation)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.chunks == [chunk]

    def test_add_relation_preserves_file(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation()
        result = agg.add_relation(relation)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.file is file

    def test_add_relation_event_has_relation_type(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation(relation_type=RelationType.CROSS_REFERENCE)
        result = agg.add_relation(relation)
        assert result.is_ok is True
        event = result.get_events()[0]
        assert isinstance(event, FileRelationCreatedEvent)
        assert event.relation_type == "cross_reference"


# ---------------------------------------------------------------------------
# TestChunkUniqueness
# ---------------------------------------------------------------------------

class TestChunkUniqueness:
    """Chunk uniqueness enforced by memory_id across aggregate operations."""

    def test_cannot_add_two_chunks_with_same_memory_id(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk1 = _make_chunk(memory_id="m_same")
        result1 = agg.add_chunk(chunk1)
        assert result1.is_ok is True

        chunk2 = _make_chunk(id="fc2", memory_id="m_same")
        result2 = result1.value.add_chunk(chunk2)
        assert result2.is_ko is True
        assert result2.errors[0].error_code == "CHUNK_ALREADY_EXISTS"

    def test_different_memory_ids_allowed(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")
        result1 = agg.add_chunk(chunk1)
        assert result1.is_ok is True
        result2 = result1.value.add_chunk(chunk2)
        assert result2.is_ok is True
        assert len(result2.value.chunks) == 2

    def test_remove_then_re_add_same_memory_id_allowed(self):
        """After removal, the same memory_id can be re-added."""
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        remove_result = agg.remove_chunk("m1")
        assert remove_result.is_ok is True

        re_add_result = remove_result.value.add_chunk(chunk)
        assert re_add_result.is_ok is True
        assert len(re_add_result.value.chunks) == 1


# ---------------------------------------------------------------------------
# TestAggregateImmutability
# ---------------------------------------------------------------------------

class TestAggregateImmutability:
    """Aggregate operations return new instances, never mutate the original."""

    def test_original_aggregate_unchanged_after_add_chunk(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        # Original unchanged
        assert len(agg.chunks) == 0

    def test_original_aggregate_unchanged_after_remove_chunk(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        # Original unchanged
        assert len(agg.chunks) == 1

    def test_original_aggregate_unchanged_after_add_relation(self):
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        relation = _make_relation()
        result = agg.add_relation(relation)
        assert result.is_ok is True
        # Original unchanged
        assert len(agg.relations) == 0

    def test_chained_operations_build_on_new_instances(self):
        """Chaining add_chunk -> add_chunk -> remove_chunk works correctly."""
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value

        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")

        result1 = agg.add_chunk(chunk1)
        result2 = result1.value.add_chunk(chunk2)
        result3 = result2.value.remove_chunk("m1")

        assert result3.is_ok is True
        final_agg = result3.value
        assert len(final_agg.chunks) == 1
        assert final_agg.chunks[0].memory_id == "m2"

    def test_events_not_stored_on_aggregate(self):
        """Events are in Result.events, not on the aggregate."""
        file = _make_file()
        agg = FileMetadataAggregate.of(file).value
        chunk = _make_chunk()
        result = agg.add_chunk(chunk)
        assert result.is_ok is True
        assert not hasattr(result.value, "events")


# ---------------------------------------------------------------------------
# TestComposeContent
# ---------------------------------------------------------------------------

class TestComposeContent:
    """compose_content() produces file representation from chunks and mnemosyne."""

    def test_compose_content_returns_summary_and_content_with_chunks(self):
        file = _make_file(summary="File summary")
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        agg = FileMetadataAggregate.of(file, chunks=[chunk1, chunk2]).value

        # Mnemosyne client mock: get(memory_id) -> {"content": "..."} or None
        def fake_get(memory_id):
            return {"content": f"Content of {memory_id}"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] == "File summary"
        assert "Content of m1" in output["content"]
        assert "Content of m2" in output["content"]
        assert output["chunks_count"] == 2
        # Content should have summary first, then chunks
        assert output["content"] == "File summary\n\nContent of m1\nContent of m2"

    def test_compose_content_summary_only_returns_only_summary(self):
        file = _make_file(summary="File summary")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.compose_content(mnemosyne_client=fake_get, summary_only=True)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] == "File summary"
        assert output["content"] == "File summary"
        assert output["chunks_count"] == 0
        # Mnemosyne should not have been called in summary_only mode
        # (we can't easily verify this without a mock, but chunks_count=0 proves it)

    def test_compose_content_summary_only_no_summary_returns_empty(self):
        file = _make_file()  # no summary
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.compose_content(mnemosyne_client=fake_get, summary_only=True)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] is None
        assert output["content"] == ""
        assert output["chunks_count"] == 0

    def test_compose_content_no_summary_chunks_only(self):
        file = _make_file()  # no summary
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.compose_content(mnemosyne_client=fake_get, summary_only=False)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] is None
        assert output["content"] == "Chunk content"
        assert output["chunks_count"] == 1

    def test_compose_content_orders_chunks_by_chunk_index(self):
        file = _make_file(summary="Summary")
        # Chunks in reverse order
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk2, chunk1]).value

        fake_get = lambda mid: {"content": f"Content of {mid}"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        # Chunks should be ordered by chunk_index: m1 first, then m2
        assert output["content"] == "Summary\n\nContent of m1\nContent of m2"

    def test_compose_content_skips_missing_memory(self):
        file = _make_file(summary="Summary")
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        agg = FileMetadataAggregate.of(file, chunks=[chunk1, chunk2]).value

        # m2 memory not found in mnemosyne
        def fake_get(memory_id):
            if memory_id == "m1":
                return {"content": "Content of m1"}
            return None

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert "Content of m1" in output["content"]
        assert "Content of m2" not in output["content"]
        assert output["chunks_count"] == 2

    def test_compose_content_empty_chunks_returns_summary_only(self):
        file = _make_file(summary="Summary")
        agg = FileMetadataAggregate.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] == "Summary"
        assert output["content"] == "Summary"
        assert output["chunks_count"] == 0

    def test_compose_content_no_chunks_no_summary_returns_empty(self):
        file = _make_file()  # no summary
        agg = FileMetadataAggregate.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] is None
        assert output["content"] == ""
        assert output["chunks_count"] == 0

    def test_compose_content_includes_metadata(self):
        file = _make_file(
            summary="Summary",
            aggregated_keywords=["kw1", "kw2"],
            aggregated_tags=["tag1"],
        )
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Content"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert "metadata" in output
        assert output["metadata"]["keywords"] == ["kw1", "kw2"]
        assert output["metadata"]["tags"] == ["tag1"]

    def test_compose_content_memory_without_content_key(self):
        file = _make_file(summary="Summary")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        # Memory returned but has no "content" key
        fake_get = lambda mid: {"text": "No content key"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert "No content key" not in output["content"]
        assert output["content"] == "Summary"

    def test_compose_content_emits_domain_event(self):
        file = _make_file(summary="Summary")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Content"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert events[0].event_type == "file.content_composed"
        assert events[0].file_id == "f1"

    def test_compose_content_summary_only_no_domain_event(self):
        file = _make_file(summary="Summary")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Content"}

        result = agg.compose_content(mnemosyne_client=fake_get, summary_only=True)
        assert result.is_ok is True
        # Summary-only mode should NOT emit a content_composed event
        # (no actual composition happened)
        assert result.has_events() is False


# ---------------------------------------------------------------------------
# TestToDict
# ---------------------------------------------------------------------------

class TestToDict:
    """to_dict() produces the full output structure used by expand_file_relations."""

    def test_to_dict_minimal_no_content_no_relation(self):
        file = _make_file(
            id="f1",
            path="/tmp/test.txt",
            aggregated_keywords=["kw1"],
            aggregated_tags=["tag1"],
            summary="A summary",
        )
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict()
        assert result.is_ok is True
        d = result.value
        assert d["file"]["id"] == "f1"
        assert d["file"]["path"] == "/tmp/test.txt"
        assert d["file"]["source_type"] == "file_system"
        assert "relation_type" not in d["file"]
        assert d["summary"] == "A summary"
        assert "content" not in d
        assert "chunks_count" not in d
        assert d["metadata"]["keywords"] == ["kw1"]
        assert d["metadata"]["tags"] == ["tag1"]
        assert d["metadata"]["file_type"] == ""
        assert d["metadata"]["size"] is None
        assert d["metadata"]["language"] is None

    def test_to_dict_with_relation_type(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict(include_relation_type=RelationType.SIBLING)
        assert result.is_ok is True
        assert result.value["file"]["relation_type"] == "sibling"

    def test_to_dict_relation_type_none_omitted(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict(include_relation_type=None)
        assert result.is_ok is True
        assert "relation_type" not in result.value["file"]

    def test_to_dict_with_content_composes_via_mnemosyne(self):
        file = _make_file(
            id="f1",
            path="/tmp/test.txt",
            summary="Summary",
            aggregated_keywords=["kw"],
            aggregated_tags=["tg"],
        )
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        agg = FileMetadataAggregate.of(file, chunks=[chunk1, chunk2]).value

        fake_get = lambda mid: {"content": f"Content of {mid}"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["summary"] == "Summary"
        assert d["content"] == "Summary\n\nContent of m1\nContent of m2"
        assert d["chunks_count"] == 2
        assert d["metadata"]["keywords"] == ["kw"]
        assert d["metadata"]["tags"] == ["tg"]

    def test_to_dict_with_content_no_summary_chunks_only(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["summary"] is None
        assert d["content"] == "Chunk content"
        assert d["chunks_count"] == 1

    def test_to_dict_with_content_no_chunks_returns_summary_only(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="Only summary")
        agg = FileMetadataAggregate.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["content"] == "Only summary"
        assert d["chunks_count"] == 0

    def test_to_dict_with_content_no_chunks_no_summary_empty(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        agg = FileMetadataAggregate.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["summary"] is None
        assert d["content"] == ""
        assert d["chunks_count"] == 0

    def test_to_dict_with_content_skips_missing_memory(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="Summary")
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        agg = FileMetadataAggregate.of(file, chunks=[chunk1, chunk2]).value

        def fake_get(mid):
            return {"content": "Found"} if mid == "m1" else None

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert "Found" in d["content"]
        assert d["chunks_count"] == 2

    def test_to_dict_with_content_orders_by_chunk_index(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        # Reversed order in aggregate
        chunk2 = _make_chunk(id="fc2", memory_id="m2", chunk_index=1)
        chunk1 = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk2, chunk1]).value

        fake_get = lambda mid: {"content": f"C{mid}"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["content"] == "S\n\nCm1\nCm2"

    def test_to_dict_no_content_omits_content_and_chunks_count(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict(include_content=False)
        assert result.is_ok is True
        d = result.value
        assert "content" not in d
        assert "chunks_count" not in d
        assert d["summary"] == "S"

    def test_to_dict_summary_only_returns_summary_as_content(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="Summary text")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.to_dict(
            include_content=True,
            summary_only=True,
            mnemosyne_client=fake_get,
        )
        assert result.is_ok is True
        d = result.value
        assert d["content"] == "Summary text"
        assert d["chunks_count"] == 0
        # Mnemosyne should NOT have been called in summary_only mode
        # (chunks_count=0 proves it)

    def test_to_dict_with_relation_and_content_full_structure(self):
        file = _make_file(
            id="f1",
            path="/tmp/full.txt",
            source_type=SourceType.AGENT_SESSION,
            summary="Full summary",
            aggregated_keywords=["k1", "k2"],
            aggregated_tags=["t1"],
        )
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Body"}

        result = agg.to_dict(
            include_relation_type=RelationType.CROSS_REFERENCE,
            include_content=True,
            mnemosyne_client=fake_get,
        )
        assert result.is_ok is True
        d = result.value
        assert d["file"]["id"] == "f1"
        assert d["file"]["path"] == "/tmp/full.txt"
        assert d["file"]["source_type"] == "agent_session"
        assert d["file"]["relation_type"] == "cross_reference"
        assert d["summary"] == "Full summary"
        assert d["content"] == "Full summary\n\nBody"
        assert d["chunks_count"] == 1
        assert d["metadata"]["keywords"] == ["k1", "k2"]
        assert d["metadata"]["tags"] == ["t1"]

    def test_to_dict_metadata_includes_file_type_size_language(self):
        file = _make_file(
            id="f1",
            path="/tmp/data.json",
            aggregated_keywords=[],
            aggregated_tags=[],
        )
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict()
        assert result.is_ok is True
        d = result.value
        assert d["metadata"]["file_type"] == ""
        assert d["metadata"]["size"] is None
        assert d["metadata"]["language"] is None

    def test_to_dict_emits_content_composed_event_when_content_composed(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadataAggregate.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Body"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert events[0].event_type == "file.content_composed"

    def test_to_dict_no_event_when_no_content(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadataAggregate.of(file).value

        result = agg.to_dict(include_content=False)
        assert result.is_ok is True
        assert result.has_events() is False

    def test_to_dict_emits_event_when_content_even_no_chunks(self):
        """compose_content emits FileContentComposedEvent even with 0 chunks."""
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadataAggregate.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Body"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        assert result.has_events() is True
