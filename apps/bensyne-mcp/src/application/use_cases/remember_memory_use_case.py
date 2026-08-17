"""RememberMemoryUseCase — orchestrates memory creation with hash deduplication.

Validates input, creates Memory entity, checks hash index for
deduplication, and saves via repository.
"""

import uuid

import structlog.stdlib
from src.application.services.file_service import FileService
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.memory_entity import Memory
from src.domain.models.file_context_model import parse_file_context
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient

from src.utils.result import ErrorWithDetails, Result


class RememberMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory creation with hash deduplication."""

    def __init__(
        self,
        memory_repository: MnemosyneClient,
        hash_index_service: HashIndexService,
        file_service: FileService,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.memory_repository = memory_repository
        self.hash_index_service = hash_index_service
        self.file_service = file_service

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

        # 1. Check hash index for deduplication first.
        chunk_hash = self._extract_chunk_hash(parameters)
        if chunk_hash:
            self.logger.debug(
                "Hash index lookup",
                use_case="remember_memory",
                chunk_hash=chunk_hash[:16],
            )
            lookup_result = self.hash_index_service.lookup(chunk_hash)
            if lookup_result.is_ok and lookup_result.value:
                existing_memory_id = lookup_result.value
                self.logger.info(
                    "Memory deduplicated",
                    use_case="remember_memory",
                    existing_memory_id=existing_memory_id,
                )
                response: dict = {
                    "status": "deduplicated",
                    "memory_id": existing_memory_id,
                    "memory_bank": memory_bank,
                }
                # D14 (S3): a dedup hit STILL materializes with the EXISTING id —
                # idempotent upserts link the shared memory under this file.
                self._materialize(parameters, memory_bank, existing_memory_id, response)
                return Result.ok(response)

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
        if chunk_hash and saved_memory.id:
            self.hash_index_service.store(chunk_hash, saved_memory.id)
            self.logger.info(
                "Hash indexed",
                use_case="remember_memory",
                memory_id=saved_memory.id,
                chunk_hash=chunk_hash[:16],
            )

        response: dict = {
            "status": "stored",
            "memory_id": saved_memory.id,
            "memory_bank": memory_bank,
        }

        # 5. Materialize file context (spec §4.1) — non-fatal (S2).
        self._materialize(parameters, memory_bank, saved_memory.id, response)

        return Result.ok(response)

    def _materialize(
        self, parameters: dict, memory_bank: str, memory_id: str, response: dict
    ) -> None:
        """Materialize file context into ``response`` (non-fatal, S2).

        No file_path in metadata ⇒ no FileContext ⇒ plain memory response and
        FileService is never invoked. Failures are surfaced additively via
        ``response["file_materialization"]`` — remember still succeeds.
        """
        context = parse_file_context(parameters.get("metadata"))
        if context is None:
            return
        self.logger.info(
            "Materializing file context",
            use_case="remember_memory",
            memory_id=memory_id,
            file_path=context.file_path,
        )
        materialize_result = self.file_service.materialize_file_context(memory_bank, context, memory_id)
        if materialize_result.is_ok:
            response["file_materialization"] = {
                "status": "ok",
                "file_id": materialize_result.value["file_id"],
            }
        else:
            self.logger.error(
                "File context materialization failed",
                use_case="remember_memory",
                memory_id=memory_id,
                file_path=context.file_path,
                errors=materialize_result.get_formatted_errors(),
            )
            response["file_materialization"] = {
                "status": "failed",
                "errors": [error.error_code for error in materialize_result.errors],
            }

    @staticmethod
    def _extract_chunk_hash(parameters: dict) -> str | None:
        """Extract the chunk hash from ``metadata.chunk_hash`` (snake_case, D12)."""
        metadata = parameters.get("metadata")
        if not isinstance(metadata, dict):
            return None
        return metadata.get("chunk_hash")
