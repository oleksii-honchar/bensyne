"""Unit tests for FileMetadata aggregate root."""

from datetime import datetime
from typing import List, Optional

import pytest

from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.file_entity import File
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation
from src.domain.events.file_events import (
    FileChunkRemovedEvent,
)
from src.domain.events.file_chunk_events import (
    FileChunkCreatedEvent,
    FileChunkUpdatedEvent,
)
from src.domain.events.file_relation_events import (
    FileRelationCreatedEvent,
    FileRelationUpdatedEvent,
)
from src.utils.result import Result
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
    source_type: SourceType = SourceType.VAULT,
    status: FileStatus = FileStatus.PENDING,
    aggregated_keywords: Optional[List[str]] = None,
    aggregated_tags: Optional[List[str]] = None,
    summary: Optional[str] = None,
) -> File:
    """Create a File entity for tests."""
    return File.of(
        {
            "id": id,
            "path": path,
            "source_type": source_type,
            "hash": VALID_HASH,
            "status": status,
            "aggregated_keywords": aggregated_keywords or [],
            "aggregated_tags": aggregated_tags or [],
            "summary": summary,
        }
    ).value


def _make_chunk(
    id: str = "fc1",
    file_id: str = "f1",
    memory_id: str = "m1",
    chunk_index: int = 0,
    start_line: int = 0,
    end_line: int = 0,
    content_hash: Optional[str] = None,
    content_type: Optional[ContentType] = None,
    is_partial: Optional[bool] = None,
    section_header: Optional[str] = None,
    parent_unit_ref: Optional[str] = None,
    parent_unit_summary: Optional[str] = None,
) -> FileChunk:
    """Create a FileChunk entity for tests."""
    props: dict = {
        "id": id,
        "file_id": file_id,
        "memory_id": memory_id,
        "chunk_index": chunk_index,
        "start_line": start_line,
        "end_line": end_line,
    }
    if content_hash is not None:
        props["content_hash"] = content_hash
    if content_type is not None:
        props["content_type"] = content_type
    if is_partial is not None:
        props["is_partial"] = is_partial
    if section_header is not None:
        props["section_header"] = section_header
    if parent_unit_ref is not None:
        props["parent_unit_ref"] = parent_unit_ref
    if parent_unit_summary is not None:
        props["parent_unit_summary"] = parent_unit_summary
    return FileChunk.of(props).value


def _make_relation(
    id: str = "fr1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.PARENT_CHILD,
    strength: float = 0.8,
    direction: Direction = Direction.UNIDIRECTIONAL,
    description: Optional[str] = None,
) -> FileRelation:
    """Create a FileRelation entity for tests."""
    props: dict = {
        "id": id,
        "source_file_id": source_file_id,
        "target_file_id": target_file_id,
        "relation_type": relation_type,
        "strength": strength,
        "direction": direction,
    }
    if description is not None:
        props["description"] = description
    return FileRelation.of(props).value


# ---------------------------------------------------------------------------
# TestFileMetadataOf
# ---------------------------------------------------------------------------


class TestFileMetadataOf:
    """FileMetadata.of returns Result[FileMetadata]."""

    def test_of_returns_ok_with_file_only(self):
        file = _make_file()
        result = FileMetadata.of(file)
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == []
        assert agg.relations == []

    def test_of_returns_ok_with_file_and_chunks(self):
        file = _make_file()
        chunk = _make_chunk()
        result = FileMetadata.of(file, chunks=[chunk])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == [chunk]
        assert agg.relations == []

    def test_of_returns_ok_with_file_and_relations(self):
        file = _make_file()
        relation = _make_relation()
        result = FileMetadata.of(file, relations=[relation])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == []
        assert agg.relations == [relation]

    def test_of_returns_ok_with_all_collections(self):
        file = _make_file()
        chunk = _make_chunk()
        relation = _make_relation()
        result = FileMetadata.of(file, chunks=[chunk], relations=[relation])
        assert result.is_ok is True
        agg = result.value
        assert agg.file is file
        assert agg.chunks == [chunk]
        assert agg.relations == [relation]

    def test_of_with_none_chunks_defaults_to_empty(self):
        file = _make_file()
        result = FileMetadata.of(file, chunks=None)
        assert result.is_ok is True
        assert result.value.chunks == []

    def test_of_with_none_relations_defaults_to_empty(self):
        file = _make_file()
        result = FileMetadata.of(file, relations=None)
        assert result.is_ok is True
        assert result.value.relations == []

    def test_of_returns_frozen_instance(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        with pytest.raises(Exception):
            agg.file = None  # type: ignore


# ---------------------------------------------------------------------------
# TestRemoveChunk
# ---------------------------------------------------------------------------


class TestRemoveChunk:
    """remove_chunk() removes chunk, produces event, updates file metadata."""

    def test_remove_chunk_from_aggregate(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadata.of(file, chunks=[chunk]).value
        result = agg.remove_chunk("m1")
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 0

    def test_remove_chunk_preserves_other_chunks(self):
        file = _make_file()
        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")
        agg = FileMetadata.of(file, chunks=[chunk1, chunk2]).value
        result = agg.remove_chunk("m1")
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 1
        assert new_agg.chunks[0].memory_id == "m2"

    def test_remove_chunk_produces_file_chunk_removed_event(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadata.of(file, chunks=[chunk]).value
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
        agg = FileMetadata.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        new_agg = result.value
        # File should be updated via without_chunk — the file instance changes
        assert new_agg.file is not file

    def test_remove_chunk_returns_new_aggregate(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadata.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        assert result.value is not agg

    def test_remove_chunk_preserves_relations(self):
        file = _make_file()
        chunk = _make_chunk()
        relation = _make_relation()
        agg = FileMetadata.of(file, chunks=[chunk], relations=[relation]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        new_agg = result.value
        assert new_agg.relations == [relation]

    def test_remove_chunk_rejects_nonexistent_memory_id(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        result = agg.remove_chunk("nonexistent")
        assert result.is_ko is True
        assert result.errors[0].error_code == "CHUNK_NOT_FOUND"
        assert result.errors[0].details["file_id"] == "f1"
        assert result.errors[0].details["memory_id"] == "nonexistent"

    def test_remove_chunk_rejection_preserves_aggregate(self):
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadata.of(file, chunks=[chunk]).value
        result = agg.remove_chunk("nonexistent")
        assert result.is_ko is True
        # Original aggregate unchanged
        assert len(agg.chunks) == 1

    def test_remove_chunk_file_without_chunk_ko_propagates(self):
        """If file.without_chunk returns ko, the aggregate propagates the error."""
        deleted_file = _make_file(status=FileStatus.DELETED)
        chunk = _make_chunk()
        agg = FileMetadata.of(deleted_file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        # File.without_chunk should reject on deleted file
        assert result.is_ko is True


# ---------------------------------------------------------------------------
# TestUpsertChunk
# ---------------------------------------------------------------------------


class TestUpsertChunk:
    """upsert_chunk() implements the spec §4.1 decision table.

    Row 1: no existing chunk for memory_id -> add + FileChunkCreatedEvent.
    Row 2: existing, chunk_index differs -> replace (Removed then Created),
           row id fc_{file_id}_{memory_id} preserved.
    Row 3: existing, updatable fields differ -> update_metadata,
           FileChunkUpdatedEvent, row id preserved.
    Row 4: existing, all fields equal -> silent no-op, zero events.
    """

    # -- Row 1: new chunk ----------------------------------------------------

    def test_upsert_new_chunk_adds_to_aggregate(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1")
        result = agg.upsert_chunk(chunk)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 1
        assert new_agg.chunks[0] is chunk

    def test_upsert_new_chunk_reaggregates_file(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1")
        result = agg.upsert_chunk(chunk)
        assert result.is_ok is True
        # File re-aggregated via with_chunk — new file instance
        assert result.value.file is not file

    def test_upsert_new_chunk_event_stream_exactly_created(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=2)
        result = agg.upsert_chunk(chunk)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileChunkCreatedEvent)
        assert event.chunk_id == "fc_f1_m1"
        assert event.file_id == "f1"
        assert event.memory_id == "m1"

    def test_upsert_new_chunk_preserves_relations(self):
        file = _make_file()
        relation = _make_relation()
        agg = FileMetadata.of(file, relations=[relation]).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1")
        result = agg.upsert_chunk(chunk)
        assert result.is_ok is True
        assert result.value.relations == [relation]

    def test_upsert_new_chunk_on_deleted_file_propagates_ko(self):
        deleted_file = _make_file(status=FileStatus.DELETED)
        agg = FileMetadata.of(deleted_file).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1")
        result = agg.upsert_chunk(chunk)
        # File.with_chunk rejects on deleted file
        assert result.is_ko is True

    # -- Row 2: chunk_index differs -> replace -------------------------------

    def test_upsert_index_change_replaces_chunk(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=3)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.chunks) == 1
        assert new_agg.chunks[0].memory_id == "m1"
        assert new_agg.chunks[0].chunk_index == 3

    def test_upsert_index_change_preserves_row_id(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=3)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        # Row id fc_{file_id}_{memory_id} preserved across replacement
        assert result.value.chunks[0].id == "fc_f1_m1"

    def test_upsert_index_change_event_stream_removed_then_created(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=3)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        events = result.get_events()
        assert len(events) == 2
        assert isinstance(events[0], FileChunkRemovedEvent)
        assert events[0].file_id == "f1"
        assert events[0].memory_id == "m1"
        assert isinstance(events[1], FileChunkCreatedEvent)
        assert events[1].chunk_id == "fc_f1_m1"
        assert events[1].file_id == "f1"
        assert events[1].memory_id == "m1"

    def test_upsert_index_change_reaggregates_file(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=1)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        # Replace = remove old + add new -> file re-aggregated
        assert result.value.file is not file

    def test_upsert_index_change_preserves_other_chunks(self):
        file = _make_file()
        other = _make_chunk(id="fc_f1_m0", memory_id="m0", chunk_index=0)
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=1)
        agg = FileMetadata.of(file, chunks=[other, existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=5)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert len(result.value.chunks) == 2
        assert result.value.chunks[0] is other

    def test_upsert_index_change_on_deleted_file_propagates_ko(self):
        deleted_file = _make_file(status=FileStatus.DELETED)
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(deleted_file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=1)
        result = agg.upsert_chunk(incoming)
        # File.without_chunk rejects on deleted file
        assert result.is_ko is True

    # -- Row 3: updatable fields differ -> update_metadata --------------------

    def test_upsert_metadata_change_updates_chunk_in_place(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1")
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(
            id="fc_f1_m1",
            memory_id="m1",
            content_type=ContentType.TEXT,
            start_line=10,
            end_line=20,
        )
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert len(result.value.chunks) == 1
        updated = result.value.chunks[0]
        assert updated.content_type == ContentType.TEXT
        assert updated.start_line == 10
        assert updated.end_line == 20
        # memory_id and chunk_index untouched
        assert updated.memory_id == "m1"
        assert updated.chunk_index == 0

    def test_upsert_metadata_change_preserves_row_id(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1")
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", section_header="New header")
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert result.value.chunks[0].id == "fc_f1_m1"

    def test_upsert_metadata_change_event_exactly_updated(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1")
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", is_partial=True)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileChunkUpdatedEvent)
        assert event.chunk_id == "fc_f1_m1"
        assert "is_partial" in event.changed_fields

    def test_upsert_metadata_change_preserves_other_chunks(self):
        file = _make_file()
        other = _make_chunk(id="fc_f1_m0", memory_id="m0")
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1")
        agg = FileMetadata.of(file, chunks=[other, existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", section_header="H")
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert len(result.value.chunks) == 2
        assert result.value.chunks[0] is other

    def test_upsert_metadata_change_keeps_file_unchanged(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1")
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", section_header="H")
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        # In-place update does not re-aggregate the file
        assert result.value.file is file

    # -- Row 4: all fields equal -> silent no-op ------------------------------

    def test_upsert_identical_chunk_is_silent_noop(self):
        file = _make_file()
        existing = _make_chunk(
            id="fc_f1_m1",
            memory_id="m1",
            content_type=ContentType.CODE,
            start_line=1,
            end_line=9,
            section_header="H",
        )
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(
            id="fc_f1_m1",
            memory_id="m1",
            content_type=ContentType.CODE,
            start_line=1,
            end_line=9,
            section_header="H",
        )
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        # Idempotency contract: zero events
        assert result.has_events() is False
        assert result.get_events() == []

    def test_upsert_identical_chunk_returns_aggregate_unchanged(self):
        file = _make_file()
        existing = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=4)
        agg = FileMetadata.of(file, chunks=[existing]).value
        incoming = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=4)
        result = agg.upsert_chunk(incoming)
        assert result.is_ok is True
        assert result.value is agg
        assert result.value.file is file
        assert result.value.chunks == [existing]

    # -- Cross-cutting: immutability + uniqueness invariant --------------------

    def test_original_aggregate_unchanged_after_upsert(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk = _make_chunk(id="fc_f1_m1", memory_id="m1")
        result = agg.upsert_chunk(chunk)
        assert result.is_ok is True
        # Original aggregate never mutated
        assert len(agg.chunks) == 0
        assert agg.file is file

    def test_upsert_enforces_uniqueness_via_replace_not_reject(self):
        """Repeated upserts of the same memory_id never produce two rows."""
        file = _make_file()
        agg = FileMetadata.of(file).value
        c1 = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=0)
        r1 = agg.upsert_chunk(c1)
        assert r1.is_ok is True
        c2 = _make_chunk(id="fc_f1_m1", memory_id="m1", chunk_index=7)
        r2 = r1.value.upsert_chunk(c2)
        assert r2.is_ok is True
        assert len(r2.value.chunks) == 1
        assert r2.value.chunks[0].chunk_index == 7


# ---------------------------------------------------------------------------
# TestUpsertRelation
# ---------------------------------------------------------------------------


class TestUpsertRelation:
    """upsert_relation() implements the spec §4.2 decision table.

    Dedup key: (target_file_id, relation_type) scoped to
    source_file_id == aggregate.file.id.

    Row 1: no existing (target, type) -> add under canonical id
           fr_{source}_{target}_{type}, exactly one entity-level
           FileRelationCreatedEvent (file_relation_events.py).
    Row 2: existing (target, type), strength/description/direction differ
           -> in-place update, same id, exactly one
           FileRelationUpdatedEvent.
    Row 3: existing (target, type), all equal -> silent no-op, zero events.
    Scope: a relation whose source is not the aggregate's file is rejected.
    Coexistence: the same target under different relation types coexists.
    """

    # -- Row 1: no existing (target, type) -> add with canonical id -----------

    def test_upsert_new_relation_adds_to_aggregate(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        relation = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        new_agg = result.value
        assert len(new_agg.relations) == 1
        stored = new_agg.relations[0]
        assert stored.target_file_id == "f2"
        assert stored.relation_type == RelationType.PARENT_CHILD
        assert stored.strength == 0.8

    def test_upsert_new_relation_stored_with_canonical_id(self):
        """A non-canonical incoming id is normalized to fr_{s}_{t}_{type}."""
        file = _make_file()
        agg = FileMetadata.of(file).value
        relation = _make_relation(
            id="legacy_f1_f2",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        assert result.value.relations[0].id == "fr_f1_f2_parent_child"

    def test_upsert_new_relation_canonical_id_includes_relation_type(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        relation = _make_relation(
            id="fr_f1_f2_sibling",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        assert result.value.relations[0].id == "fr_f1_f2_sibling"

    def test_upsert_new_relation_event_exactly_entity_level_created(self):
        """Event stream is exactly one FileRelationCreatedEvent from
        file_relation_events.py (the entity-level class)."""
        file = _make_file()
        agg = FileMetadata.of(file).value
        relation = _make_relation(
            id="legacy_f1_f2",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        # Strict class check: the single surviving entity-level class
        # (file_relation_events.py); the aggregate-level duplicate was
        # deleted in Task 4.
        assert type(event) is FileRelationCreatedEvent
        assert event.relation_id == "fr_f1_f2_parent_child"
        assert event.source_file_id == "f1"
        assert event.target_file_id == "f2"

    def test_upsert_new_relation_preserves_file_and_chunks(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadata.of(file, chunks=[chunk]).value
        relation = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        # Relations do not re-aggregate the file
        assert result.value.file is file
        assert result.value.chunks == [chunk]

    def test_upsert_new_relation_appends_to_unrelated_existing(self):
        file = _make_file()
        other = _make_relation(
            id="fr_f1_f9_sibling",
            target_file_id="f9",
            relation_type=RelationType.SIBLING,
        )
        agg = FileMetadata.of(file, relations=[other]).value
        relation = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        assert len(result.value.relations) == 2
        assert result.value.relations[0].target_file_id == "f9"
        assert result.value.relations[1].target_file_id == "f2"

    # -- Row 2: existing (target, type), fields differ -> in-place update -----

    def test_upsert_strength_change_updates_in_place(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
            description="old",
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.3,
            description="old",
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert len(result.value.relations) == 1
        updated = result.value.relations[0]
        assert updated.strength == 0.3
        # Untouched fields preserved
        assert updated.description == "old"
        assert updated.direction == Direction.UNIDIRECTIONAL
        assert updated.relation_type == RelationType.PARENT_CHILD

    def test_upsert_update_preserves_existing_id(self):
        """Update in place keeps the existing row id — even a legacy
        fr_{s}_{t} id is not renamed by the aggregate (convergence happens
        at persist time)."""
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.4,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.value.relations[0].id == "fr_f1_f2"
        assert result.value.relations[0].strength == 0.4

    def test_upsert_description_change_updates_in_place(self):
        """description None -> text is a real change (None is a value, not
        an 'unchanged' sentinel)."""
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            description="expanded note",
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.value.relations[0].description == "expanded note"

    def test_upsert_direction_change_updates_in_place(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            direction=Direction.UNIDIRECTIONAL,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            direction=Direction.BIDIRECTIONAL,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.value.relations[0].direction == Direction.BIDIRECTIONAL

    def test_upsert_single_field_change_event_exactly_updated(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.5,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert type(event) is FileRelationUpdatedEvent
        assert event.relation_id == "fr_f1_f2_parent_child"
        assert event.changed_fields == ["strength"]

    def test_upsert_multi_field_change_emits_single_updated_event(self):
        """One upsert fact = exactly one event, even when all three
        upsertable fields differ (D22)."""
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
            direction=Direction.UNIDIRECTIONAL,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.1,
            direction=Direction.BIDIRECTIONAL,
            description="new note",
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert type(event) is FileRelationUpdatedEvent
        assert event.relation_id == "fr_f1_f2_parent_child"
        assert set(event.changed_fields) == {"strength", "description", "direction"}

    def test_upsert_update_preserves_other_relations(self):
        file = _make_file()
        other = _make_relation(
            id="fr_f1_f9_sibling",
            target_file_id="f9",
            relation_type=RelationType.SIBLING,
        )
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        agg = FileMetadata.of(file, relations=[other, existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.9,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert len(result.value.relations) == 2
        assert result.value.relations[0] is other

    # -- Row 3: existing (target, type), all equal -> silent no-op ------------

    def test_upsert_identical_relation_is_silent_noop(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
            direction=Direction.BIDIRECTIONAL,
            description="same",
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
            strength=0.8,
            direction=Direction.BIDIRECTIONAL,
            description="same",
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        # Idempotency contract: zero events
        assert result.has_events() is False
        assert result.get_events() == []

    def test_upsert_identical_relation_returns_aggregate_unchanged(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.value is agg
        assert result.value.file is file
        assert result.value.relations == [existing]

    def test_upsert_identical_fields_different_ids_is_noop(self):
        """Dedup is by (target, type) — not by id. An identical incoming
        relation carrying a different id is still a silent no-op and never
        renames the existing row."""
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f2",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        incoming = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        assert result.has_events() is False
        assert result.value.relations[0].id == "fr_f1_f2"

    # -- Coexistence: same target, different relation types -------------------

    def test_same_target_different_types_coexist(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        rel1 = _make_relation(
            id="fr_f1_f2_sibling",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )
        result1 = agg.upsert_relation(rel1)
        assert result1.is_ok is True
        rel2 = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result2 = result1.value.upsert_relation(rel2)
        assert result2.is_ok is True
        assert len(result2.value.relations) == 2
        types = {r.relation_type for r in result2.value.relations}
        assert types == {RelationType.SIBLING, RelationType.PARENT_CHILD}
        # Both under the same target
        assert all(r.target_file_id == "f2" for r in result2.value.relations)

    # -- Dedup scope: source must be the aggregate's file ---------------------

    def test_rejects_relation_with_foreign_source(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        foreign = _make_relation(
            id="fr_f3_f2_parent_child",
            source_file_id="f3",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(foreign)
        assert result.is_ko is True
        assert result.errors[0].error_code == "RELATION_SOURCE_MISMATCH"
        assert result.errors[0].details["aggregate_file_id"] == "f1"
        assert result.errors[0].details["relation_source_file_id"] == "f3"

    def test_rejection_preserves_aggregate(self):
        file = _make_file()
        existing = _make_relation(
            id="fr_f1_f9_sibling",
            target_file_id="f9",
            relation_type=RelationType.SIBLING,
        )
        agg = FileMetadata.of(file, relations=[existing]).value
        foreign = _make_relation(
            id="fr_f3_f2_parent_child",
            source_file_id="f3",
            target_file_id="f2",
            relation_type=RelationType.PARENT_CHILD,
        )
        result = agg.upsert_relation(foreign)
        assert result.is_ko is True
        # Original aggregate unchanged
        assert len(agg.relations) == 1
        assert agg.relations[0] is existing

    def test_dedup_scoped_to_source_ignores_foreign_source_rows(self):
        """A row in the aggregate whose source is NOT the aggregate's file
        is out of dedup scope — the same (target, type) pair is a NEW
        relation for this aggregate's file, not an update of that row."""
        file = _make_file()
        foreign_row = _make_relation(
            id="fr_f3_f2_sibling",
            source_file_id="f3",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )
        agg = FileMetadata.of(file, relations=[foreign_row]).value
        incoming = _make_relation(
            id="fr_f1_f2_sibling",
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
        )
        result = agg.upsert_relation(incoming)
        assert result.is_ok is True
        # Added, not merged: the foreign row stays untouched, new row added
        assert len(result.value.relations) == 2
        assert result.value.relations[0] is foreign_row
        added = result.value.relations[1]
        assert added.source_file_id == "f1"
        assert added.id == "fr_f1_f2_sibling"

    # -- Cross-cutting: immutability -------------------------------------------

    def test_original_aggregate_unchanged_after_upsert_relation(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        relation = _make_relation(
            id="fr_f1_f2_parent_child",
            target_file_id="f2",
        )
        result = agg.upsert_relation(relation)
        assert result.is_ok is True
        # Original aggregate never mutated
        assert len(agg.relations) == 0
        assert agg.file is file


# ---------------------------------------------------------------------------
# TestChunkUniqueness
# ---------------------------------------------------------------------------


class TestChunkUniqueness:
    """Chunk uniqueness enforced by memory_id across aggregate operations."""

    def test_different_memory_ids_allowed(self):
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")
        result1 = agg.upsert_chunk(chunk1)
        assert result1.is_ok is True
        result2 = result1.value.upsert_chunk(chunk2)
        assert result2.is_ok is True
        assert len(result2.value.chunks) == 2

    def test_remove_then_re_upsert_same_memory_id_allowed(self):
        """After removal, the same memory_id can be upserted again."""
        file = _make_file()
        chunk = _make_chunk(memory_id="m1")
        agg = FileMetadata.of(file, chunks=[chunk]).value

        remove_result = agg.remove_chunk("m1")
        assert remove_result.is_ok is True

        re_add_result = remove_result.value.upsert_chunk(chunk)
        assert re_add_result.is_ok is True
        assert len(re_add_result.value.chunks) == 1


# ---------------------------------------------------------------------------
# TestAggregateImmutability
# ---------------------------------------------------------------------------


class TestAggregateImmutability:
    """Aggregate operations return new instances, never mutate the original."""

    def test_original_aggregate_unchanged_after_remove_chunk(self):
        file = _make_file()
        chunk = _make_chunk()
        agg = FileMetadata.of(file, chunks=[chunk]).value
        result = agg.remove_chunk(chunk.memory_id)
        assert result.is_ok is True
        # Original unchanged
        assert len(agg.chunks) == 1

    def test_chained_operations_build_on_new_instances(self):
        """Chaining upsert_chunk -> upsert_chunk -> remove_chunk works correctly."""
        file = _make_file()
        agg = FileMetadata.of(file).value

        chunk1 = _make_chunk(memory_id="m1")
        chunk2 = _make_chunk(id="fc2", memory_id="m2")

        result1 = agg.upsert_chunk(chunk1)
        result2 = result1.value.upsert_chunk(chunk2)
        result3 = result2.value.remove_chunk("m1")

        assert result3.is_ok is True
        final_agg = result3.value
        assert len(final_agg.chunks) == 1
        assert final_agg.chunks[0].memory_id == "m2"

    def test_events_not_stored_on_aggregate(self):
        """Events are in Result.events, not on the aggregate."""
        file = _make_file()
        agg = FileMetadata.of(file).value
        chunk = _make_chunk()
        result = agg.upsert_chunk(chunk)
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
        agg = FileMetadata.of(file, chunks=[chunk1, chunk2]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk2, chunk1]).value

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
        agg = FileMetadata.of(file, chunks=[chunk1, chunk2]).value

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
        agg = FileMetadata.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.compose_content(mnemosyne_client=fake_get)
        assert result.is_ok is True

        output = result.value
        assert output["summary"] == "Summary"
        assert output["content"] == "Summary"
        assert output["chunks_count"] == 0

    def test_compose_content_no_chunks_no_summary_returns_empty(self):
        file = _make_file()  # no summary
        agg = FileMetadata.of(file, chunks=[]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        agg = FileMetadata.of(file).value

        result = agg.to_dict()
        assert result.is_ok is True
        d = result.value
        assert d["file"]["id"] == "f1"
        assert d["file"]["path"] == "/tmp/test.txt"
        assert d["file"]["source_type"] == "vault"
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
        agg = FileMetadata.of(file).value

        result = agg.to_dict(include_relation_type=RelationType.SIBLING)
        assert result.is_ok is True
        assert result.value["file"]["relation_type"] == "sibling"

    def test_to_dict_relation_type_none_omitted(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        agg = FileMetadata.of(file).value

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
        agg = FileMetadata.of(file, chunks=[chunk1, chunk2]).value

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
        agg = FileMetadata.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Chunk content"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["summary"] is None
        assert d["content"] == "Chunk content"
        assert d["chunks_count"] == 1

    def test_to_dict_with_content_no_chunks_returns_summary_only(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="Only summary")
        agg = FileMetadata.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Should not be called"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["content"] == "Only summary"
        assert d["chunks_count"] == 0

    def test_to_dict_with_content_no_chunks_no_summary_empty(self):
        file = _make_file(id="f1", path="/tmp/test.txt")
        agg = FileMetadata.of(file, chunks=[]).value

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
        agg = FileMetadata.of(file, chunks=[chunk1, chunk2]).value

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
        agg = FileMetadata.of(file, chunks=[chunk2, chunk1]).value

        fake_get = lambda mid: {"content": f"C{mid}"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        d = result.value
        assert d["content"] == "S\n\nCm1\nCm2"

    def test_to_dict_no_content_omits_content_and_chunks_count(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadata.of(file).value

        result = agg.to_dict(include_content=False)
        assert result.is_ok is True
        d = result.value
        assert "content" not in d
        assert "chunks_count" not in d
        assert d["summary"] == "S"

    def test_to_dict_summary_only_returns_summary_as_content(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="Summary text")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
            source_type=SourceType.AGENT_SESSIONS,
            summary="Full summary",
            aggregated_keywords=["k1", "k2"],
            aggregated_tags=["t1"],
        )
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[chunk]).value

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
        assert d["file"]["source_type"] == "agent-sessions"
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
        agg = FileMetadata.of(file).value

        result = agg.to_dict()
        assert result.is_ok is True
        d = result.value
        assert d["metadata"]["file_type"] == ""
        assert d["metadata"]["size"] is None
        assert d["metadata"]["language"] is None

    def test_to_dict_emits_content_composed_event_when_content_composed(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        chunk = _make_chunk(memory_id="m1", chunk_index=0)
        agg = FileMetadata.of(file, chunks=[chunk]).value

        fake_get = lambda mid: {"content": "Body"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert events[0].event_type == "file.content_composed"

    def test_to_dict_no_event_when_no_content(self):
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadata.of(file).value

        result = agg.to_dict(include_content=False)
        assert result.is_ok is True
        assert result.has_events() is False

    def test_to_dict_emits_event_when_content_even_no_chunks(self):
        """compose_content emits FileContentComposedEvent even with 0 chunks."""
        file = _make_file(id="f1", path="/tmp/test.txt", summary="S")
        agg = FileMetadata.of(file, chunks=[]).value

        fake_get = lambda mid: {"content": "Body"}

        result = agg.to_dict(include_content=True, mnemosyne_client=fake_get)
        assert result.is_ok is True
        assert result.has_events() is True
