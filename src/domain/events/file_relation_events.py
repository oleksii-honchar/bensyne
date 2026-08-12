"""Concrete domain events for file relation operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from src.utils.result import DomainEvent, ErrorWithDetails, Result


@dataclass(frozen=True)
class FileRelationCreatedEvent(DomainEvent):
    """Emitted when a new file relation is created."""

    relation_id: str
    source_file_id: str
    target_file_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(
        cls,
        relation_id: str,
        source_file_id: str,
        target_file_id: str,
    ) -> Result["FileRelationCreatedEvent"]:
        if not relation_id or not source_file_id or not target_file_id:
            return Result.ko([ErrorWithDetails("INVALID_FILE_RELATION_CREATED_EVENT", {
                "relation_id": relation_id,
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
            })])
        return Result.ok(cls(relation_id=relation_id, source_file_id=source_file_id, target_file_id=target_file_id))

    @property
    def event_type(self) -> str:
        return "file_relation.created"

    def get_name(self) -> str:
        return "file_relation.created"


@dataclass(frozen=True)
class FileRelationUpdatedEvent(DomainEvent):
    """Emitted when a file relation is updated."""

    relation_id: str
    changed_fields: List[str]
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, relation_id: str, changed_fields: List[str]) -> Result["FileRelationUpdatedEvent"]:
        if not relation_id:
            return Result.ko([ErrorWithDetails("INVALID_FILE_RELATION_UPDATED_EVENT", {
                "relation_id": relation_id,
            })])
        return Result.ok(cls(relation_id=relation_id, changed_fields=changed_fields))

    @property
    def event_type(self) -> str:
        return "file_relation.updated"

    def get_name(self) -> str:
        return "file_relation.updated"
