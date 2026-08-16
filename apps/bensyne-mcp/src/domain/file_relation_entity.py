"""FileRelation domain entity.

Tracks semantic relationships between files with a strength value
indicating the confidence in the relationship.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from src.domain.events.file_relation_events import (
    FileRelationCreatedEvent,
    FileRelationUpdatedEvent,
)
from src.utils.result import ErrorWithDetails, Result
from src.domain.models.file_relation_model import Direction, FileRelationSchema, RelationType


@dataclass(frozen=True)
class FileRelation:
    """FileRelation entity tracking semantic relationships between files."""

    id: str
    source_file_id: str
    target_file_id: str
    relation_type: RelationType
    strength: float
    direction: Direction
    description: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, properties: dict) -> "Result[FileRelation]":
        """Factory method with Pydantic validation."""
        try:
            validated = FileRelationSchema(**properties)
            rel = cls(
                id=validated.id,
                source_file_id=validated.source_file_id,
                target_file_id=validated.target_file_id,
                relation_type=validated.relation_type,
                strength=validated.strength,
                direction=validated.direction,
                description=validated.description,
                created_at=validated.created_at,
                updated_at=validated.updated_at,
            )
            event = FileRelationCreatedEvent.of(
                validated.id,
                validated.source_file_id,
                validated.target_file_id,
            )
            if event.is_ko:
                return Result.ko(event.errors)
            return Result.ok(rel, events=[event.value])
        except ValidationError as e:
            return Result.ko([ErrorWithDetails("INVALID_FILE_RELATION", e.errors())])

    def update_strength(self, strength: float) -> "Result[FileRelation]":
        """Update the relation strength.

        Returns Result.ko if strength is outside [0.0, 1.0].
        Emits FileRelationUpdatedEvent on success.
        """
        if strength < 0.0 or strength > 1.0:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "INVALID_STRENGTH",
                        {
                            "given": strength,
                            "min": 0.0,
                            "max": 1.0,
                        },
                    )
                ]
            )

        if strength == self.strength:
            return Result.ok(self)

        updated = self._replace(strength=strength)
        event = FileRelationUpdatedEvent.of(self.id, changed_fields=["strength"])
        if event.is_ko:
            return Result.ko(event.errors)
        return Result.ok(updated, events=[event.value])

    def update_description(self, description: str | None) -> "Result[FileRelation]":
        """Update the relation description.

        Emits FileRelationUpdatedEvent on success.
        """
        if description == self.description:
            return Result.ok(self)

        updated = self._replace(description=description)
        event = FileRelationUpdatedEvent.of(self.id, changed_fields=["description"])
        if event.is_ko:
            return Result.ko(event.errors)
        return Result.ok(updated, events=[event.value])

    def _replace(self, **changes: object) -> "FileRelation":
        """Create a new FileRelation instance with updated fields (preserves immutability)."""
        return FileRelation(
            id=self.id,
            source_file_id=changes.get("source_file_id", self.source_file_id),
            target_file_id=changes.get("target_file_id", self.target_file_id),
            relation_type=changes.get("relation_type", self.relation_type),
            strength=changes.get("strength", self.strength),
            direction=changes.get("direction", self.direction),
            description=changes.get("description", self.description),
            created_at=changes.get("created_at", self.created_at),
            updated_at=changes.get("updated_at", datetime.now()),
        )
