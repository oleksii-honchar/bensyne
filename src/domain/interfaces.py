"""Domain interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.domain.aggregates.memory_bank_aggregate import MemoryBankAggregate
from src.domain.entities.file import File
from src.domain.entities.file_chunk import FileChunk
from src.domain.entities.file_relation import FileRelation, RelationType
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


class FileRepository(ABC):
    """Repository port for File entities.

    Only depends on domain types (File, Result) — zero infrastructure dependencies.
    """

    @abstractmethod
    def save_file(self, file: File) -> Result[File]:
        """Save a file, returning the saved entity."""
        ...

    @abstractmethod
    def get_file_by_id(self, file_id: str) -> Result[Optional[File]]:
        """Find a file by its id."""
        ...

    @abstractmethod
    def get_file_by_path(self, path: str) -> Result[Optional[File]]:
        """Find a file by its path."""
        ...

    @abstractmethod
    def list_files(self) -> Result[List[File]]:
        """List all saved files."""
        ...

    @abstractmethod
    def search_files_by_query(self, query: str) -> Result[List[File]]:
        """Search files by query across path, keywords, and tags."""
        ...

    @abstractmethod
    def delete_file(self, file_id: str) -> Result[bool]:
        """Delete a file by id, returning True if it existed."""
        ...


class FileChunkRepository(ABC):
    """Repository port for FileChunk entities.

    Only depends on domain types (FileChunk, Result) — zero infrastructure dependencies.
    """

    @abstractmethod
    def save_chunk(self, chunk: FileChunk) -> Result[FileChunk]:
        """Save a chunk, returning the saved entity."""
        ...

    @abstractmethod
    def get_chunk_by_id(self, chunk_id: str) -> Result[Optional[FileChunk]]:
        """Find a chunk by its id."""
        ...

    @abstractmethod
    def get_chunks_by_file_id(self, file_id: str) -> Result[List[FileChunk]]:
        """Find all chunks belonging to a file, ordered by chunk_index."""
        ...

    @abstractmethod
    def get_chunk_by_memory_id(self, memory_id: str) -> Result[Optional[FileChunk]]:
        """Find a chunk by its associated memory id."""
        ...

    @abstractmethod
    def get_chunks_by_memory_id(self, memory_id: str) -> Result[List[FileChunk]]:
        """Find all chunks by their associated memory id."""
        ...

    @abstractmethod
    def delete_chunk(self, chunk_id: str) -> Result[bool]:
        """Delete a chunk by id, returning True if it existed."""
        ...


class FileRelationRepository(ABC):
    """Repository port for FileRelation entities.

    Only depends on domain types (FileRelation, Result) — zero infrastructure dependencies.
    """

    @abstractmethod
    def save_relation(self, relation: FileRelation) -> Result[FileRelation]:
        """Save a relation, returning the saved entity."""
        ...

    @abstractmethod
    def get_relation_by_id(self, relation_id: str) -> Result[Optional[FileRelation]]:
        """Find a relation by its id."""
        ...

    @abstractmethod
    def get_relations_by_file_id(self, file_id: str) -> Result[List[FileRelation]]:
        """Find all relations where the given file is either source or target."""
        ...

    @abstractmethod
    def get_relations_by_type(self, relation_type: RelationType) -> Result[List[FileRelation]]:
        """Find all relations of a given type."""
        ...

    @abstractmethod
    def delete_relation(self, relation_id: str) -> Result[bool]:
        """Delete a relation by id, returning True if it existed."""
        ...
