"""Concrete domain events for file chunk operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime
from src.utils.result import DomainEvent, ErrorWithDetails, Result


@dataclass(frozen=True)
class FileChunkCreatedEvent(DomainEvent):
    """Emitted when a new file chunk is created."""

    chunk_id: str
    file_id: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, chunk_id: str, file_id: str, memory_id: str) -> Result["FileChunkCreatedEvent"]:
        if not chunk_id or not file_id or not memory_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_CHUNK_CREATED_EVENT",
                        {
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "memory_id": memory_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(chunk_id=chunk_id, file_id=file_id, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "file_chunk.created"

    def get_name(self) -> str:
        return "file_chunk.created"


@dataclass(frozen=True)
class FileChunkUpdatedEvent(DomainEvent):
    """Emitted when a file chunk is updated."""

    chunk_id: str
    changed_fields: list[str]
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, chunk_id: str, changed_fields: list[str]) -> Result["FileChunkUpdatedEvent"]:
        if not chunk_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_CHUNK_UPDATED_EVENT",
                        {
                            "chunk_id": chunk_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(chunk_id=chunk_id, changed_fields=changed_fields))

    @property
    def event_type(self) -> str:
        return "file_chunk.updated"

    def get_name(self) -> str:
        return "file_chunk.updated"
