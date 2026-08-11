"""ProcessMemoryUseCase — orchestrates memory creation with hash deduplication.

Validates input, creates Memory entity, checks hash index for
deduplication, and saves via repository.
"""

from typing import Optional

import structlog.stdlib
from src.infrastructure.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.entities.memory import Memory
from src.domain.interfaces import MemoryRepository
from src.domain.result import ErrorWithDetails, Result


class ProcessMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory creation with hash deduplication."""

    def __init__(
        self,
        memory_repository: MemoryRepository,
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
        # 1. Check hash index for deduplication first (early exit)
        file_hash = self._extract_file_hash(parameters)
        if file_hash:
            existing_memory_id = self.hash_index_service.lookup(file_hash)
            if existing_memory_id:
                return Result.ok({
                    "status": "deduplicated",
                    "memory_id": existing_memory_id,
                })

        # 2. Create memory entity
        memory_result = Memory.of(parameters)
        if not memory_result.is_ok:
            return memory_result

        memory = memory_result.value

        # 3. Save memory
        save_result = self.memory_repository.save(memory)
        if not save_result.is_ok:
            return save_result

        # 4. Index hash if applicable
        if file_hash and memory.id:
            self.hash_index_service.store(file_hash, memory.id)

        return Result.ok({
            "status": "stored",
            "memory_id": memory.id,
            "memory_bank": parameters.get("memory_bank", "default"),
        })

    @staticmethod
    def _extract_file_hash(parameters: dict) -> Optional[str]:
        """Extract file hash from parameters."""
        return parameters.get("hash")
