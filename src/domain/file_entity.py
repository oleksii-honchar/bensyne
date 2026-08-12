"""File domain entity."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from pydantic import ValidationError

from src.domain.events.file_events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileIndexCompletedEvent,
    FileUpdatedEvent,
)
from src.utils.result import ErrorWithDetails, Result
from src.domain.models.file_model import FileSchema, FileStatus, SourceType


@dataclass(frozen=True)
class File:
    """File entity representing a tracked source file with metadata."""

    id: str
    path: str
    source_type: SourceType
    hash: Optional[str]
    file_type: Optional[str]
    size: Optional[int]
    language: Optional[str]
    aggregated_keywords: List[str]
    aggregated_tags: List[str]
    status: FileStatus
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, properties: dict) -> "Result[File]":
        """Factory method with Pydantic validation."""
        try:
            validated = FileSchema(**properties)
            return Result.ok(
                cls(
                    id=validated.id,
                    path=validated.path,
                    source_type=validated.source_type,
                    hash=validated.hash,
                    file_type=validated.file_type,
                    size=validated.size,
                    language=validated.language,
                    aggregated_keywords=validated.aggregated_keywords,
                    aggregated_tags=validated.aggregated_tags,
                    status=validated.status,
                    summary=validated.summary,
                    created_at=validated.created_at,
                    updated_at=validated.updated_at,
                ),
                events=[FileCreatedEvent.of(validated.id, validated.path).value],
            )
        except ValidationError as e:
            return Result.ko([ErrorWithDetails("INVALID_FILE", e.errors())])

    def _is_deleted(self) -> bool:
        """Check if file is in deleted state."""
        return self.status == FileStatus.DELETED

    def mark_indexed(self) -> "Result[File]":
        """Transition file to INDEXED status.

        Returns Result.ko if already indexed or deleted.
        Emits FileIndexCompletedEvent on success.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])
        if self.status == FileStatus.INDEXED:
            return Result.ko([ErrorWithDetails("FILE_ALREADY_INDEXED", {"id": self.id})])

        updated = self._replace(status=FileStatus.INDEXED)
        event = FileIndexCompletedEvent.of(self.id, chunk_count=0)
        return Result.ok(updated, events=[event.value])

    def mark_archived(self) -> "Result[File]":
        """Transition file to ARCHIVED status.

        Returns Result.ko if already archived or deleted.
        Emits FileUpdatedEvent on success.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])
        if self.status == FileStatus.ARCHIVED:
            return Result.ko([ErrorWithDetails("FILE_ALREADY_ARCHIVED", {"id": self.id})])

        updated = self._replace(status=FileStatus.ARCHIVED)
        event = FileUpdatedEvent.of(self.id, changed_fields=["status"])
        return Result.ok(updated, events=[event.value])

    def mark_deleted(self) -> "Result[File]":
        """Transition file to DELETED status.

        Returns Result.ko if already deleted.
        Emits FileDeletedEvent on success.
        """
        if self.status == FileStatus.DELETED:
            return Result.ko([ErrorWithDetails("FILE_ALREADY_DELETED", {"id": self.id})])

        updated = self._replace(status=FileStatus.DELETED)
        event = FileDeletedEvent.of(self.id)
        return Result.ok(updated, events=[event.value])

    def update_metadata(
        self,
        hash: Optional[str] = None,
        file_type: Optional[str] = None,
        size: Optional[int] = None,
        language: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> "Result[File]":
        """Update file metadata fields.

        Returns Result.ko if file is deleted or validation fails.
        Emits FileUpdatedEvent on success.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        changed = []
        new_hash = hash if hash is not None else self.hash
        new_file_type = file_type if file_type is not None else self.file_type
        new_size = size if size is not None else self.size
        new_language = language if language is not None else self.language
        new_summary = summary if summary is not None else self.summary

        if new_hash != self.hash:
            changed.append("hash")
        if new_file_type != self.file_type:
            changed.append("file_type")
        if new_size != self.size:
            changed.append("size")
        if new_language != self.language:
            changed.append("language")
        if new_summary != self.summary:
            changed.append("summary")

        if not changed:
            return Result.ok(self)

        updated = self._replace(
            hash=new_hash,
            file_type=new_file_type,
            size=new_size,
            language=new_language,
            summary=new_summary,
        )
        event = FileUpdatedEvent.of(self.id, changed_fields=changed)
        return Result.ok(updated, events=[event.value])

    def add_keywords(self, keywords: List[str]) -> "Result[File]":
        """Append keywords to aggregated_keywords.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        new_keywords = self.aggregated_keywords + keywords
        updated = self._replace(aggregated_keywords=new_keywords)
        event = FileUpdatedEvent.of(self.id, changed_fields=["aggregated_keywords"])
        return Result.ok(updated, events=[event.value])

    def add_tags(self, tags: List[str]) -> "Result[File]":
        """Append tags to aggregated_tags.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        new_tags = self.aggregated_tags + tags
        updated = self._replace(aggregated_tags=new_tags)
        event = FileUpdatedEvent.of(self.id, changed_fields=["aggregated_tags"])
        return Result.ok(updated, events=[event.value])

    def with_chunk(
        self,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> "Result[File]":
        """Update file metadata when a chunk is added.

        Increments chunk count and aggregates keywords/tags from the chunk.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        changed: List[str] = []
        new_keywords = self.aggregated_keywords
        new_tags = self.aggregated_tags

        if keywords:
            new_keywords = self.aggregated_keywords + keywords
            changed.append("aggregated_keywords")
        if tags:
            new_tags = self.aggregated_tags + tags
            changed.append("aggregated_tags")

        if not changed:
            updated = self._replace()
            return Result.ok(updated)

        updated = self._replace(
            aggregated_keywords=new_keywords,
            aggregated_tags=new_tags,
        )
        event = FileUpdatedEvent.of(self.id, changed_fields=changed)
        return Result.ok(updated, events=[event.value])

    def without_chunk(self, importance: float = 0.5) -> "Result[File]":
        """Update file metadata when a chunk is removed.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        updated = self._replace()
        event = FileUpdatedEvent.of(self.id, changed_fields=[])
        return Result.ok(updated, events=[event.value])

    def _replace(self, **changes: object) -> "File":
        """Create a new File instance with updated fields (preserves immutability)."""
        return File(
            id=self.id,
            path=changes.get("path", self.path),
            source_type=changes.get("source_type", self.source_type),
            hash=changes.get("hash", self.hash),
            file_type=changes.get("file_type", self.file_type),
            size=changes.get("size", self.size),
            language=changes.get("language", self.language),
            aggregated_keywords=changes.get("aggregated_keywords", self.aggregated_keywords),
            aggregated_tags=changes.get("aggregated_tags", self.aggregated_tags),
            status=changes.get("status", self.status),
            summary=changes.get("summary", self.summary),
            created_at=changes.get("created_at", self.created_at),
            updated_at=changes.get("updated_at", datetime.now()),
        )
