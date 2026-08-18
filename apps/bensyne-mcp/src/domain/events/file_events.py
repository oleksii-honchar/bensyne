"""Concrete domain events for file operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime
from src.utils.result import DomainEvent, ErrorWithDetails, Result


@dataclass(frozen=True)
class FileCreatedEvent(DomainEvent):
    """Emitted when a new file is created in the system."""

    file_id: str
    path: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str, path: str) -> Result["FileCreatedEvent"]:
        if not file_id or not path:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_CREATED_EVENT",
                        {
                            "file_id": file_id,
                            "path": path,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id, path=path))

    @property
    def event_type(self) -> str:
        return "file.created"

    def get_name(self) -> str:
        return "file.created"


@dataclass(frozen=True)
class FileUpdatedEvent(DomainEvent):
    """Emitted when a file is updated."""

    file_id: str
    changed_fields: list[str]
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str, changed_fields: list[str]) -> Result["FileUpdatedEvent"]:
        if not file_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_UPDATED_EVENT",
                        {
                            "file_id": file_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id, changed_fields=changed_fields))

    @property
    def event_type(self) -> str:
        return "file.updated"

    def get_name(self) -> str:
        return "file.updated"


@dataclass(frozen=True)
class FileDeletedEvent(DomainEvent):
    """Emitted when a file is deleted."""

    file_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str) -> Result["FileDeletedEvent"]:
        if not file_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_DELETED_EVENT",
                        {
                            "file_id": file_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id))

    @property
    def event_type(self) -> str:
        return "file.deleted"

    def get_name(self) -> str:
        return "file.deleted"


@dataclass(frozen=True)
class FileIndexCompletedEvent(DomainEvent):
    """Emitted when file indexing is completed."""

    file_id: str
    chunk_count: int
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str, chunk_count: int) -> Result["FileIndexCompletedEvent"]:
        if not file_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_INDEX_COMPLETED_EVENT",
                        {
                            "file_id": file_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id, chunk_count=chunk_count))

    @property
    def event_type(self) -> str:
        return "file.index_completed"

    def get_name(self) -> str:
        return "file.index_completed"


@dataclass(frozen=True)
class FileChunkRemovedEvent(DomainEvent):
    """Emitted when a chunk is removed from a file aggregate."""

    file_id: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str, memory_id: str) -> Result["FileChunkRemovedEvent"]:
        if not file_id or not memory_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_CHUNK_REMOVED_EVENT",
                        {
                            "file_id": file_id,
                            "memory_id": memory_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "file.chunk_removed"

    def get_name(self) -> str:
        return "file.chunk_removed"


@dataclass(frozen=True)
class FileContentComposedEvent(DomainEvent):
    """Emitted when file content is composed from chunks."""

    file_id: str
    chunks_composed: int
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, file_id: str, chunks_composed: int) -> Result["FileContentComposedEvent"]:
        if not file_id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_FILE_CONTENT_COMPOSED_EVENT",
                        {
                            "file_id": file_id,
                        },
                    )
                ]
            )
        return Result.ok(cls(file_id=file_id, chunks_composed=chunks_composed))

    @property
    def event_type(self) -> str:
        return "file.content_composed"

    def get_name(self) -> str:
        return "file.content_composed"
