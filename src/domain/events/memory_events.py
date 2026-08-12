"""Concrete domain events for memory operations.

Each event implements DomainEvent ABC and has a factory method of() that
returns Result, validating non-empty inputs.
"""

from dataclasses import dataclass
from datetime import datetime

from src.utils.result import DomainEvent, ErrorWithDetails, Result


@dataclass(frozen=True)
class MemoryRememberedEvent(DomainEvent):
    """Emitted when a memory is remembered (stored) in a memory bank."""

    bank_name: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str, memory_id: str) -> Result["MemoryRememberedEvent"]:
        if not bank_name or not memory_id:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_REMEMBERED_EVENT", {
                "bank_name": bank_name,
                "memory_id": memory_id,
            })])
        return Result.ok(cls(bank_name=bank_name, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "memory.remembered"

    def get_name(self) -> str:
        return "memory.remembered"


@dataclass(frozen=True)
class MemoryForgottenEvent(DomainEvent):
    """Emitted when a memory is forgotten (removed) from a memory bank."""

    bank_name: str
    memory_id: str
    timestamp: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now())

    @classmethod
    def of(cls, bank_name: str, memory_id: str) -> Result["MemoryForgottenEvent"]:
        if not bank_name or not memory_id:
            return Result.ko([ErrorWithDetails("INVALID_MEMORY_FORGOTTEN_EVENT", {
                "bank_name": bank_name,
                "memory_id": memory_id,
            })])
        return Result.ok(cls(bank_name=bank_name, memory_id=memory_id))

    @property
    def event_type(self) -> str:
        return "memory.forgotten"

    def get_name(self) -> str:
        return "memory.forgotten"
