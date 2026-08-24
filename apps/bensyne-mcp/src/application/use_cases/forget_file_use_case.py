"""ForgetFileUseCase — deletes a file and its unique memories, preserving shared ones.

File-granular forget capability. For each memory contributed by this file:
- If the memory is NOT referenced by any other file: forget it from mnemosyne and
  remove it from the hash index.
- If the memory IS referenced by other files: preserve the mnemosyne memory and
  hash index entry (the other files still need it); only the file's chunk row is
  removed via the D20 cascade.

This use case intentionally bypasses the forgetMemory bank-type guard: file-level
deletion is an operator action, not a recall operation.
"""

from __future__ import annotations

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result
from src.domain.models.file_model import FileStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.services.file_service import FileService


class ForgetFileUseCase(BaseUseCase[dict, dict]):
    """Orchestrates file-level deletion with shared-memory guard.

    For each memory contributed by the file:
    - Not shared: forget from mnemosyne, remove from hash index
    - Shared: preserve mnemosyne memory and hash index entry
    File marked DELETED via D20 cascade.

    Intentionally bypasses the forgetMemory bank-type guard: file-level deletion
    is an operator action, not a recall operation.
    """

    def __init__(
        self,
        file_service: FileService,
        hash_index_service: HashIndexService,
        mnemosyne_client: MnemosyneClient,
        logger: structlog.stdlib.BoundLogger,
        memory_bank: str = "default",
    ) -> None:
        super().__init__(logger)
        self.file_service = file_service
        self.hash_index_service = hash_index_service
        self.mnemosyne_client = mnemosyne_client
        self.memory_bank = memory_bank

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that file_path is present and non-empty."""
        file_path = parameters.get("file_path")
        if not file_path:
            return Result.ko([ErrorWithDetails("FILE_PATH_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute file-level forget with shared-memory guard and D20 cascade."""
        file_path = parameters["file_path"]

        self.logger.info(
            "Forgetting file",
            use_case="forget_file",
            method="execute_internal",
            file_path=file_path,
            memory_bank=self.memory_bank,
        )

        # Step 2: Get the file by path
        file_result = self.file_service.get_file_by_path(file_path)
        if file_result.is_ko:
            return file_result

        file = file_result.value
        if file is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"path": file_path})])

        # Step 3: Already deleted? Return idempotent no-op.
        if file.status == FileStatus.DELETED:
            self.logger.debug(
                "File already deleted",
                use_case="forget_file",
                method="execute_internal",
                file_id=file.id,
            )
            return Result.ok({"status": "already_deleted"})

        # Step 4: Load all chunks (memories) for this file
        chunks_result = self.file_service.get_chunks_by_file_id(file.id)
        if chunks_result.is_ko:
            return chunks_result  # type: ignore[return-value]

        chunks = chunks_result.value

        # Process each memory: forget if not shared, preserve if shared
        for chunk in chunks:
            memory_id = chunk.memory_id
            if not memory_id:
                continue

            # Shared-memory guard: is this memory still referenced by another file?
            if self._is_memory_still_referenced(memory_id, file.id):
                # Memory is shared — DO NOT forget, DO NOT remove from hash index
                # The D20 cascade will remove this file's chunk row only
                self.logger.debug(
                    "Memory is shared, skipping forget",
                    use_case="forget_file",
                    method="execute_internal",
                    memory_id=memory_id,
                    file_id=file.id,
                )
                continue

            # Memory is not shared — safe to forget
            # Remove from hash index (ignore error — idempotent)
            self.hash_index_service.remove(memory_id)

            # Forget from mnemosyne
            forget_result = self.mnemosyne_client.forget(memory_id)
            if not forget_result.is_ok:
                return forget_result

            # Mirror forget_memory_use_case: treat .value as truthy/falsy
            # Both True (deleted) and False (not found) are non-error outcomes
            deleted = forget_result.value

            self.logger.debug(
                "Memory forgotten",
                use_case="forget_file",
                method="execute_internal",
                memory_id=memory_id,
                deleted=deleted,
            )

        # Step 5: Mark file as DELETED (D20 cascade removes chunk rows)
        delete_result = self.file_service.delete_file(file.id)
        if delete_result.is_ko:
            return delete_result

        self.logger.info(
            "File forgotten",
            use_case="forget_file",
            method="execute_internal",
            file_id=file.id,
            status="forgotten",
        )

        # Step 6: Return success
        return Result.ok({
            "status": "forgotten",
            "file_id": file.id,
            "files_affected": 1,
        })

    def _is_memory_still_referenced(self, memory_id: str, exclude_file_id: str) -> bool:
        """Check if a memory is still referenced by another file.

        Returns True if ANY chunk with this memory_id belongs to a different file.
        """
        chunks_result = self.file_service.get_chunks_by_memory_id(memory_id)
        if chunks_result.is_ko:
            return False  # On error, treat as not referenced (idempotent)

        chunks = chunks_result.value
        return any(chunk.file_id != exclude_file_id for chunk in chunks)
