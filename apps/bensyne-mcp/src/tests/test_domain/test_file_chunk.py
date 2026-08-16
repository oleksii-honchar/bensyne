"""Unit tests for FileChunk domain entity, enums, and domain events."""

from datetime import datetime

import pytest

from src.domain.file_chunk_entity import (
    ContentType,
    FileChunk,
)
from src.domain.events.file_chunk_events import (
    FileChunkCreatedEvent,
    FileChunkUpdatedEvent,
)
from src.utils.result import DomainEvent, ErrorWithDetails, Result

VALID_CONTENT_HASH = "b" * 64


class TestFileChunkOfValidData:
    """FileChunk.of accepts valid data and returns Result.ok."""

    def test_of_returns_ok_with_minimal_required_fields(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
            }
        )
        assert result.is_ok is True
        chunk = result.value
        assert chunk.id == "fc1"
        assert chunk.file_id == "f1"
        assert chunk.memory_id == "m1"
        assert chunk.chunk_index == 0
        assert chunk.start_line == 0
        assert chunk.end_line == 0
        assert chunk.content_hash is None
        assert chunk.content_type == ContentType.UNKNOWN
        assert chunk.is_partial is False
        assert chunk.created_at is not None
        assert chunk.updated_at is not None

    def test_of_returns_ok_with_all_fields(self):
        now = datetime.now()
        result = FileChunk.of(
            {
                "id": "fc2",
                "file_id": "f2",
                "memory_id": "m2",
                "chunk_index": 3,
                "start_line": 50,
                "end_line": 100,
                "content_hash": VALID_CONTENT_HASH,
                "content_type": ContentType.CODE,
                "is_partial": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert result.is_ok is True
        chunk = result.value
        assert chunk.id == "fc2"
        assert chunk.file_id == "f2"
        assert chunk.memory_id == "m2"
        assert chunk.chunk_index == 3
        assert chunk.start_line == 50
        assert chunk.end_line == 100
        assert chunk.content_hash == VALID_CONTENT_HASH
        assert chunk.content_type == ContentType.CODE
        assert chunk.is_partial is True
        assert chunk.created_at == now
        assert chunk.updated_at == now

    def test_of_sets_timestamps_when_not_provided(self):
        result = FileChunk.of(
            {
                "id": "fc3",
                "file_id": "f3",
                "memory_id": "m3",
                "chunk_index": 0,
            }
        )
        assert result.is_ok is True
        chunk = result.value
        assert isinstance(chunk.created_at, datetime)
        assert isinstance(chunk.updated_at, datetime)

    def test_of_returns_frozen_instance(self):
        result = FileChunk.of(
            {
                "id": "fc4",
                "file_id": "f4",
                "memory_id": "m4",
                "chunk_index": 0,
            }
        )
        assert result.is_ok is True
        chunk = result.value
        with pytest.raises(Exception):
            chunk.file_id = "f5"  # type: ignore

    def test_of_accepts_all_content_types(self):
        for ct in ContentType:
            result = FileChunk.of(
                {
                    "id": f"fc_ct_{ct.value}",
                    "file_id": "f_ct",
                    "memory_id": "m_ct",
                    "chunk_index": 0,
                    "content_type": ct,
                }
            )
            assert result.is_ok is True
            assert result.value.content_type == ct

    def test_of_with_zero_chunk_index(self):
        result = FileChunk.of(
            {
                "id": "fc5",
                "file_id": "f5",
                "memory_id": "m5",
                "chunk_index": 0,
            }
        )
        assert result.is_ok is True
        assert result.value.chunk_index == 0

    def test_of_with_is_partial_false(self):
        result = FileChunk.of(
            {
                "id": "fc6",
                "file_id": "f6",
                "memory_id": "m6",
                "chunk_index": 0,
                "is_partial": False,
            }
        )
        assert result.is_ok is True
        assert result.value.is_partial is False

    def test_of_with_is_partial_true(self):
        result = FileChunk.of(
            {
                "id": "fc7",
                "file_id": "f7",
                "memory_id": "m7",
                "chunk_index": 0,
                "is_partial": True,
            }
        )
        assert result.is_ok is True
        assert result.value.is_partial is True

    def test_of_with_zero_line_range(self):
        result = FileChunk.of(
            {
                "id": "fc8",
                "file_id": "f8",
                "memory_id": "m8",
                "chunk_index": 0,
                "start_line": 0,
                "end_line": 0,
            }
        )
        assert result.is_ok is True
        assert result.value.start_line == 0
        assert result.value.end_line == 0

    def test_of_with_none_content_hash(self):
        result = FileChunk.of(
            {
                "id": "fc9",
                "file_id": "f9",
                "memory_id": "m9",
                "chunk_index": 0,
                "content_hash": None,
            }
        )
        assert result.is_ok is True
        assert result.value.content_hash is None

    def test_of_emits_created_event(self):
        result = FileChunk.of(
            {
                "id": "fc10",
                "file_id": "f10",
                "memory_id": "m10",
                "chunk_index": 0,
            }
        )
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert isinstance(events[0], FileChunkCreatedEvent)
        event = events[0]
        assert event.chunk_id == "fc10"
        assert event.file_id == "f10"
        assert event.memory_id == "m10"

    def test_of_is_domain_event(self):
        result = FileChunk.of(
            {
                "id": "fc11",
                "file_id": "f11",
                "memory_id": "m11",
                "chunk_index": 0,
            }
        )
        event = result.get_events()[0]
        assert isinstance(event, DomainEvent)


class TestFileChunkOfRejectsInvalidData:
    """FileChunk.of rejects invalid data and returns Result.ko."""

    def test_of_rejects_missing_id(self):
        result = FileChunk.of(
            {
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_missing_file_id(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "memory_id": "m1",
                "chunk_index": 0,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_missing_memory_id(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "chunk_index": 0,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_missing_chunk_index(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
            }
        )
        assert result.is_ko is True

    def test_of_rejects_negative_chunk_index(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": -1,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_negative_start_line(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
                "start_line": -1,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_negative_end_line(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
                "end_line": -1,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_end_line_before_start_line(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
                "start_line": 100,
                "end_line": 50,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_invalid_content_hash(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
                "content_hash": "not-a-valid-hash",
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_invalid_content_type(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "m1",
                "chunk_index": 0,
                "content_type": "INVALID_TYPE",
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_empty_file_id(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "",
                "memory_id": "m1",
                "chunk_index": 0,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"

    def test_of_rejects_empty_memory_id(self):
        result = FileChunk.of(
            {
                "id": "fc1",
                "file_id": "f1",
                "memory_id": "",
                "chunk_index": 0,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK"


class TestFileChunkPositionTracking:
    """FileChunk position tracking and line range validation."""

    def _create_chunk(self, **overrides) -> FileChunk:
        props = {
            "id": "fc_pos",
            "file_id": "f_pos",
            "memory_id": "m_pos",
            "chunk_index": 0,
        }
        props.update(overrides)
        return FileChunk.of(props).value

    def test_default_line_range_is_zero(self):
        chunk = self._create_chunk()
        assert chunk.start_line == 0
        assert chunk.end_line == 0

    def test_line_range_with_valid_values(self):
        chunk = self._create_chunk(start_line=10, end_line=50)
        assert chunk.start_line == 10
        assert chunk.end_line == 50

    def test_line_range_equal_start_and_end(self):
        chunk = self._create_chunk(start_line=42, end_line=42)
        assert chunk.start_line == 42
        assert chunk.end_line == 42

    def test_chunk_index_ordering(self):
        chunk0 = self._create_chunk(chunk_index=0)
        chunk1 = self._create_chunk(chunk_index=1)
        chunk2 = self._create_chunk(chunk_index=2)
        assert chunk0.chunk_index < chunk1.chunk_index < chunk2.chunk_index

    def test_line_range_spans(self):
        chunk_a = self._create_chunk(chunk_index=0, start_line=1, end_line=50)
        chunk_b = self._create_chunk(chunk_index=1, start_line=51, end_line=100)
        assert chunk_a.end_line + 1 == chunk_b.start_line

    def test_content_hash_valid(self):
        chunk = self._create_chunk(content_hash=VALID_CONTENT_HASH)
        assert chunk.content_hash == VALID_CONTENT_HASH

    def test_content_hash_none_by_default(self):
        chunk = self._create_chunk()
        assert chunk.content_hash is None

    def test_is_partial_default_false(self):
        chunk = self._create_chunk()
        assert chunk.is_partial is False

    def test_is_partial_true(self):
        chunk = self._create_chunk(is_partial=True)
        assert chunk.is_partial is True

    def test_content_type_default_unknown(self):
        chunk = self._create_chunk()
        assert chunk.content_type == ContentType.UNKNOWN

    def test_content_type_text(self):
        chunk = self._create_chunk(content_type=ContentType.TEXT)
        assert chunk.content_type == ContentType.TEXT

    def test_content_type_code(self):
        chunk = self._create_chunk(content_type=ContentType.CODE)
        assert chunk.content_type == ContentType.CODE

    def test_content_type_config(self):
        chunk = self._create_chunk(content_type=ContentType.CONFIG)
        assert chunk.content_type == ContentType.CONFIG

    def test_content_type_image(self):
        chunk = self._create_chunk(content_type=ContentType.IMAGE)
        assert chunk.content_type == ContentType.IMAGE

    def test_content_type_binary(self):
        chunk = self._create_chunk(content_type=ContentType.BINARY)
        assert chunk.content_type == ContentType.BINARY


class TestFileChunkUpdateMetadata:
    """FileChunk.update_metadata method with event emission."""

    def _create_chunk(self, **overrides) -> FileChunk:
        props = {
            "id": "fc_upd",
            "file_id": "f_upd",
            "memory_id": "m_upd",
            "chunk_index": 0,
        }
        props.update(overrides)
        return FileChunk.of(props).value

    def test_update_content_type(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_type=ContentType.CODE)
        assert result.is_ok is True
        updated = result.value
        assert updated.content_type == ContentType.CODE
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileChunkUpdatedEvent)

    def test_update_content_hash(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_hash=VALID_CONTENT_HASH)
        assert result.is_ok is True
        updated = result.value
        assert updated.content_hash == VALID_CONTENT_HASH
        assert result.has_events() is True

    def test_update_is_partial(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(is_partial=True)
        assert result.is_ok is True
        updated = result.value
        assert updated.is_partial is True
        assert result.has_events() is True

    def test_update_line_range(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(start_line=10, end_line=50)
        assert result.is_ok is True
        updated = result.value
        assert updated.start_line == 10
        assert updated.end_line == 50
        assert result.has_events() is True

    def test_update_multiple_fields(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(
            content_type=ContentType.TEXT,
            content_hash=VALID_CONTENT_HASH,
            is_partial=True,
        )
        assert result.is_ok is True
        updated = result.value
        assert updated.content_type == ContentType.TEXT
        assert updated.content_hash == VALID_CONTENT_HASH
        assert updated.is_partial is True
        assert result.has_events() is True

    def test_update_no_changes_returns_same_instance(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata()
        assert result.is_ok is True
        assert result.value is chunk
        assert result.has_events() is False

    def test_update_preserves_existing_fields(self):
        chunk = self._create_chunk(
            content_type=ContentType.CODE,
            content_hash=VALID_CONTENT_HASH,
        )
        result = chunk.update_metadata(is_partial=True)
        assert result.is_ok is True
        updated = result.value
        assert updated.content_type == ContentType.CODE
        assert updated.content_hash == VALID_CONTENT_HASH
        assert updated.is_partial is True

    def test_update_rejects_invalid_content_hash(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_hash="invalid-hash")
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_CONTENT_HASH"

    def test_update_rejects_invalid_content_type(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_type="INVALID")  # type: ignore
        assert result.is_ko is True

    def test_update_rejects_negative_start_line(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(start_line=-1)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_LINE_RANGE"

    def test_update_rejects_negative_end_line(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(end_line=-1)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_LINE_RANGE"

    def test_update_rejects_end_before_start(self):
        chunk = self._create_chunk(start_line=50, end_line=100)
        result = chunk.update_metadata(start_line=150)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_LINE_RANGE"

    def test_update_updated_at_changes(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_type=ContentType.TEXT)
        assert result.is_ok is True
        updated = result.value
        assert updated.updated_at is not None
        assert updated.updated_at >= chunk.created_at

    def test_update_changed_fields_in_event(self):
        chunk = self._create_chunk()
        result = chunk.update_metadata(content_type=ContentType.TEXT, is_partial=True)
        assert result.is_ok is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileChunkUpdatedEvent)
        assert "content_type" in event.changed_fields
        assert "is_partial" in event.changed_fields


class TestFileChunkCreatedEvent:
    """FileChunkCreatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileChunkCreatedEvent.of(
            chunk_id="fc1",
            file_id="f1",
            memory_id="m1",
        )
        assert result.is_ok is True
        event = result.value
        assert event.chunk_id == "fc1"
        assert event.file_id == "f1"
        assert event.memory_id == "m1"

    def test_factory_rejects_empty_chunk_id(self):
        result = FileChunkCreatedEvent.of(chunk_id="", file_id="f1", memory_id="m1")
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK_CREATED_EVENT"

    def test_factory_rejects_empty_file_id(self):
        result = FileChunkCreatedEvent.of(chunk_id="fc1", file_id="", memory_id="m1")
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK_CREATED_EVENT"

    def test_factory_rejects_empty_memory_id(self):
        result = FileChunkCreatedEvent.of(chunk_id="fc1", file_id="f1", memory_id="")
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK_CREATED_EVENT"

    def test_event_type(self):
        event = FileChunkCreatedEvent.of("fc1", "f1", "m1").value
        assert event.event_type == "file_chunk.created"

    def test_get_name(self):
        event = FileChunkCreatedEvent.of("fc1", "f1", "m1").value
        assert event.get_name() == "file_chunk.created"

    def test_timestamp_is_datetime(self):
        event = FileChunkCreatedEvent.of("fc1", "f1", "m1").value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        event = FileChunkCreatedEvent.of("fc1", "f1", "m1").value
        assert isinstance(event, DomainEvent)


class TestFileChunkUpdatedEvent:
    """FileChunkUpdatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileChunkUpdatedEvent.of(
            chunk_id="fc1",
            changed_fields=["content_type", "is_partial"],
        )
        assert result.is_ok is True
        event = result.value
        assert event.chunk_id == "fc1"
        assert event.changed_fields == ["content_type", "is_partial"]

    def test_factory_rejects_empty_chunk_id(self):
        result = FileChunkUpdatedEvent.of(chunk_id="", changed_fields=["content_type"])
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_CHUNK_UPDATED_EVENT"

    def test_factory_accepts_empty_changed_fields(self):
        result = FileChunkUpdatedEvent.of(chunk_id="fc1", changed_fields=[])
        assert result.is_ok is True

    def test_event_type(self):
        event = FileChunkUpdatedEvent.of("fc1", ["content_type"]).value
        assert event.event_type == "file_chunk.updated"

    def test_get_name(self):
        event = FileChunkUpdatedEvent.of("fc1", ["content_type"]).value
        assert event.get_name() == "file_chunk.updated"

    def test_is_domain_event(self):
        event = FileChunkUpdatedEvent.of("fc1", ["content_type"]).value
        assert isinstance(event, DomainEvent)
