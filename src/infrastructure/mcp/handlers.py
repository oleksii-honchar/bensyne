"""MCP tool handlers with memory bank routing.

Delegates to application-layer use cases instead of calling the
router/client directly. Each handler:
1. Extracts memory_bank from arguments
2. Instantiates the appropriate use case with dependencies
3. Calls use_case.execute(arguments)
4. Returns Result.value on success
5. Raises ValidationError on Result.ko
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.application.use_cases.list_banks_use_case import ListBanksUseCase
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.application.use_cases.sleep_use_case import SleepUseCase
from src.application.services.file_service import FileService
from src.application.use_cases.update_memory_use_case import UpdateMemoryUseCase
from src.domain.exceptions import ValidationError
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.infrastructure.mcp.validation import require_memory_bank
from src.utils.logging import log_tool_call
from src.utils.structured_logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter

logger = get_logger(__name__)


def _raise_on_ko(result, handler_name: str) -> dict:
    """Extract Result.value or raise ValidationError on Result.ko."""
    if result.is_ok:
        return result.value  # type: ignore[return-value]
    error = result.errors[0] if result.errors else None
    msg = f"{handler_name} failed"
    if error:
        msg = f"{handler_name} failed: {error.error_code}"
    raise ValidationError(msg)


@log_tool_call("rememberMemory")
async def handle_remember(router: MemoryBankRouter, arguments: dict) -> dict:
    """Store a durable memory in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    content = arguments.get("content")

    logger.debug("[rememberMemory] Received arguments", memory_bank=memory_bank, content=content)

    if not content:
        raise ValidationError("content is required")

    # Get MnemosyneClient from router to use as memory_repository
    instance = await router.get_instance(memory_bank)
    logger.debug("[rememberMemory] Got instance", memory_bank=instance.memory_bank)

    # Create hash index service for this memory bank
    hash_index_service = HashIndexService(memory_bank)

    # Build parameters for the use case — enrich with memory_bank and hash
    params = dict(arguments)
    params["memory_bank"] = memory_bank
    # Extract file hash from arguments and pass as "hash" key
    file_hash = HashIndexService.extract_file_hash(arguments)
    if file_hash:
        params["hash"] = file_hash

    use_case = RememberMemoryUseCase(
        memory_repository=instance,
        hash_index_service=hash_index_service,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "rememberMemory")


@log_tool_call("recallMemory")
async def handle_recall(router: MemoryBankRouter, arguments: dict) -> dict:
    """Search for relevant memories in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    query = arguments.get("query")

    if not query:
        raise ValidationError("query is required")

    instance = await router.get_instance(memory_bank)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = RecallMemoryUseCase(
        mnemosyne_client=instance,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "recallMemory")


@log_tool_call("forgetMemory")
async def handle_forget(router: MemoryBankRouter, arguments: dict) -> dict:
    """Delete a memory from the specified memory bank.

    Only allowed on "pure_memories" banks — banks with file associations
    will be rejected with MEMORY_BANK_NOT_SUPPORTED.
    """
    memory_bank = require_memory_bank(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(memory_bank)
    hash_index_service = HashIndexService(memory_bank)

    # Create per-bank file metadata repositories for chunk cleanup
    from pathlib import Path

    from src.infrastructure.storage.sqlite.file_chunk_repository import (
        FileChunkRepository,
    )
    from src.infrastructure.storage.sqlite.file_metadata_connection import (
        FileMetadataConnectionManager,
    )
    from src.infrastructure.storage.sqlite.file_relation_repository import (
        FileRelationRepository,
    )
    from src.infrastructure.storage.sqlite.file_repository import FileRepository

    bank_dir = Path(router.config.data_dir) / memory_bank
    conn_manager = FileMetadataConnectionManager(bank_dir=bank_dir)
    file_repo = FileRepository(conn_manager)
    chunk_repo = FileChunkRepository(conn_manager)
    relation_repo = FileRelationRepository(conn_manager)

    file_service = FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=logger,
    )

    # Bank type checker: determine if this bank is "pure_memories"
    def _bank_type_checker(bank_name: str) -> str:
        """Return the bank type for a given bank name.

        A bank is "file_metadata" if it has file metadata stored (SQLite DB exists),
        otherwise it's "pure_memories".
        """
        db_path = Path(router.config.data_dir) / bank_name / "file_metadata.db"
        if db_path.exists():
            return "file_metadata"
        return "pure_memories"

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = ForgetMemoryUseCase(
        mnemosyne_client=instance,
        hash_index_service=hash_index_service,
        logger=logger,
        file_service=file_service,
        chunk_repository=chunk_repo,
        bank_type_checker=_bank_type_checker,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "forgetMemory")


@log_tool_call("updateMemory")
async def handle_update(router: MemoryBankRouter, arguments: dict) -> dict:
    """Update memory content or importance in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(memory_bank)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = UpdateMemoryUseCase(
        mnemosyne_client=instance,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "updateMemory")


@log_tool_call("sleep")
async def handle_sleep(router: MemoryBankRouter, arguments: dict) -> dict:
    """Trigger memory consolidation in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)

    instance = await router.get_instance(memory_bank)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = SleepUseCase(
        mnemosyne_client=instance,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "sleep")


@log_tool_call("getMemoryStats")
async def handle_stats(router: MemoryBankRouter, arguments: dict) -> dict:
    """Return memory statistics for the specified memory bank."""
    memory_bank = require_memory_bank(arguments)

    instance = await router.get_instance(memory_bank)
    stats_result = instance.stats()

    if stats_result.is_ok:
        stats = stats_result.value
    else:
        stats = {"error": "Failed to retrieve stats"}

    return {
        "stats": stats,
        "memory_bank": memory_bank,
    }


@log_tool_call("listMemoryBanks")
async def handle_list_banks(router: MemoryBankRouter, arguments: dict) -> dict:
    """List all active memory banks with their status, descriptions, and memory counts.

    Delegates to ListBanksUseCase.
    """
    use_case = ListBanksUseCase(
        router=router,
        logger=logger,
    )
    result = use_case.execute(arguments)
    return _raise_on_ko(result, "listMemoryBanks")


@log_tool_call("registerMemoryBank")
async def handle_register_bank(router: MemoryBankRouter, arguments: dict) -> dict:
    """Register or update a memory bank description."""
    use_case = RegisterBankUseCase(
        router=router,
        logger=logger,
    )
    result = use_case.execute(arguments)
    return _raise_on_ko(result, "registerMemoryBank")


@log_tool_call("searchFiles")
async def handle_search_files(router: MemoryBankRouter, arguments: dict) -> dict:
    """Search files using semantic recall with file metadata enrichment.

    Two-phase search: Phase 1 — query memories via mnemosyne,
    Phase 2 — enrich with file metadata from SQLite.
    """
    memory_bank = require_memory_bank(arguments)
    query = arguments.get("query")

    if not query:
        raise ValidationError("query is required")

    # Get MnemosyneClient from router
    instance = await router.get_instance(memory_bank)

    # Create per-bank file metadata repositories
    from pathlib import Path

    from src.infrastructure.storage.sqlite.file_chunk_repository import (
        FileChunkRepository,
    )
    from src.infrastructure.storage.sqlite.file_metadata_connection import (
        FileMetadataConnectionManager,
    )
    from src.infrastructure.storage.sqlite.file_relation_repository import (
        FileRelationRepository,
    )
    from src.infrastructure.storage.sqlite.file_repository import FileRepository

    bank_dir = Path(router.config.data_dir) / memory_bank
    conn_manager = FileMetadataConnectionManager(bank_dir=bank_dir)
    file_repo = FileRepository(conn_manager)
    chunk_repo = FileChunkRepository(conn_manager)
    relation_repo = FileRelationRepository(conn_manager)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = SearchFilesUseCase(
        mnemosyne_client=instance,
        chunk_repository=chunk_repo,
        file_repository=file_repo,
        relation_repository=relation_repo,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "searchFiles")


@log_tool_call("expandFileRelations")
async def handle_expand_file_relations(router: MemoryBankRouter, arguments: dict) -> dict:
    """Expand file relations to get content from related files.

    Retrieves related files via file_relations and composes content
    from their memory chunks.
    """
    memory_bank = require_memory_bank(arguments)
    file_id = arguments.get("file_id")

    if not file_id:
        raise ValidationError("file_id is required")

    # Get MnemosyneClient from router
    instance = await router.get_instance(memory_bank)

    # Create per-bank file metadata repositories
    from pathlib import Path

    from src.infrastructure.storage.sqlite.file_chunk_repository import (
        FileChunkRepository,
    )
    from src.infrastructure.storage.sqlite.file_metadata_connection import (
        FileMetadataConnectionManager,
    )
    from src.infrastructure.storage.sqlite.file_relation_repository import (
        FileRelationRepository,
    )
    from src.infrastructure.storage.sqlite.file_repository import FileRepository

    bank_dir = Path(router.config.data_dir) / memory_bank
    conn_manager = FileMetadataConnectionManager(bank_dir=bank_dir)
    file_repo = FileRepository(conn_manager)
    chunk_repo = FileChunkRepository(conn_manager)
    relation_repo = FileRelationRepository(conn_manager)

    file_service = FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=logger,
    )

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = ExpandFileRelationsUseCase(
        mnemosyne_client=instance,
        file_service=file_service,
        relation_repository=relation_repo,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "expandFileRelations")


@log_tool_call("fetchFile")
async def handle_fetch_file(router: MemoryBankRouter, arguments: dict) -> dict:
    """Fetch and reconstruct file content from its memory chunks.

    Looks up file by ID, retrieves all chunks ordered by chunk_index,
    reconstructs content with line continuity, and returns with metadata.
    """
    memory_bank = require_memory_bank(arguments)
    file_id = arguments.get("file_id")

    if not file_id:
        raise ValidationError("file_id is required")

    # Get MnemosyneClient from router
    instance = await router.get_instance(memory_bank)

    # Create per-bank file metadata repositories
    from pathlib import Path

    from src.infrastructure.storage.sqlite.file_chunk_repository import (
        FileChunkRepository,
    )
    from src.infrastructure.storage.sqlite.file_metadata_connection import (
        FileMetadataConnectionManager,
    )
    from src.infrastructure.storage.sqlite.file_repository import FileRepository

    bank_dir = Path(router.config.data_dir) / memory_bank
    conn_manager = FileMetadataConnectionManager(bank_dir=bank_dir)
    file_repo = FileRepository(conn_manager)
    chunk_repo = FileChunkRepository(conn_manager)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = FetchFileUseCase(
        mnemosyne_client=instance,
        chunk_repository=chunk_repo,
        file_repository=file_repo,
        logger=logger,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "fetchFile")
