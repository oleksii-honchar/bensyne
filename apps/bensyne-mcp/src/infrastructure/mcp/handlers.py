"""MCP tool handlers with memory bank routing.

Delegates to application-layer use cases instead of calling the
router/client directly. Each handler:
1. Extracts memory_bank from arguments
2. Resolves per-bank dependencies from the DI container (D25)
3. Calls use_case.execute(arguments)
4. Returns Result.value on success
5. Raises ValidationError on Result.ko

File-path dependencies (per-bank file metadata bundle, FileService, hash
index service, bank type checker) and file-path use cases are constructed
exclusively by the DI container factories — handlers never call their
constructors directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.application.use_cases.list_banks_use_case import ListBanksUseCase
from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
from src.application.use_cases.sleep_use_case import SleepUseCase
from src.application.use_cases.update_memory_use_case import UpdateMemoryUseCase
from src.domain.exceptions import ValidationError
from src.infrastructure.di import Container, ProductionContainer
from src.infrastructure.mcp.validation import require_memory_bank
from src.utils.logging import log_tool_call
from src.utils.structured_logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter

logger = get_logger(__name__)


def _resolve_container(container: Container | None) -> Container:
    """Return the given container, or a fresh ProductionContainer (unit-test path)."""
    return container if container is not None else ProductionContainer()


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
async def handle_remember(
    router: MemoryBankRouter, arguments: dict, container: Container | None = None
) -> dict:
    """Store a durable memory in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    content = arguments.get("content")

    logger.debug("[rememberMemory] Received arguments", memory_bank=memory_bank, content=content)

    if not content:
        raise ValidationError("content is required")

    # Get MnemosyneClient from router to use as memory_repository
    instance = await router.get_instance(memory_bank)
    logger.debug("[rememberMemory] Got instance", memory_bank=instance.memory_bank)

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)
    file_service = container.file_service(bundle=bundle)
    hash_index_service = container.hash_index_service(memory_bank=memory_bank)

    # Build parameters for the use case — enrich with memory_bank.
    # The chunk hash lives in metadata.chunk_hash; the use case reads it directly.
    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.remember_memory_use_case(
        memory_repository=instance,
        hash_index_service=hash_index_service,
        file_service=file_service,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "rememberMemory")


@log_tool_call("recallMemory")
async def handle_recall(
    router: MemoryBankRouter, arguments: dict, container: Container | None = None
) -> dict:
    """Search for relevant memories in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    query = arguments.get("query")

    if not query:
        raise ValidationError("query is required")

    instance = await router.get_instance(memory_bank)

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)
    file_service = container.file_service(bundle=bundle)
    file_enrichment_service = container.file_enrichment_service(file_service=file_service)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.recall_memory_use_case(
        mnemosyne_client=instance,
        file_enrichment_service=file_enrichment_service,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "recallMemory")


@log_tool_call("forgetMemory")
async def handle_forget(
    router: MemoryBankRouter,
    arguments: dict,
    bank_type_checker: Callable[[str], str] | None = None,
    container: Container | None = None,
) -> dict:
    """Delete a memory from the specified memory bank.

    Only allowed on "pure_memories" banks — banks with file associations
    will be rejected with MEMORY_BANK_NOT_SUPPORTED.
    """
    memory_bank = require_memory_bank(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(memory_bank)

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    hash_index_service = container.hash_index_service(memory_bank=memory_bank)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)
    file_service = container.file_service(bundle=bundle)

    # Bank type checker: determine if this bank is "pure_memories"
    if bank_type_checker is None:
        bank_type_checker = container.bank_type_checker(data_dir=Path(router.config.data_dir))

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.forget_memory_use_case(
        mnemosyne_client=instance,
        hash_index_service=hash_index_service,
        file_service=file_service,
        bank_type_checker=bank_type_checker,
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
    stats_result = instance.get_stats()

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
async def handle_search_files(
    router: MemoryBankRouter, arguments: dict, container: Container | None = None
) -> dict:
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

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)
    file_service = container.file_service(bundle=bundle)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.search_files_use_case(
        mnemosyne_client=instance,
        file_service=file_service,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "searchFiles")


@log_tool_call("expandFileRelations")
async def handle_expand_file_relations(
    router: MemoryBankRouter, arguments: dict, container: Container | None = None
) -> dict:
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

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.expand_file_relations_use_case(
        mnemosyne_client=instance.get,
        bundle=bundle,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "expandFileRelations")


@log_tool_call("fetchFile")
async def handle_fetch_file(
    router: MemoryBankRouter, arguments: dict, container: Container | None = None
) -> dict:
    """Fetch and reconstruct file content from its memory chunks.

    Default mode: looks up file by ID, retrieves all chunks ordered by chunk_index,
    reconstructs content with line continuity, and returns with metadata.

    Neighbor mode (center_chunk_index provided): returns only the window
    [center - adjacent_chunks .. center + adjacent_chunks] clamped to
    0..total_chunks-1, each chunk with content, position and section_header.
    """
    memory_bank = require_memory_bank(arguments)
    file_id = arguments.get("file_id")

    if not file_id:
        raise ValidationError("file_id is required")

    # Get MnemosyneClient from router
    instance = await router.get_instance(memory_bank)

    # Per-bank file metadata dependencies via DI container (D25)
    container = _resolve_container(container)
    bank_dir = Path(router.config.data_dir) / memory_bank
    bundle = container.file_metadata_bundle(bank_dir=bank_dir)
    file_service = container.file_service(bundle=bundle)

    params = dict(arguments)
    params["memory_bank"] = memory_bank

    use_case = container.fetch_file_use_case(
        mnemosyne_client=instance,
        file_service=file_service,
    )
    result = use_case.execute(params)
    return _raise_on_ko(result, "fetchFile")
