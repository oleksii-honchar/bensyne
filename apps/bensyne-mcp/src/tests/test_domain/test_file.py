"""Unit tests for File domain entity, enums, and domain events."""

from datetime import datetime
from typing import List

import pytest

from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.models.file_model import FileRole
from src.domain.events.file_events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileIndexCompletedEvent,
    FileUpdatedEvent,
)
from src.utils.result import DomainEvent, ErrorWithDetails, Result

VALID_HASH = "a" * 64


class TestFileOfValidData:
    """File.of accepts valid data and returns Result.ok."""

    def test_of_returns_ok_with_minimal_required_fields(self):
        result = File.of(
            {
                "id": "f1",
                "path": "/tmp/test.txt",
                "source_type": SourceType.VAULT,
            }
        )
        assert result.is_ok is True
        file = result.value
        assert file.id == "f1"
        assert file.path == "/tmp/test.txt"
        assert file.source_type == SourceType.VAULT
        assert file.hash is None
        assert file.file_type is None
        assert file.size is None
        assert file.language is None
        assert file.aggregated_keywords == []
        assert file.aggregated_tags == []
        assert file.status == FileStatus.PENDING
        assert file.total_chunks == 0
        assert file.average_importance == 0.5
        assert file.metadata == {}
        assert file.created_at is not None
        assert file.updated_at is not None

    def test_of_returns_ok_with_new_fields(self):
        result = File.of(
            {
                "id": "f_new",
                "path": "/tmp/new.txt",
                "source_type": SourceType.VAULT,
                "total_chunks": 12,
                "average_importance": 0.75,
                "metadata": {"session_id": "s1", "note": "hello"},
            }
        )
        assert result.is_ok is True
        file = result.value
        assert file.total_chunks == 12
        assert file.average_importance == 0.75
        assert file.metadata == {"session_id": "s1", "note": "hello"}

    def test_of_rejects_negative_total_chunks(self):
        result = File.of(
            {
                "id": "f_neg",
                "path": "/tmp/neg.txt",
                "source_type": SourceType.VAULT,
                "total_chunks": -1,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_out_of_range_average_importance(self):
        for bad in (0.0, 1.5):
            result = File.of(
                {
                    "id": "f_oi",
                    "path": "/tmp/oi.txt",
                    "source_type": SourceType.VAULT,
                    "average_importance": bad,
                }
            )
            assert result.is_ko is True

    def test_of_rejects_non_string_metadata_values(self):
        result = File.of(
            {
                "id": "f_md",
                "path": "/tmp/md.txt",
                "source_type": SourceType.VAULT,
                "metadata": {"count": 3},
            }
        )
        assert result.is_ko is True

    def test_of_returns_ok_with_all_fields(self):
        now = datetime.now()
        result = File.of(
            {
                "id": "f2",
                "path": "/home/user/script.py",
                "source_type": SourceType.AGENT_SESSIONS,
                "hash": VALID_HASH,
                "file_type": "python",
                "size": 1024,
                "language": "python",
                "aggregated_keywords": ["domain", "entity"],
                "aggregated_tags": ["core"],
                "status": FileStatus.INDEXED,
                "created_at": now,
                "updated_at": now,
            }
        )
        assert result.is_ok is True
        file = result.value
        assert file.id == "f2"
        assert file.path == "/home/user/script.py"
        assert file.source_type == SourceType.AGENT_SESSIONS
        assert file.hash == VALID_HASH
        assert file.file_type == "python"
        assert file.size == 1024
        assert file.language == "python"
        assert file.aggregated_keywords == ["domain", "entity"]
        assert file.aggregated_tags == ["core"]
        assert file.status == FileStatus.INDEXED
        assert file.created_at == now
        assert file.updated_at == now

    def test_of_sets_timestamps_when_not_provided(self):
        result = File.of(
            {
                "id": "f3",
                "path": "/tmp/auto.txt",
                "source_type": SourceType.UNKNOWN,
            }
        )
        assert result.is_ok is True
        file = result.value
        assert isinstance(file.created_at, datetime)
        assert isinstance(file.updated_at, datetime)

    def test_of_returns_frozen_instance(self):
        result = File.of(
            {
                "id": "f4",
                "path": "/tmp/frozen.txt",
                "source_type": SourceType.UNKNOWN,
            }
        )
        assert result.is_ok is True
        file = result.value
        with pytest.raises(Exception):
            file.path = "/tmp/mutated.txt"  # type: ignore

    def test_of_accepts_all_source_types(self):
        for st in SourceType:
            result = File.of(
                {
                    "id": f"f_st_{st.value}",
                    "path": "/tmp/test.txt",
                    "source_type": st,
                }
            )
            assert result.is_ok is True
            assert result.value.source_type == st

    def test_of_accepts_all_statuses(self):
        for status in FileStatus:
            result = File.of(
                {
                    "id": f"f_st_{status.value}",
                    "path": "/tmp/test.txt",
                    "source_type": SourceType.UNKNOWN,
                    "status": status,
                }
            )
            assert result.is_ok is True
            assert result.value.status == status

    def test_of_with_zero_size(self):
        result = File.of(
            {
                "id": "f5",
                "path": "/tmp/empty.txt",
                "source_type": SourceType.VAULT,
                "size": 0,
            }
        )
        assert result.is_ok is True
        assert result.value.size == 0

    def test_of_with_none_size(self):
        result = File.of(
            {
                "id": "f6",
                "path": "/tmp/unknown.txt",
                "source_type": SourceType.VAULT,
                "size": None,
            }
        )
        assert result.is_ok is True
        assert result.value.size is None


class TestFileOfRejectsInvalidData:
    """File.of rejects invalid data and returns Result.ko."""

    def test_of_rejects_empty_path(self):
        result = File.of(
            {
                "id": "f7",
                "path": "",
                "source_type": SourceType.UNKNOWN,
            }
        )
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_FILE"

    def test_of_rejects_missing_path(self):
        result = File.of(
            {
                "id": "f8",
                "source_type": SourceType.UNKNOWN,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_negative_size(self):
        result = File.of(
            {
                "id": "f9",
                "path": "/tmp/test.txt",
                "source_type": SourceType.UNKNOWN,
                "size": -1,
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE"

    def test_of_rejects_invalid_status(self):
        result = File.of(
            {
                "id": "f10",
                "path": "/tmp/test.txt",
                "source_type": SourceType.UNKNOWN,
                "status": "INVALID_STATUS",
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE"

    def test_of_rejects_invalid_hash(self):
        result = File.of(
            {
                "id": "f11",
                "path": "/tmp/test.txt",
                "source_type": SourceType.UNKNOWN,
                "hash": "not-a-valid-hash",
            }
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE"

    def test_of_rejects_missing_id(self):
        result = File.of(
            {
                "path": "/tmp/test.txt",
                "source_type": SourceType.UNKNOWN,
            }
        )
        assert result.is_ko is True

    def test_of_rejects_missing_source_type(self):
        result = File.of(
            {
                "id": "f12",
                "path": "/tmp/test.txt",
            }
        )
        assert result.is_ko is True


class TestFileStatusTransitions:
    """File status transition methods with event emission."""

    def _make_file(self, status: FileStatus = FileStatus.PENDING) -> File:
        return File.of(
            {
                "id": "f_trans",
                "path": "/tmp/transition.txt",
                "source_type": SourceType.VAULT,
                "status": status,
            }
        ).value

    # --- mark_indexed ---

    def test_mark_indexed_from_pending(self):
        file = self._make_file(FileStatus.PENDING)
        result = file.mark_indexed()
        assert result.is_ok is True
        updated = result.value
        assert updated.status == FileStatus.INDEXED
        assert updated.updated_at is not None
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert isinstance(events[0], FileIndexCompletedEvent)

    def test_mark_indexed_from_archived(self):
        file = self._make_file(FileStatus.ARCHIVED)
        result = file.mark_indexed()
        assert result.is_ok is True
        assert result.value.status == FileStatus.INDEXED

    def test_mark_indexed_when_already_indexed(self):
        file = self._make_file(FileStatus.INDEXED)
        result = file.mark_indexed()
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ALREADY_INDEXED"

    def test_mark_indexed_from_deleted_resurrects(self):
        # D21 (O1): re-materializing a DELETED file revives it — mark_indexed
        # resurrects DELETED -> INDEXED, making forget -> re-remember a clean
        # round-trip. Emits FileIndexCompletedEvent like any other transition.
        file = self._make_file(FileStatus.DELETED)
        result = file.mark_indexed()
        assert result.is_ok is True
        assert result.value.status == FileStatus.INDEXED
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileIndexCompletedEvent)

    # --- mark_archived ---

    def test_mark_archived_from_indexed(self):
        file = self._make_file(FileStatus.INDEXED)
        result = file.mark_archived()
        assert result.is_ok is True
        assert result.value.status == FileStatus.ARCHIVED
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileUpdatedEvent)

    def test_mark_archived_from_pending(self):
        file = self._make_file(FileStatus.PENDING)
        result = file.mark_archived()
        assert result.is_ok is True
        assert result.value.status == FileStatus.ARCHIVED

    def test_mark_archived_when_already_archived(self):
        file = self._make_file(FileStatus.ARCHIVED)
        result = file.mark_archived()
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ALREADY_ARCHIVED"

    def test_mark_archived_from_deleted_is_rejected(self):
        file = self._make_file(FileStatus.DELETED)
        result = file.mark_archived()
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_DELETED"

    # --- mark_deleted ---

    def test_mark_deleted_from_indexed(self):
        file = self._make_file(FileStatus.INDEXED)
        result = file.mark_deleted()
        assert result.is_ok is True
        assert result.value.status == FileStatus.DELETED
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileDeletedEvent)

    def test_mark_deleted_from_archived(self):
        file = self._make_file(FileStatus.ARCHIVED)
        result = file.mark_deleted()
        assert result.is_ok is True
        assert result.value.status == FileStatus.DELETED

    def test_mark_deleted_when_already_deleted(self):
        file = self._make_file(FileStatus.DELETED)
        result = file.mark_deleted()
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_ALREADY_DELETED"

    # --- update_metadata ---

    def test_update_metadata_updates_fields(self):
        file = self._make_file()
        result = file.update_metadata(
            hash=VALID_HASH,
            file_type="python",
            size=2048,
            language="python",
        )
        assert result.is_ok is True
        updated = result.value
        assert updated.hash == VALID_HASH
        assert updated.file_type == "python"
        assert updated.size == 2048
        assert updated.language == "python"
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileUpdatedEvent)

    def test_update_metadata_partial_update(self):
        file = self._make_file()
        result = file.update_metadata(hash=VALID_HASH)
        assert result.is_ok is True
        assert result.value.hash == VALID_HASH
        assert result.value.file_type is None
        assert result.value.size is None

    def test_update_metadata_on_deleted_file_is_rejected(self):
        file = self._make_file(FileStatus.DELETED)
        result = file.update_metadata(hash=VALID_HASH)
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_DELETED"

    def test_update_metadata_preserves_existing_fields(self):
        file = File.of(
            {
                "id": "f_preserve",
                "path": "/tmp/preserve.py",
                "source_type": SourceType.VAULT,
                "hash": VALID_HASH,
                "file_type": "python",
            }
        ).value
        result = file.update_metadata(size=512)
        assert result.is_ok is True
        assert result.value.hash == VALID_HASH
        assert result.value.file_type == "python"
        assert result.value.size == 512

    def test_update_metadata_new_fields(self):
        file = self._make_file()
        result = file.update_metadata(
            total_chunks=7,
            average_importance=0.9,
            metadata={"k": "v"},
        )
        assert result.is_ok is True
        updated = result.value
        assert updated.total_chunks == 7
        assert updated.average_importance == 0.9
        assert updated.metadata == {"k": "v"}
        assert result.has_events() is True
        changed = result.get_events()[0].changed_fields
        assert "total_chunks" in changed
        assert "average_importance" in changed
        assert "metadata" in changed

    def test_update_metadata_new_fields_partial_preserves_others(self):
        file = File.of(
            {
                "id": "f_part",
                "path": "/tmp/part.txt",
                "source_type": SourceType.VAULT,
                "total_chunks": 3,
                "average_importance": 0.2,
                "metadata": {"a": "1"},
            }
        ).value
        result = file.update_metadata(total_chunks=5)
        assert result.is_ok is True
        updated = result.value
        assert updated.total_chunks == 5
        assert updated.average_importance == 0.2
        assert updated.metadata == {"a": "1"}

    def test_update_metadata_no_change_returns_self_without_events(self):
        file = File.of(
            {
                "id": "f_same",
                "path": "/tmp/same.txt",
                "source_type": SourceType.VAULT,
                "total_chunks": 4,
                "average_importance": 0.5,
                "metadata": {"x": "y"},
            }
        ).value
        result = file.update_metadata(total_chunks=4, average_importance=0.5, metadata={"x": "y"})
        assert result.is_ok is True
        assert result.value is file
        assert result.has_events() is False

    # --- add_keywords ---

    def test_add_keywords_appends_to_aggregated(self):
        file = File.of(
            {
                "id": "f_kw",
                "path": "/tmp/keywords.txt",
                "source_type": SourceType.VAULT,
                "aggregated_keywords": ["existing"],
            }
        ).value
        result = file.add_keywords(["new1", "new2"])
        assert result.is_ok is True
        assert result.value.aggregated_keywords == ["existing", "new1", "new2"]

    def test_add_keywords_on_empty_aggregated(self):
        file = self._make_file()
        result = file.add_keywords(["first"])
        assert result.is_ok is True
        assert result.value.aggregated_keywords == ["first"]

    def test_add_keywords_on_deleted_file_is_rejected(self):
        file = self._make_file(FileStatus.DELETED)
        result = file.add_keywords(["kw"])
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_DELETED"

    # --- add_tags ---

    def test_add_tags_appends_to_aggregated(self):
        file = File.of(
            {
                "id": "f_tg",
                "path": "/tmp/tags.txt",
                "source_type": SourceType.VAULT,
                "aggregated_tags": ["existing"],
            }
        ).value
        result = file.add_tags(["new1"])
        assert result.is_ok is True
        assert result.value.aggregated_tags == ["existing", "new1"]

    def test_add_tags_on_deleted_file_is_rejected(self):
        file = self._make_file(FileStatus.DELETED)
        result = file.add_tags(["tg"])
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_DELETED"


class TestFileCreatedEvent:
    """FileCreatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileCreatedEvent.of(file_id="f1", path="/tmp/test.txt")
        assert result.is_ok is True
        event = result.value
        assert event.file_id == "f1"
        assert event.path == "/tmp/test.txt"

    def test_factory_rejects_empty_file_id(self):
        result = FileCreatedEvent.of(file_id="", path="/tmp/test.txt")
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_FILE_CREATED_EVENT"

    def test_factory_rejects_empty_path(self):
        result = FileCreatedEvent.of(file_id="f1", path="")
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_FILE_CREATED_EVENT"

    def test_event_type(self):
        event = FileCreatedEvent.of("f1", "/tmp/test.txt").value
        assert event.event_type == "file.created"

    def test_get_name(self):
        event = FileCreatedEvent.of("f1", "/tmp/test.txt").value
        assert event.get_name() == "file.created"

    def test_timestamp_is_datetime(self):
        event = FileCreatedEvent.of("f1", "/tmp/test.txt").value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        event = FileCreatedEvent.of("f1", "/tmp/test.txt").value
        assert isinstance(event, DomainEvent)


class TestFileUpdatedEvent:
    """FileUpdatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileUpdatedEvent.of(file_id="f1", changed_fields=["hash", "size"])
        assert result.is_ok is True
        event = result.value
        assert event.file_id == "f1"
        assert event.changed_fields == ["hash", "size"]

    def test_factory_rejects_empty_file_id(self):
        result = FileUpdatedEvent.of(file_id="", changed_fields=["hash"])
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_UPDATED_EVENT"

    def test_factory_accepts_empty_changed_fields(self):
        result = FileUpdatedEvent.of(file_id="f1", changed_fields=[])
        assert result.is_ok is True

    def test_event_type(self):
        event = FileUpdatedEvent.of("f1", ["hash"]).value
        assert event.event_type == "file.updated"

    def test_get_name(self):
        event = FileUpdatedEvent.of("f1", ["hash"]).value
        assert event.get_name() == "file.updated"

    def test_is_domain_event(self):
        event = FileUpdatedEvent.of("f1", ["hash"]).value
        assert isinstance(event, DomainEvent)


class TestFileDeletedEvent:
    """FileDeletedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileDeletedEvent.of(file_id="f1")
        assert result.is_ok is True
        event = result.value
        assert event.file_id == "f1"

    def test_factory_rejects_empty_file_id(self):
        result = FileDeletedEvent.of(file_id="")
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_DELETED_EVENT"

    def test_event_type(self):
        event = FileDeletedEvent.of("f1").value
        assert event.event_type == "file.deleted"

    def test_get_name(self):
        event = FileDeletedEvent.of("f1").value
        assert event.get_name() == "file.deleted"

    def test_is_domain_event(self):
        event = FileDeletedEvent.of("f1").value
        assert isinstance(event, DomainEvent)


class TestFileIndexCompletedEvent:
    """FileIndexCompletedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileIndexCompletedEvent.of(file_id="f1", chunk_count=5)
        assert result.is_ok is True
        event = result.value
        assert event.file_id == "f1"
        assert event.chunk_count == 5

    def test_factory_rejects_empty_file_id(self):
        result = FileIndexCompletedEvent.of(file_id="", chunk_count=5)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_INDEX_COMPLETED_EVENT"

    def test_event_type(self):
        event = FileIndexCompletedEvent.of("f1", 5).value
        assert event.event_type == "file.index_completed"

    def test_get_name(self):
        event = FileIndexCompletedEvent.of("f1", 5).value
        assert event.get_name() == "file.index_completed"

    def test_is_domain_event(self):
        event = FileIndexCompletedEvent.of("f1", 5).value
        assert isinstance(event, DomainEvent)

# ---------------------------------------------------------------------------
# to_dict() — canonical plain file block (D24.1, spec §7.1)
# ---------------------------------------------------------------------------

# The legacy SearchFilesUseCase file-block key set (pre-D24.1, L239–251) —
# the reference block per spec §7.1 / S9. The canonical block adds file_hash
# (D15).
LEGACY_SEARCH_FILE_KEYS = {
    "id",
    "path",
    "source_type",
    "file_role",
    "total_chunks",
    "keywords",
    "tags",
    "average_importance",
    "metadata",
}
CANONICAL_FILE_BLOCK_KEYS = LEGACY_SEARCH_FILE_KEYS | {"file_hash"}


class TestFileToDict:
    """File.to_dict() — single source of the retrieval file block (D24.1).

    Emitted verbatim by searchFiles `file`, fetchFile `file`, recall
    `file_enrichment.file`, and expandFileRelations `source_file`. Key set =
    the legacy SearchFilesUseCase block + `file_hash` (D15).
    """

    @staticmethod
    def _a_file(**overrides) -> File:
        base = {
            "id": "f1",
            "path": "/vault/notes/a.md",
            "source_type": SourceType.AGENT_SESSIONS,
            "file_role": FileRole.DOCS,
            "hash": "f" * 64,
            "file_type": "markdown",
            "size": 1234,
            "language": "en",
            "aggregated_keywords": ["kw1", "kw2"],
            "aggregated_tags": ["tag1"],
            "status": FileStatus.INDEXED,
            "summary": "A note",
            "total_chunks": 7,
            "average_importance": 0.82,
            "metadata": {"session.id": "sess_42"},
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
        }
        base.update(overrides)
        return File(**base)

    def test_key_set_is_legacy_search_keys_plus_file_hash(self):
        """Acceptance: key set = old search file-block keys + file_hash, exactly."""
        d = self._a_file().to_dict()
        assert set(d.keys()) == CANONICAL_FILE_BLOCK_KEYS

    def test_values_come_from_entity_fields(self):
        file = self._a_file()
        d = file.to_dict()
        assert d["id"] == "f1"
        assert d["path"] == "/vault/notes/a.md"
        assert d["source_type"] == SourceType.AGENT_SESSIONS.value
        assert d["file_role"] == FileRole.DOCS.value
        assert d["total_chunks"] == 7
        assert d["keywords"] == ["kw1", "kw2"]
        assert d["tags"] == ["tag1"]
        assert d["average_importance"] == 0.82
        assert d["metadata"] == {"session.id": "sess_42"}
        assert d["file_hash"] == "f" * 64

    def test_file_role_none_emits_empty_string(self):
        """Same convention as the legacy search block: None → ""."""
        d = self._a_file(file_role=None).to_dict()
        assert d["file_role"] == ""

    def test_file_hash_null_tolerant(self):
        """Legacy File row with NULL hash ⇒ file_hash is null, not an error."""
        d = self._a_file(hash=None).to_dict()
        assert d["file_hash"] is None

    def test_metadata_is_defensive_copy(self):
        file = self._a_file()
        d = file.to_dict()
        d["metadata"]["injected"] = "x"
        assert file.metadata == {"session.id": "sess_42"}

    def test_same_input_same_output(self):
        a = self._a_file().to_dict()
        b = self._a_file().to_dict()
        assert a == b
        assert a == self._a_file().to_dict()

    def test_excludes_timestamp_lifecycle_and_non_block_fields(self):
        """Canonical block boundary: no system-managed or out-of-scope fields
        (D23 — timestamps system-managed; block is the retrieval contract)."""
        d = self._a_file().to_dict()
        for key in (
            "created_at",
            "updated_at",
            "status",
            "summary",
            "file_type",
            "size",
            "language",
        ):
            assert key not in d
