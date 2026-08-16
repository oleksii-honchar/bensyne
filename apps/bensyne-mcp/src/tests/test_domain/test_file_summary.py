"""Unit tests for File.summary field.

Verifies that the summary field is accepted, validated, persisted,
and flows through File.of(), _replace(), and aggregate operations.
"""

from datetime import datetime

import pytest

from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.events.file_events import FileUpdatedEvent
from src.utils.result import Result

VALID_HASH = "a" * 64
NOW = datetime(2026, 1, 1, 0, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_data(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    summary: str | None = None,
    status: FileStatus = FileStatus.PENDING,
) -> dict:
    data: dict = {
        "id": id,
        "path": path,
        "source_type": source_type,
        "status": status,
    }
    if summary is not None:
        data["summary"] = summary
    return data


# ===================================================================
# File.of() — summary field
# ===================================================================


class TestFileOfWithSummary:
    """File.of accepts and validates the summary field."""

    def test_of_accepts_summary(self):
        result = File.of(
            {
                **_file_data(summary="This file contains important config"),
            }
        )
        assert result.is_ok is True
        assert result.value.summary == "This file contains important config"

    def test_of_defaults_summary_to_none(self):
        result = File.of(_file_data())
        assert result.is_ok is True
        assert result.value.summary is None

    def test_of_accepts_empty_string_summary(self):
        result = File.of(
            {
                **_file_data(summary=""),
            }
        )
        assert result.is_ok is True
        assert result.value.summary == ""

    def test_of_preserves_summary_with_all_fields(self):
        result = File.of(
            {
                **_file_data(summary="A short summary"),
                "hash": VALID_HASH,
                "aggregated_keywords": ["config"],
                "aggregated_tags": ["core"],
            }
        )
        assert result.is_ok is True
        file = result.value
        assert file.summary == "A short summary"
        assert file.hash == VALID_HASH

    def test_of_emits_file_created_event_with_summary(self):
        result = File.of(
            {
                **_file_data(summary="New file summary"),
            }
        )
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert any(e.event_type == "file.created" for e in events)


# ===================================================================
# File immutability — summary preserved through _replace
# ===================================================================


class TestFileSummaryImmutability:
    """Summary is preserved across entity operations that use _replace()."""

    def test_mark_indexed_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.mark_indexed()
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_mark_archived_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.mark_archived()
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_mark_deleted_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.mark_deleted()
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_update_metadata_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.update_metadata(hash=VALID_HASH)
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"
        assert result.value.hash == VALID_HASH

    def test_add_keywords_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.add_keywords(["new_kw"])
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_add_tags_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.add_tags(["new_tag"])
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_with_chunk_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.with_chunk(keywords=["kw"])
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"

    def test_without_chunk_preserves_summary(self):
        file = File.of(
            {
                **_file_data(summary="Preserved summary"),
            }
        ).value
        result = file.without_chunk()
        assert result.is_ok is True
        assert result.value.summary == "Preserved summary"


# ===================================================================
# File frozen — summary cannot be mutated
# ===================================================================


class TestFileSummaryFrozen:
    """File is frozen; summary cannot be mutated after creation."""

    def test_summary_cannot_be_mutated(self):
        file = File.of(
            {
                **_file_data(summary="Original summary"),
            }
        ).value
        with pytest.raises(Exception):
            file.summary = "Mutated summary"  # type: ignore


# ===================================================================
# Aggregate — summary persists through aggregate operations
# ===================================================================


class TestFileSummaryInAggregate:
    """Summary persists through FileMetadataAggregate operations."""

    def test_aggregate_preserves_summary_on_add_chunk(self):
        from src.domain.file_metadata_aggregate import FileMetadataAggregate
        from src.domain.file_chunk_entity import FileChunk

        file = File.of(
            {
                **_file_data(summary="Aggregate summary"),
            }
        ).value
        agg = FileMetadataAggregate.of(file).value
        assert agg.file.summary == "Aggregate summary"

        # Adding a chunk should not affect summary
        chunk = FileChunk.of(
            {
                "id": "c1",
                "file_id": "f1",
                "memory_id": "mem_1",
                "chunk_index": 0,
            }
        ).value
        add_result = agg.add_chunk(chunk)
        assert add_result.is_ok is True
        assert add_result.value.file.summary == "Aggregate summary"

    def test_aggregate_preserves_summary_on_add_relation(self):
        from src.domain.file_metadata_aggregate import FileMetadataAggregate
        from src.domain.file_relation_entity import FileRelation, RelationType

        file = File.of(
            {
                **_file_data(summary="Aggregate summary"),
            }
        ).value
        agg = FileMetadataAggregate.of(file).value

        relation = FileRelation.of(
            {
                "id": "r1",
                "source_file_id": "f1",
                "target_file_id": "f2",
                "relation_type": RelationType.SIBLING,
            }
        ).value
        add_result = agg.add_relation(relation)
        assert add_result.is_ok is True
        assert add_result.value.file.summary == "Aggregate summary"
