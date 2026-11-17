"""ForgetMemoryUseCase — deletes a memory, cleans up related files, and hash index.

Destructive operation with a bank guard: allowed on "pure_memories" banks, and on
"file_metadata" banks ONLY for rows proven not file-backed (row-level provenance —
persona banks hold both file-backed node projections, which must never be forgotten,
and plain occasional memories, which must be forgettable). On successful memory
deletion, finds and removes all related file chunks. If a file has no remaining
chunks after removal, deletes the file and its relations.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result

if TYPE_CHECKING:
    from src.application.services.file_service import FileService


class ForgetMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory deletion with file chunk cleanup and hash index cleanup.

    Guard: "pure_memories" banks allowed directly; "file_metadata" banks allowed only
    after a row-level provenance check proves the target is not file-backed (node/file
    projections must never be forgotten; unknown provenance fails closed). Other bank
    types keep the bank-level refusal.
    """

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        hash_index_service: HashIndexService,
        logger: structlog.stdlib.BoundLogger,
        file_service: FileService,
        bank_type_checker: Callable[[str], str],
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.hash_index_service = hash_index_service
        self.file_service = file_service
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

        self.logger.info(
            "Forgetting memory",
            use_case="forget_memory",
            method="execute_internal",
            memory_id=memory_id,
            memory_bank=memory_bank,
        )

        # Guard: pure_memories banks proceed directly; file_metadata banks require a
        # row-level provenance check (file-backed rows = node/file projections = never
        # forgettable; provenance unknown = fail-closed). Other bank types: refusal.
        bank_type = self.bank_type_checker(memory_bank)
        if bank_type not in ("pure_memories", "file_metadata"):
            return Result.ko(
                [
                    ErrorWithDetails(
                        "MEMORY_BANK_NOT_SUPPORTED",
                        {
                            "memory_bank": memory_bank,
                            "bank_type": bank_type,
                        },
                    )
                ]
            )

        if bank_type == "file_metadata":
            chunks_result = self.file_service.get_chunks_by_memory_id(memory_id)
            if not chunks_result.is_ok:
                return Result.ko(
                    [
                        ErrorWithDetails(
                            "MEMORY_PROVENANCE_UNKNOWN",
                            {
                                "memory_id": memory_id,
                                "memory_bank": memory_bank,
                                "reason": "file-provenance lookup failed; refusing to delete a possibly file-backed row",
                            },
                        )
                    ]
                )
            if chunks_result.value:
                return Result.ko(
                    [
                        ErrorWithDetails(
                            "MEMORY_FILE_BACKED",
                            {
                                "memory_id": memory_id,
                                "memory_bank": memory_bank,
                                "reason": "row is file-backed (node/file projection); such memories are Racochu-managed — retire the source file instead",
                            },
                        )
                    ]
                )

        self.logger.debug(
            "Bank type check passed",
            use_case="forget_memory",
            method="execute_internal",
            memory_bank=memory_bank,
            bank_type=bank_type,
        )

        forget_result = self.mnemosyne_client.forget(memory_id)
        if not forget_result.is_ok:
            return forget_result

        # Mnemosyne.forget returns bool — True means deleted, False means not found
        deleted = forget_result.value
        status = "deleted" if deleted else "not_found"

        self.logger.debug(
            "Memory deletion result",
            use_case="forget_memory",
            method="execute_internal",
            memory_id=memory_id,
            deleted=deleted,
        )

        # Only clean up related files and hash index if memory was actually deleted
        if deleted:
            self._cleanup_chunks_and_files(memory_id)
            self.hash_index_service.remove(memory_id)

            self.logger.debug(
                "Chunk and file cleanup completed",
                use_case="forget_memory",
                method="execute_internal",
                memory_id=memory_id,
            )

        self.logger.info(
            "Memory forgotten",
            use_case="forget_memory",
            method="execute_internal",
            memory_id=memory_id,
            status=status,
        )

        return Result.ok(
            {
                "status": status,
                "memory_id": memory_id,
                "memory_bank": memory_bank,
            }
        )

    def _cleanup_chunks_and_files(self, memory_id: str) -> None:
        """Remove all file chunks referencing the memory and delete empty files."""
        chunks_result = self.file_service.get_chunks_by_memory_id(memory_id)
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
