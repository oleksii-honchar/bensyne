"""Domain interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


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


class INamespaceRouter(ABC):
    """Interface for namespace routing."""

    @abstractmethod
    async def get_instance(self, namespace: str) -> IMnemosyneClient:
        """Get or create Mnemosyne client for the given namespace."""
        ...

    @abstractmethod
    async def list_namespaces(self) -> List[str]:
        """List all active namespace names."""
        ...
