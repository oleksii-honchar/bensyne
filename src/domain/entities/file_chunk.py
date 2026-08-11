"""FileChunk domain entity.

Links a File to a Memory with positional metadata so file content
can be reconstructed from ordered chunks.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import ValidationError

from src.domain.events.file_chunk_events import (
    FileChunkCreatedEvent,
    FileChunkUpdatedEvent,
)
from src.domain.result import ErrorWithDetails, Result
from src.domain.schemas.file_chunk_schema import ContentType, FileChunkSchema
from src.domain.value_objects.file_hash import FileHash


@dataclass(frozen=True)
class FileChunk:
    """FileChunk entity linking a File to a Memory with positional metadata."""

    id: str
    file_id: str
    memory_id: str
    chunk_index: int
    start_line: int
    end_line: int
    content_hash: Optional[str]
    content_type: ContentType
    is_partial: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, properties: dict) -> "Result[FileChunk]":
        """Factory method with Pydantic validation."""
        try:
            validated = FileChunkSchema(**properties)
            chunk = cls(
                id=validated.id,
                file_id=validated.file_id,
                memory_id=validated.memory_id,
                chunk_index=validated.chunk_index,
                start_line=validated.start_line,
                end_line=validated.end_line,
                content_hash=validated.content_hash,
                content_type=validated.content_type,
                is_partial=validated.is_partial,
                created_at=validated.created_at,
                updated_at=validated.updated_at,
            )
            event = FileChunkCreatedEvent.of(validated.id, validated.file_id, validated.memory_id)
            if event.is_ko:
                return Result.ko(event.errors)
            return Result.ok(chunk, events=[event.value])
        except ValidationError as e:
            return Result.ko([ErrorWithDetails("INVALID_FILE_CHUNK", e.errors())])

    def update_metadata(
        self,
        content_type: Optional[ContentType] = None,
        content_hash: Optional[str] = None,
        is_partial: Optional[bool] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> "Result[FileChunk]":
        """Update FileChunk metadata fields.

        Returns Result.ko if validation fails.
        Emits FileChunkUpdatedEvent on success.
        """
        # Validate content_type if provided
        if content_type is not None and not isinstance(content_type, ContentType):
            return Result.ko([ErrorWithDetails("INVALID_CONTENT_TYPE", {
                "given": content_type,
            })])

        # Validate content_hash if provided
        if content_hash is not None:
            result = FileHash.of(content_hash)
            if result.is_ko:
                return Result.ko([ErrorWithDetails("INVALID_CONTENT_HASH", result.errors[0].details)])

        # Validate line range if provided
        new_start = start_line if start_line is not None else self.start_line
        new_end = end_line if end_line is not None else self.end_line

        if start_line is not None and start_line < 0:
            return Result.ko([ErrorWithDetails("INVALID_LINE_RANGE", {
                "start_line": start_line,
                "reason": "must be >= 0",
            })])
        if end_line is not None and end_line < 0:
            return Result.ko([ErrorWithDetails("INVALID_LINE_RANGE", {
                "end_line": end_line,
                "reason": "must be >= 0",
            })])
        if new_end < new_start:
            return Result.ko([ErrorWithDetails("INVALID_LINE_RANGE", {
                "start_line": new_start,
                "end_line": new_end,
                "reason": "end_line must be >= start_line",
            })])

        changed = []
        new_content_type = content_type if content_type is not None else self.content_type
        new_content_hash = content_hash if content_hash is not None else self.content_hash
        new_is_partial = is_partial if is_partial is not None else self.is_partial

        if new_content_type != self.content_type:
            changed.append("content_type")
        if new_content_hash != self.content_hash:
            changed.append("content_hash")
        if new_is_partial != self.is_partial:
            changed.append("is_partial")
        if new_start != self.start_line:
            changed.append("start_line")
        if new_end != self.end_line:
            changed.append("end_line")

        if not changed:
            return Result.ok(self)

        updated = self._replace(
            content_type=new_content_type,
            content_hash=new_content_hash,
            is_partial=new_is_partial,
            start_line=new_start,
            end_line=new_end,
        )
        event = FileChunkUpdatedEvent.of(self.id, changed_fields=changed)
        if event.is_ko:
            return Result.ko(event.errors)
        return Result.ok(updated, events=[event.value])

    def _replace(self, **changes: object) -> "FileChunk":
        """Create a new FileChunk instance with updated fields (preserves immutability)."""
        return FileChunk(
            id=self.id,
            file_id=changes.get("file_id", self.file_id),
            memory_id=changes.get("memory_id", self.memory_id),
            chunk_index=changes.get("chunk_index", self.chunk_index),
            start_line=changes.get("start_line", self.start_line),
            end_line=changes.get("end_line", self.end_line),
            content_hash=changes.get("content_hash", self.content_hash),
            content_type=changes.get("content_type", self.content_type),
            is_partial=changes.get("is_partial", self.is_partial),
            created_at=changes.get("created_at", self.created_at),
            updated_at=changes.get("updated_at", datetime.now()),
        )
