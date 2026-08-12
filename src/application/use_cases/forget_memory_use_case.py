"""ForgetMemoryUseCase — deletes a memory, cleans up related files, and hash index.

Destructive operation with memory bank type guard: only allowed on "pure_memories"
banks. On successful memory deletion, finds and removes all related file chunks.
If a file has no remaining chunks after removal, deletes the file and its relations.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository

if TYPE_CHECKING:
    from src.application.services.file_service import FileService


class ForgetMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory deletion with file chunk cleanup and hash index cleanup.

    Guard: only allowed on "pure_memories" banks — banks with file associations
    should not use this destructive operation.
    """

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        hash_index_service: HashIndexService,
        logger: structlog.stdlib.BoundLogger,
        file_service: FileService,
        chunk_repository: FileChunkRepository,
        bank_type_checker: Callable[[str], str],
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.hash_index_service = hash_index_service
        self.file_service = file_service
        self.chunk_repository = chunk_repository
        self.bank_type_checker = bank_type_checker

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that memory_id is present and non-empty."""
        if not parameters.get("memory_id"):
            return Result.ko([ErrorWithDetails("MEMORY_ID_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute forget with bank type guard, chunk cleanup, and hash index cleanup."""
        memory_id = parameters["memory_id"]
        memory_bank = parameters.get("memory_bank", "default")

        # Guard: only allow on pure_memories banks
        bank_type = self.bank_type_checker(memory_bank)
        if bank_type != "pure_memories":
            return Result.ko([ErrorWithDetails("MEMORY_BANK_NOT_SUPPORTED", {
                "memory_bank": memory_bank,
                "bank_type": bank_type,
            })])

        forget_result = self.mnemosyne_client.forget(memory_id)
        if not forget_result.is_ok:
            return forget_result

        # Mnemosyne.forget returns bool — True means deleted, False means not found
        deleted = forget_result.value
        status = "deleted" if deleted else "not_found"

        # Only clean up related files and hash index if memory was actually deleted
        if deleted:
            self._cleanup_chunks_and_files(memory_id)
            self.hash_index_service.remove(memory_id)

        return Result.ok({
            "status": status,
            "memory_id": memory_id,
            "memory_bank": memory_bank,
        })

    def _cleanup_chunks_and_files(self, memory_id: str) -> None:
        """Remove all file chunks referencing the memory and delete empty files."""
        chunks_result = self.chunk_repository.get_chunks_by_memory_id(memory_id)
        if not chunks_result.is_ok:
            return

        chunks = chunks_result.value
        if not chunks:
            return

        for chunk in chunks:
            file_id = chunk.file_id
            remove_result = self.file_service.remove_chunk(file_id, memory_id)
            if remove_result.is_ko:
                continue

            # Check if file has no remaining chunks — delete it
            count_result = self.file_service.get_chunks_count_by_file_id(file_id)
            if count_result.is_ok and count_result.value == 0:
                self.file_service.delete_file(file_id)
