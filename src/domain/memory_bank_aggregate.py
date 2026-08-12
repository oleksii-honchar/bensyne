"""MemoryBank — aggregate root for memory bank and its memories.

Combines entity fields (name, description, status, timestamps, memory_count)
with aggregate membership (memories list). Enforces domain invariants
(e.g. bank must be active to remember) and produces domain events via
Result.events.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from src.domain.events.memory_bank_events import (
    MemoryBankActivatedEvent,
    MemoryBankSuspendedEvent,
)
from src.domain.events.memory_events import (
    MemoryRememberedEvent,
    MemoryForgottenEvent,
)
from src.domain.memory_entity import Memory
from src.domain.models.memory_bank_model import MemoryBankSchema
from src.utils.result import ErrorWithDetails, Result


@dataclass(frozen=True)
class MemoryBank:
    """Memory bank aggregate — orchestrates bank lifecycle and its memories."""

    name: str
    description: str
    status: str  # "active", "registered", "suspended"
    created_at: datetime
    last_accessed: datetime | None
    memory_count: int
    memories: list[Memory]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def of(cls, name: str, description: str) -> Result["MemoryBank"]:
        """Factory method for creating a new memory bank."""
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
                memories=[],
            )
        )

    # ------------------------------------------------------------------
    # Entity lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> Result["MemoryBank"]:
        """Activate the memory bank.

        Emits MemoryBankActivatedEvent on success.
        """
        if self.status == "suspended":
            return Result.ko(
                [ErrorWithDetails("BANK_SUSPENDED", {"name": self.name})]
            )

        updated = self.replace(status="active", last_accessed=datetime.now())
        event = MemoryBankActivatedEvent.of(bank_name=updated.name)
        if event.is_ko:
            return event

        return Result.ok(updated, events=[event.value])

    def suspend(self) -> Result["MemoryBank"]:
        """Suspend the memory bank.

        Emits MemoryBankSuspendedEvent on success.
        """
        updated = self.replace(status="suspended")
        event = MemoryBankSuspendedEvent.of(bank_name=updated.name)
        if event.is_ko:
            return event

        return Result.ok(updated, events=[event.value])

    # ------------------------------------------------------------------
    # Memory count
    # ------------------------------------------------------------------

    def increment_memory_count(self) -> "MemoryBank":
        """Increment the memory count by one."""
        return self.replace(memory_count=self.memory_count + 1)

    def decrement_memory_count(self) -> "MemoryBank":
        """Decrement the memory count by one, floored at zero."""
        return self.replace(memory_count=max(0, self.memory_count - 1))

    # ------------------------------------------------------------------
    # Aggregate membership
    # ------------------------------------------------------------------

    def remember(self, memory: Memory) -> Result["MemoryBank"]:
        """Add a memory to this bank.

        Rejects if the bank is not active. On success produces a
        MemoryRememberedEvent and increments the bank's memory count.
        """
        if self.status != "active":
            return Result.ko([ErrorWithDetails("BANK_NOT_ACTIVE", {"name": self.name})])

        event = MemoryRememberedEvent.of(
            bank_name=self.name,
            memory_id=memory.id,
        )
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.replace(
                memory_count=self.memory_count + 1,
                memories=[*self.memories, memory],
            ),
            events=[event.value],
        )

    def forget(self, memory_id: str) -> Result["MemoryBank"]:
        """Remove a memory by id.

        Rejects if the memory is not found. On success produces a
        MemoryForgottenEvent and decrements the bank's memory count.
        """
        memory = next((m for m in self.memories if m.id == memory_id), None)
        if not memory:
            return Result.ko([ErrorWithDetails("MEMORY_NOT_FOUND", {"id": memory_id})])

        event = MemoryForgottenEvent.of(
            bank_name=self.name,
            memory_id=memory.id,
        )
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.replace(
                memory_count=max(0, self.memory_count - 1),
                memories=[m for m in self.memories if m.id != memory_id],
            ),
            events=[event.value],
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def replace(self, **kwargs) -> "MemoryBank":
        """Create new instance with updated fields (preserves immutability)."""
        return self.__class__(**{**self.__dict__, **kwargs})
