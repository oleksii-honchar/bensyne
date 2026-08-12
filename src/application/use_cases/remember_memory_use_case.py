"""RememberMemoryUseCase — orchestrates memory creation with hash deduplication.

Validates input, creates Memory entity, checks hash index for
deduplication, and saves via repository.
"""

import uuid
from typing import Optional

import structlog.stdlib
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.memory_entity import Memory
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient

from src.utils.result import ErrorWithDetails, Result


class RememberMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory creation with hash deduplication."""

    def __init__(
        self,
        memory_repository: MnemosyneClient,
        hash_index_service: HashIndexService,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.memory_repository = memory_repository
        self.hash_index_service = hash_index_service

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that content is present and non-empty."""
        if not parameters.get("content"):
            return Result.ko([ErrorWithDetails("CONTENT_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute memory creation with hash deduplication."""
        memory_bank = parameters.get("memory_bank", "default")

        self.logger.info(
            "Processing memory",
            use_case="remember_memory",
            memory_bank=memory_bank,
        )

        # 1. Check hash index for deduplication first (early exit)
        file_hash = self._extract_file_hash(parameters)
        if file_hash:
            self.logger.debug(
                "Hash index lookup",
                use_case="remember_memory",
                file_hash=file_hash[:16],
            )
            lookup_result = self.hash_index_service.lookup(file_hash)
            if lookup_result.is_ok and lookup_result.value:
                existing_memory_id = lookup_result.value
                self.logger.info(
                    "Memory deduplicated",
                    use_case="remember_memory",
                    existing_memory_id=existing_memory_id,
                )
                return Result.ok({
                    "status": "deduplicated",
                    "memory_id": existing_memory_id,
                })

        # 2. Create memory entity — generate id if not provided
        create_params = dict(parameters)
        create_params.setdefault("id", str(uuid.uuid4()))
        memory_result = Memory.of(create_params)
        if not memory_result.is_ok:
            self.logger.error(
                "Memory creation failed",
                use_case="remember_memory",
                errors=memory_result.get_formatted_errors(),
            )
            return memory_result

        memory = memory_result.value
        self.logger.debug(
            "Memory entity created",
            use_case="remember_memory",
            memory_id=memory.id,
        )

        # 3. Save memory — save may return a Memory with a different (actual) id
        save_result = self.memory_repository.save(memory)
        if not save_result.is_ok:
            self.logger.error(
                "Memory save failed",
                use_case="remember_memory",
                memory_id=memory.id,
                errors=save_result.get_formatted_errors(),
            )
            return save_result

        # Use the saved memory — it may have a different id than the input
        saved_memory = save_result.value

        # 4. Index hash if applicable
        if file_hash and saved_memory.id:
            self.hash_index_service.store(file_hash, saved_memory.id)
            self.logger.info(
                "Hash indexed",
                use_case="remember_memory",
                memory_id=saved_memory.id,
                file_hash=file_hash[:16],
            )

        return Result.ok({
            "status": "stored",
            "memory_id": saved_memory.id,
            "memory_bank": memory_bank,
        })

    @staticmethod
    def _extract_file_hash(parameters: dict) -> Optional[str]:
        """Extract file hash from parameters."""
        return parameters.get("hash")
