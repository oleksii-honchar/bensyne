"""Memory domain entity."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from src.utils.result import ErrorWithDetails, Result
from src.domain.models.memory_model import MemorySchema


@dataclass(frozen=True)
class Memory:
    """Memory entity representing a durable memory in the system."""

    id: str
    content: str
    importance: float
    source: str
    scope: str
    created_at: datetime
    updated_at: datetime | None
    veracity: float | None
    metadata: dict | None

    @classmethod
    def of(cls, properties: dict) -> "Result[Memory]":
        """Factory method with Pydantic validation."""
        try:
            validated = MemorySchema(**properties)
            return Result.ok(
                cls(
                    id=validated.id,
                    content=validated.content,
                    importance=validated.importance,
                    source=validated.source,
                    scope=validated.scope,
                    created_at=validated.created_at,
                    updated_at=validated.updated_at,
                    veracity=validated.veracity,
                    metadata=validated.metadata,
                )
            )
        except ValidationError as e:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY", e.errors())])

    def update(
        self,
        content: str | None = None,
        importance: float | None = None,
        scope: str | None = None,
    ) -> "Result[Memory]":
        """Update memory with new content, importance, or scope."""
        properties = {
            "id": self.id,
            "content": content if content is not None else self.content,
            "importance": importance if importance is not None else self.importance,
            "source": self.source,
            "scope": scope if scope is not None else self.scope,
            "created_at": self.created_at,
            "updated_at": datetime.now(),
            "veracity": self.veracity,
            "metadata": self.metadata,
        }
        return Memory.of(properties)

    def suspend(self) -> "Result[Memory]":
        """Suspend the memory."""
        if self.scope == "suspended":
            return Result.ko(
                [
                    ErrorWithDetails(
                        "MEMORY_ALREADY_SUSPENDED",
                        {"id": self.id},
                    )
                ]
            )
        return self.update(scope="suspended")


class MemoryNotFoundError(Exception):
    """Domain exception for memory not found."""

    pass
