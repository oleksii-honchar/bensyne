"""MemoryBank domain entity."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import ValidationError

from src.domain.result import ErrorWithDetails, Result
from src.domain.models.memory_bank_model import MemoryBankSchema


@dataclass(frozen=True)
class MemoryBank:
    """Memory bank entity representing a namespace."""

    name: str
    description: str
    status: str  # "active", "registered", "suspended"
    created_at: datetime
    last_accessed: Optional[datetime]
    memory_count: int

    @classmethod
    def of(cls, name: str, description: str) -> "Result[MemoryBank]":
        """Factory method for creating new memory bank."""
        if not name or not name.strip():
            return Result.ko(
                [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": name})]
            )
        if not description or not description.strip():
            return Result.ko(
                [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": name})]
            )
        try:
            MemoryBankSchema(name=name, description=description)
        except ValidationError:
            return Result.ko(
                [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": name})]
            )
        return Result.ok(
            cls(
                name=name,
                description=description,
                status="registered",
                created_at=datetime.now(),
                last_accessed=None,
                memory_count=0,
            )
        )

    def activate(self) -> "Result[MemoryBank]":
        """Activate the memory bank."""
        if self.status == "suspended":
            return Result.ko(
                [ErrorWithDetails("BANK_SUSPENDED", {"name": self.name})]
            )
        return Result.ok(
            self.replace(status="active", last_accessed=datetime.now())
        )

    def suspend(self) -> "Result[MemoryBank]":
        """Suspend the memory bank."""
        return Result.ok(self.replace(status="suspended"))

    def increment_memory_count(self) -> "MemoryBank":
        """Increment memory count."""
        return self.replace(memory_count=self.memory_count + 1)

    def decrement_memory_count(self) -> "MemoryBank":
        """Decrement memory count with floor at 0."""
        return self.replace(memory_count=max(0, self.memory_count - 1))

    def replace(self, **kwargs) -> "MemoryBank":
        """Create new instance with updated fields."""
        return self.__class__(**{**self.__dict__, **kwargs})
