"""Domain test utilities — stub builders and fake repositories.

Provides aEntity() factories with valid defaults and partial overrides,
plus in-memory repository implementations for unit testing.
"""

from datetime import datetime
from typing import List, Optional

from src.domain.aggregates.memory_bank_aggregate import MemoryBankAggregate
from src.domain.entities.memory import Memory
from src.domain.entities.memory_bank import MemoryBank
from src.domain.interfaces import MemoryBankRepository, MemoryRepository
from src.domain.result import Result
from src.domain.value_objects.file_hash import FileHash


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------

def a_memory(
    id: str = "test_memory_id",
    content: str = "Test memory content",
    importance: float = 0.5,
    source: str = "conversation",
    scope: str = "working",
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    veracity: Optional[float] = None,
    metadata: Optional[dict] = None,
) -> Memory:
    """Create a valid Memory instance with sensible defaults.

    Accepts partial overrides via keyword arguments.
    """
    return Memory(
        id=id,
        content=content,
        importance=importance,
        source=source,
        scope=scope,
        created_at=created_at or datetime.now(),
        updated_at=updated_at,
        veracity=veracity,
        metadata=metadata,
    )


def a_memory_bank(
    name: str = "test_bank",
    description: str = "A test memory bank",
    status: str = "active",
    created_at: Optional[datetime] = None,
    last_accessed: Optional[datetime] = None,
    memory_count: int = 0,
) -> MemoryBank:
    """Create a valid MemoryBank instance with sensible defaults.

    Accepts partial overrides via keyword arguments.
    """
    return MemoryBank(
        name=name,
        description=description,
        status=status,
        created_at=created_at or datetime.now(),
        last_accessed=last_accessed,
        memory_count=memory_count,
    )


def a_memory_bank_aggregate(
    bank: Optional[MemoryBank] = None,
    memories: Optional[List[Memory]] = None,
) -> MemoryBankAggregate:
    """Create a valid MemoryBankAggregate with sensible defaults.

    By default creates an active bank with no memories.
    Accepts partial overrides via keyword arguments.
    """
    if bank is None:
        bank = a_memory_bank()
    if memories is None:
        memories = []
    return MemoryBankAggregate(bank=bank, memories=memories)


def a_file_hash(
    hash_value: str = "a" * 64,
) -> FileHash:
    """Create a valid FileHash instance with a default SHA-256 hash.

    Accepts partial overrides via keyword arguments.
    """
    return FileHash(hash_value=hash_value)


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------

class InMemoryMemoryRepository(MemoryRepository):
    """In-memory implementation of MemoryRepository for testing."""

    def __init__(self, data: Optional[List[Memory]] = None) -> None:
        self._store: dict[str, Memory] = {}
        if data:
            for m in data:
                self._store[m.id] = m

    def save(self, memory: Memory) -> Result[Memory]:
        self._store[memory.id] = memory
        return Result.ok(memory)

    def find_by_id(self, memory_id: str) -> Result[Optional[Memory]]:
        return Result.ok(self._store.get(memory_id))

    def find_by_bank(self, bank_name: str, limit: int = 100) -> Result[List[Memory]]:
        """Find memories by bank name (matches on source field)."""
        return Result.ok([m for m in self._store.values() if m.source == bank_name][:limit])

    def delete(self, memory_id: str) -> Result[bool]:
        if memory_id in self._store:
            del self._store[memory_id]
            return Result.ok(True)
        return Result.ok(False)


class InMemoryMemoryBankRepository(MemoryBankRepository):
    """In-memory implementation of MemoryBankRepository for testing."""

    def __init__(self, data: Optional[List[MemoryBankAggregate]] = None) -> None:
        self._store: dict[str, MemoryBankAggregate] = {}
        if data:
            for agg in data:
                self._store[agg.bank.name] = agg

    def save(self, aggregate: MemoryBankAggregate) -> Result[None]:
        self._store[aggregate.bank.name] = aggregate
        return Result.ok(None)

    def find_by_id(self, bank_name: str) -> Result[Optional[MemoryBankAggregate]]:
        return Result.ok(self._store.get(bank_name))

    def list(self) -> Result[List[MemoryBankAggregate]]:
        return Result.ok(list(self._store.values()))

    def delete(self, bank_name: str) -> bool:
        if bank_name in self._store:
            del self._store[bank_name]
            return True
        return False


# ---------------------------------------------------------------------------
# Factory helpers for fake repositories
# ---------------------------------------------------------------------------

def a_memory_repository(data: Optional[List[Memory]] = None) -> InMemoryMemoryRepository:
    """Create an in-memory Memory repository, optionally seeded with data."""
    return InMemoryMemoryRepository(data)


def a_memory_bank_repository(data: Optional[List[MemoryBankAggregate]] = None) -> InMemoryMemoryBankRepository:
    """Create an in-memory MemoryBankAggregate repository, optionally seeded with data."""
    return InMemoryMemoryBankRepository(data)
