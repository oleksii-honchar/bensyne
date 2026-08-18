"""File domain entity."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from src.domain.events.file_events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileIndexCompletedEvent,
    FileUpdatedEvent,
)
from src.utils.result import ErrorWithDetails, Result
from src.domain.models.file_model import FileRole, FileSchema, FileStatus, SourceType


@dataclass(frozen=True)
class File:
    """File entity representing a tracked source file with metadata."""

    id: str
    path: str
    source_type: SourceType
    file_role: FileRole | None
    hash: str | None
    file_type: str | None
    size: int | None
    language: str | None
    aggregated_keywords: list[str]
    aggregated_tags: list[str]
    status: FileStatus
    summary: str | None
    total_chunks: int
    average_importance: float
    metadata: dict[str, str]
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
                    file_role=validated.file_role,
                    hash=validated.hash,
                    file_type=validated.file_type,
                    size=validated.size,
                    language=validated.language,
                    aggregated_keywords=validated.aggregated_keywords,
                    aggregated_tags=validated.aggregated_tags,
                    status=validated.status,
                    summary=validated.summary,
                    total_chunks=validated.total_chunks,
                    average_importance=validated.average_importance,
                    metadata=dict(validated.metadata),
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

    def to_dict(self) -> dict:
        """Canonical plain file block for retrieval responses (D24.1, spec §7.1).

        Single source of the file block emitted by every retrieval site —
        searchFiles ``file``, fetchFile ``file``, recall
        ``file_enrichment.file`` and expandFileRelations ``source_file``.
        Key set = the legacy SearchFilesUseCase file block + ``file_hash``
        (D15 — the column exists and retrieval surfaces the hash).
        Timestamps and lifecycle fields are system-managed and not part of
        the block (D23).
        """
        return {
            "id": self.id,
            "path": self.path,
            "source_type": self.source_type.value,
            "file_role": self.file_role.value if self.file_role is not None else "",
            "total_chunks": self.total_chunks,
            "keywords": self.aggregated_keywords,
            "tags": self.aggregated_tags,
            "average_importance": self.average_importance,
            "metadata": dict(self.metadata),
            "file_hash": self.hash,
        }

    def mark_indexed(self) -> "Result[File]":
        """Transition file to INDEXED status.

        Returns Result.ko if already indexed. Emits FileIndexCompletedEvent on
        success. A DELETED file is resurrected to INDEXED (D21 / O1):
        re-materializing a forgotten file revives it, making forget ->
        re-remember a clean round-trip rather than a one-way door.
        """
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
        path: str | None = None,
        source_type: SourceType | None = None,
        file_role: FileRole | None = None,
        hash: str | None = None,
        file_type: str | None = None,
        size: int | None = None,
        language: str | None = None,
        aggregated_keywords: list[str] | None = None,
        aggregated_tags: list[str] | None = None,
        summary: str | None = None,
        total_chunks: int | None = None,
        average_importance: float | None = None,
        metadata: dict[str, str] | None = None,
    ) -> "Result[File]":
        """Update file metadata fields (partial — an omitted/None value is kept).

        The merged state is validated against the single source of truth, the
        Pydantic ``FileSchema`` (D23). Returns Result.ko if the file is
        deleted or the merged state fails validation (stored row unchanged).
        Emits FileUpdatedEvent on a real change.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        new_path = path if path is not None else self.path
        new_source_type = source_type if source_type is not None else self.source_type
        new_file_role = file_role if file_role is not None else self.file_role
        new_hash = hash if hash is not None else self.hash
        new_file_type = file_type if file_type is not None else self.file_type
        new_size = size if size is not None else self.size
        new_language = language if language is not None else self.language
        new_aggregated_keywords = (
            aggregated_keywords if aggregated_keywords is not None else self.aggregated_keywords
        )
        new_aggregated_tags = (
            aggregated_tags if aggregated_tags is not None else self.aggregated_tags
        )
        new_summary = summary if summary is not None else self.summary
        new_total_chunks = total_chunks if total_chunks is not None else self.total_chunks
        new_average_importance = (
            average_importance if average_importance is not None else self.average_importance
        )
        new_metadata = metadata if metadata is not None else self.metadata

        # Single runtime validation source (D23): validate the merged state via
        # the Pydantic FileSchema. Invalid ⇒ ko, stored row unchanged.
        try:
            FileSchema(
                id=self.id,
                path=new_path,
                source_type=new_source_type,
                file_role=new_file_role,
                hash=new_hash,
                file_type=new_file_type,
                size=new_size,
                language=new_language,
                aggregated_keywords=new_aggregated_keywords,
                aggregated_tags=new_aggregated_tags,
                status=self.status,
                summary=new_summary,
                total_chunks=new_total_chunks,
                average_importance=new_average_importance,
                metadata=new_metadata,
                created_at=self.created_at,
                updated_at=self.updated_at,
            )
        except ValidationError as e:
            return Result.ko([ErrorWithDetails("INVALID_FILE", e.errors())])

        changed = []
        if new_path != self.path:
            changed.append("path")
        if new_source_type != self.source_type:
            changed.append("source_type")
        if new_file_role != self.file_role:
            changed.append("file_role")
        if new_hash != self.hash:
            changed.append("hash")
        if new_file_type != self.file_type:
            changed.append("file_type")
        if new_size != self.size:
            changed.append("size")
        if new_language != self.language:
            changed.append("language")
        if new_aggregated_keywords != self.aggregated_keywords:
            changed.append("aggregated_keywords")
        if new_aggregated_tags != self.aggregated_tags:
            changed.append("aggregated_tags")
        if new_summary != self.summary:
            changed.append("summary")
        if new_total_chunks != self.total_chunks:
            changed.append("total_chunks")
        if new_average_importance != self.average_importance:
            changed.append("average_importance")
        if new_metadata != self.metadata:
            changed.append("metadata")

        if not changed:
            return Result.ok(self)

        updated = self._replace(
            path=new_path,
            source_type=new_source_type,
            file_role=new_file_role,
            hash=new_hash,
            file_type=new_file_type,
            size=new_size,
            language=new_language,
            aggregated_keywords=new_aggregated_keywords,
            aggregated_tags=new_aggregated_tags,
            summary=new_summary,
            total_chunks=new_total_chunks,
            average_importance=new_average_importance,
            metadata=dict(new_metadata),
        )
        event = FileUpdatedEvent.of(self.id, changed_fields=changed)
        return Result.ok(updated, events=[event.value])

    def add_keywords(self, keywords: list[str]) -> "Result[File]":
        """Append keywords to aggregated_keywords.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        new_keywords = self.aggregated_keywords + keywords
        updated = self._replace(aggregated_keywords=new_keywords)
        event = FileUpdatedEvent.of(self.id, changed_fields=["aggregated_keywords"])
        return Result.ok(updated, events=[event.value])

    def add_tags(self, tags: list[str]) -> "Result[File]":
        """Append tags to aggregated_tags.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        new_tags = self.aggregated_tags + tags
        updated = self._replace(aggregated_tags=new_tags)
        event = FileUpdatedEvent.of(self.id, changed_fields=["aggregated_tags"])
        return Result.ok(updated, events=[event.value])

    def merge_tags(self, tags: list[str]) -> "Result[File]":
        """Union-merge tags into aggregated_tags, order-preserving (O5).

        Returns Result.ok(self) — zero events — when the union is identical
        to the current tag list (idempotent re-materialization is silent).
        Returns Result.ko if the file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        # Order-preserving set-union: keep existing order, append new tags.
        seen = set(self.aggregated_tags)
        merged = list(self.aggregated_tags)
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                merged.append(tag)

        if merged == self.aggregated_tags:
            return Result.ok(self)

        updated = self._replace(aggregated_tags=merged)
        event = FileUpdatedEvent.of(self.id, changed_fields=["aggregated_tags"])
        return Result.ok(updated, events=[event.value])

    def with_chunk(
        self,
        importance: float = 0.5,
        tags: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> "Result[File]":
        """Update file metadata when a chunk is added.

        Increments chunk count and aggregates keywords/tags from the chunk.

        Returns Result.ko if file is deleted.
        """
        if self._is_deleted():
            return Result.ko([ErrorWithDetails("FILE_DELETED", {"id": self.id})])

        changed: list[str] = []
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
            path=changes.get("path", self.path),  # type: ignore[arg-type]
            source_type=changes.get("source_type", self.source_type),  # type: ignore[arg-type]
            file_role=changes.get("file_role", self.file_role),  # type: ignore[arg-type]
            hash=changes.get("hash", self.hash),  # type: ignore[arg-type]
            file_type=changes.get("file_type", self.file_type),  # type: ignore[arg-type]
            size=changes.get("size", self.size),  # type: ignore[arg-type]
            language=changes.get("language", self.language),  # type: ignore[arg-type]
            aggregated_keywords=changes.get("aggregated_keywords", self.aggregated_keywords),  # type: ignore[arg-type]
            aggregated_tags=changes.get("aggregated_tags", self.aggregated_tags),  # type: ignore[arg-type]
            status=changes.get("status", self.status),  # type: ignore[arg-type]
            summary=changes.get("summary", self.summary),  # type: ignore[arg-type]
            total_chunks=changes.get("total_chunks", self.total_chunks),  # type: ignore[arg-type]
            average_importance=changes.get("average_importance", self.average_importance),  # type: ignore[arg-type]
            metadata=changes.get("metadata", self.metadata),  # type: ignore[arg-type]
            created_at=changes.get("created_at", self.created_at),  # type: ignore[arg-type]
            updated_at=changes.get("updated_at", datetime.now()),
        )
