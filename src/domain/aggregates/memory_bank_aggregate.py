"""MemoryBankAggregate — aggregate root orchestrating MemoryBank and Memory entities."""

from dataclasses import dataclass
from typing import List, Optional

from src.domain.entities.memory import Memory
from src.domain.entities.memory_bank import MemoryBank
from src.domain.events.memory_events import (
    MemoryBankActivatedEvent,
    MemoryBankSuspendedEvent,
    MemoryCreatedEvent,
    MemoryDeletedEvent,
)
from src.domain.result import ErrorWithDetails, Result


@dataclass(frozen=True)
class MemoryBankAggregate:
    """Aggregate root for a memory bank and its memories.

    Enforces domain invariants (e.g. bank must be active to remember) and
    produces domain events via Result.events.
    """

    bank: MemoryBank
    memories: List[Memory]

    @classmethod
    def of(
        cls,
        bank: MemoryBank,
        memories: Optional[List[Memory]] = None,
    ) -> Result["MemoryBankAggregate"]:
        """Factory method returning Result[MemoryBankAggregate]."""
        return Result.ok(cls(bank=bank, memories=memories or []))

    def remember(self, memory: Memory) -> Result["MemoryBankAggregate"]:
        """Add a memory to this bank.

        Rejects if the bank is not active. On success produces a
        MemoryCreatedEvent and increments the bank's memory count.
        """
        if self.bank.status != "active":
            return Result.ko([ErrorWithDetails("BANK_NOT_ACTIVE", {"name": self.bank.name})])

        event = MemoryCreatedEvent.of(
            bank_name=self.bank.name,
            memory_id=memory.id,
        )
        # Event factory validation — propagate ko if event creation fails
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.__class__(
                bank=self.bank.increment_memory_count(),
                memories=[*self.memories, memory],
            ),
            events=[event.value],
        )

    def forget(self, memory_id: str) -> Result["MemoryBankAggregate"]:
        """Remove a memory by id.

        Rejects if the memory is not found. On success produces a
        MemoryDeletedEvent and decrements the bank's memory count.
        """
        memory = next((m for m in self.memories if m.id == memory_id), None)
        if not memory:
            return Result.ko([ErrorWithDetails("MEMORY_NOT_FOUND", {"id": memory_id})])

        event = MemoryDeletedEvent.of(
            bank_name=self.bank.name,
            memory_id=memory.id,
        )
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.__class__(
                bank=self.bank.decrement_memory_count(),
                memories=[m for m in self.memories if m.id != memory_id],
            ),
            events=[event.value],
        )

    def activate(self) -> Result["MemoryBankAggregate"]:
        """Activate the bank.

        Delegates to MemoryBank.activate(); on success produces a
        MemoryBankActivatedEvent.
        """
        bank_result = self.bank.activate()
        if not bank_result.is_ok:
            return bank_result  # type: ignore[return-value]

        event = MemoryBankActivatedEvent.of(bank_name=bank_result.value.name)
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.__class__(bank=bank_result.value, memories=self.memories),
            events=[event.value],
        )

    def suspend(self) -> Result["MemoryBankAggregate"]:
        """Suspend the bank.

        Delegates to MemoryBank.suspend(); on success produces a
        MemoryBankSuspendedEvent.
        """
        bank_result = self.bank.suspend()
        if not bank_result.is_ok:
            return bank_result  # type: ignore[return-value]

        event = MemoryBankSuspendedEvent.of(bank_name=bank_result.value.name)
        if event.is_ko:
            return event  # type: ignore[return-value]

        return Result.ok(
            self.__class__(bank=bank_result.value, memories=self.memories),
            events=[event.value],
        )
