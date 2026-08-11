"""Domain interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.domain.aggregates.memory_bank_aggregate import MemoryBankAggregate
from src.domain.entities.memory import Memory
from src.domain.result import Result


class IMnemosyneClient(ABC):
    """Interface for the Mnemosyne client wrapper."""

    @abstractmethod
    async def remember(self, content: str, source: str = "conversation", **kwargs: Any) -> Dict[str, Any]:
        """Store a durable memory."""
        ...

    @abstractmethod
    async def recall(self, query: str, limit: int = 10, **kwargs: Any) -> List[Dict[str, Any]]:
        """Search for relevant memories."""
        ...

    @abstractmethod
    async def forget(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory."""
        ...

    @abstractmethod
    async def update(self, memory_id: str, content: Optional[str] = None, importance: Optional[float] = None) -> Dict[str, Any]:
        """Update memory content or importance."""
        ...

    @abstractmethod
    async def sleep(self) -> Dict[str, Any]:
        """Trigger memory consolidation."""
        ...

    @abstractmethod
    async def stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        ...

    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        ...


class IMemoryBankRouter(ABC):
    """Interface for memory bank routing."""

    @abstractmethod
    async def get_instance(self, memory_bank: str) -> IMnemosyneClient:
        """Get or create Mnemosyne client for the given memory bank."""
        ...

    @abstractmethod
    async def list_banks(self) -> List[str]:
        """List all active memory bank names."""
        ...


class MemoryRepository(ABC):
    """Repository port for Memory entities.

    Only depends on domain types (Memory, Result) — zero infrastructure dependencies.
    """

    @abstractmethod
    def save(self, memory: Memory) -> Result[Memory]:
        """Save a memory, returning the saved entity."""
        ...

    @abstractmethod
    def find_by_id(self, memory_id: str) -> Result[Optional[Memory]]:
        """Find a memory by its id."""
        ...

    @abstractmethod
    def find_by_bank(self, bank_name: str, limit: int = 100) -> Result[List[Memory]]:
        """Find memories belonging to a bank (by source field)."""
        ...

    @abstractmethod
    def delete(self, memory_id: str) -> Result[bool]:
        """Delete a memory by id, returning True if it existed."""
        ...


class MemoryBankRepository(ABC):
    """Repository port for MemoryBankAggregate entities.

    Only depends on domain types (MemoryBankAggregate, Result) — zero infrastructure dependencies.
    """

    @abstractmethod
    def save(self, aggregate: MemoryBankAggregate) -> Result[None]:
        """Save an aggregate."""
        ...

    @abstractmethod
    def find_by_id(self, bank_name: str) -> Result[Optional[MemoryBankAggregate]]:
        """Find an aggregate by bank name."""
        ...

    @abstractmethod
    def list(self) -> Result[List[MemoryBankAggregate]]:
        """List all saved aggregates."""
        ...
