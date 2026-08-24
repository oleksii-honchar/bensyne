"""Dependency injection container using dependency-injector.

Provides:
- Container: base declarative container with provider definitions
- ProductionContainer: wires real infrastructure dependencies as singletons
- TestContainer: wires in-memory repositories and mock logger for testing
- create_test_container(): convenience factory for test containers

Override pattern:
    with container.override(container.logger, mock_logger):
        # mock_logger is used
    # original provider restored

Per-bank file-metadata factories (D25):
    bundle = container.file_metadata_bundle(bank_dir=Path("..."))
    file_service = container.file_service(bundle=bundle)
    use_case = container.fetch_file_use_case(mnemosyne_client=instance, file_service=file_service)

Factory providers take per-request objects as call-time arguments (dependency-injector
does not forward runtime kwargs to nested factories), so a handler builds the bundle
ONCE per request and passes it — and the FileService built from it — into the use case
factories. The container `logger` is the only declared provider dependency: every
file-path object gets the container's logger singleton.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import structlog.stdlib

from dependency_injector import containers, providers

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.services.file_service import FileService
from src.application.services.memory_bank_service import MemoryBankService
from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.forget_file_use_case import ForgetFileUseCase
from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.domain.config_models import InstancePoolConfig
from src.infrastructure.bank.memory_bank_repository import (
    MemoryBankRepository,
    memory_banks_db_path,
)
from src.infrastructure.bank.router import MemoryBankRouter
from src.infrastructure.config.data_dir import resolve_data_dir
from src.infrastructure.mcp.hash_index_service import HashIndexService
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
from src.tests.test_domain.domain_test_utils import (
    InMemoryMemoryBankRepository,
    InMemoryMemoryRepository,
)
from src.utils.structured_logging import LoggerMock, get_logger


# ---------------------------------------------------------------------------
# Per-bank file-metadata construction (D25)
# ---------------------------------------------------------------------------


@dataclass
class FileMetadataBundle:
    """Per-bank file metadata storage: one connection manager + 3 repositories.

    Built once per request (per memory bank); every file-path object for that
    request shares this bundle so all repositories use a single connection pool.
    """

    connection_manager: FileMetadataConnectionManager
    file_repository: FileRepository
    chunk_repository: FileChunkRepository
    relation_repository: FileRelationRepository


def _build_file_metadata_bundle(bank_dir: Path) -> FileMetadataBundle:
    """Build the per-bank connection manager and the 3 file repositories (D25)."""
    connection_manager = FileMetadataConnectionManager(bank_dir=bank_dir)
    return FileMetadataBundle(
        connection_manager=connection_manager,
        file_repository=FileRepository(connection_manager),
        chunk_repository=FileChunkRepository(connection_manager),
        relation_repository=FileRelationRepository(connection_manager),
    )


def _build_file_service(bundle: FileMetadataBundle, logger: structlog.stdlib.BoundLogger) -> FileService:
    """Build FileService on top of a file metadata bundle with the container logger."""
    return FileService(
        file_repository=bundle.file_repository,
        chunk_repository=bundle.chunk_repository,
        relation_repository=bundle.relation_repository,
        logger=logger,
    )


def _build_expand_file_relations_use_case(
    mnemosyne_client: Callable[[str], dict | None],
    bundle: FileMetadataBundle,
    logger: structlog.stdlib.BoundLogger,
) -> ExpandFileRelationsUseCase:
    """Build ExpandFileRelationsUseCase from one bundle (FileService + relation repo)."""
    return ExpandFileRelationsUseCase(
        mnemosyne_client=mnemosyne_client,
        file_service=_build_file_service(bundle, logger),
        relation_repository=bundle.relation_repository,
        logger=logger,
    )


def _build_hash_index_service(
    memory_bank: str, memory_bank_router: MemoryBankRouter
) -> HashIndexService:
    """Build HashIndexService with the router's canonical hash index path."""
    db_path = memory_bank_router.get_hash_index_path(memory_bank)
    return HashIndexService(memory_bank=memory_bank, db_path=db_path)


def _build_bank_type_checker(
    memory_bank_router: MemoryBankRouter,
) -> Callable[[str], str]:
    """Build the forget-path bank type checker (mirrors router path authority).

    A bank is "file_metadata" if it has file metadata stored (SQLite DB exists),
    otherwise it's "pure_memories". Uniform v2 path for ALL banks incl. default:
    {data_dir}/banks/{bank_name}/file_metadata.db (U11).
    """

    def _checker(bank_name: str) -> str:
        db_path = memory_bank_router.get_file_metadata_path(bank_name)
        return "file_metadata" if db_path.exists() else "pure_memories"

    return _checker


def _build_memory_bank_repository() -> MemoryBankRepository:
    """Build the real SQLAlchemy-backed memory bank repository singleton.

    Resolves the data dir at resolution time (DATA_DIR env / ./data default) so
    the container honors the runtime environment instead of a baked-in path.
    """
    return MemoryBankRepository(memory_banks_db_path(resolve_data_dir()))


class Container(containers.DeclarativeContainer):
    """Base declarative container with common provider definitions."""

    # -- Infrastructure providers --

    logger = providers.Singleton(get_logger, "bensyne")

    # Resolves data_dir at resolution time so the DATA_DIR env (e.g. Docker ENV)
    # or the relative ./data default is honored instead of a baked-in /data.
    memory_bank_router = providers.Singleton(
        MemoryBankRouter,
        config=InstancePoolConfig(),
    )

    # -- Repository providers --

    memory_repository = providers.Singleton(InMemoryMemoryRepository)

    memory_bank_repository = providers.Singleton(_build_memory_bank_repository)

    memory_bank_service = providers.Singleton(
        MemoryBankService,
        memory_bank_repository=memory_bank_repository,
        logger=logger,
    )

    # -- Per-bank file-metadata factories (D25) --
    #
    # Call-time arguments are per-request values (dependency-injector does not
    # forward runtime kwargs to nested factories): a handler resolves the bundle
    # once per request and passes it, plus the FileService built from it, into
    # the use case factories. `logger` is the only provider dependency.

    file_metadata_bundle = providers.Factory(_build_file_metadata_bundle)

    file_service = providers.Factory(_build_file_service, logger=logger)

    file_enrichment_service = providers.Factory(
        FileEnrichmentService,
        logger=logger,
    )

    hash_index_service = providers.Factory(_build_hash_index_service)

    bank_type_checker = providers.Factory(_build_bank_type_checker)

    remember_memory_use_case = providers.Factory(
        RememberMemoryUseCase,
        logger=logger,
    )

    recall_memory_use_case = providers.Factory(
        RecallMemoryUseCase,
        logger=logger,
    )

    forget_memory_use_case = providers.Factory(
        ForgetMemoryUseCase,
        logger=logger,
    )

    # Operator-only file-granular forget: file_service / hash_index_service /
    # mnemosyne_client / memory_bank are per-request call-time arguments (D25),
    # resolved by the handler and passed into the factory.
    forget_file_use_case = providers.Factory(ForgetFileUseCase, logger=logger)

    search_files_use_case = providers.Factory(
        SearchFilesUseCase,
        logger=logger,
    )

    fetch_file_use_case = providers.Factory(
        FetchFileUseCase,
        logger=logger,
    )

    expand_file_relations_use_case = providers.Factory(
        _build_expand_file_relations_use_case,
        logger=logger,
    )


class ProductionContainer(Container):
    """Production container — wires real dependencies.

    Inherits the base Container: the SQLAlchemy-backed MemoryBankRepository
    singleton (memory_banks.db at the resolved data dir) and the
    MemoryBankService wired to it. Test-only fakes live in TestContainer.
    """

    pass


class TestContainer(Container):
    """Test container — wires mock/test-friendly dependencies.

    - Logger: LoggerMock instead of real structlog logger
    - Repositories: in-memory implementations
    - File-metadata factories: re-declared below so their `logger` reference
      binds to LoggerMock (dependency-injector binds provider references by
      object identity, so inherited factories keep the base logger binding)
    """

    logger = providers.Singleton(LoggerMock)

    memory_repository = providers.Singleton(InMemoryMemoryRepository)

    # Test-only fake: the contract's in-memory implementation of the
    # MemoryBankRepository interface (§4.2). Deliberately a different type than
    # the production provider, so mypy's provider-type check needs an ignore.
    memory_bank_repository = providers.Singleton(
        InMemoryMemoryBankRepository  # type: ignore[arg-type]
    )

    memory_bank_service = providers.Singleton(
        MemoryBankService,
        memory_bank_repository=memory_bank_repository,
        logger=logger,
    )

    memory_bank_router = providers.Singleton(
        MemoryBankRouter,
        config=InstancePoolConfig(),
    )

    # -- Per-bank file-metadata factories rebound to LoggerMock --

    file_service = providers.Factory(_build_file_service, logger=logger)

    file_enrichment_service = providers.Factory(FileEnrichmentService, logger=logger)

    remember_memory_use_case = providers.Factory(RememberMemoryUseCase, logger=logger)

    recall_memory_use_case = providers.Factory(RecallMemoryUseCase, logger=logger)

    forget_memory_use_case = providers.Factory(ForgetMemoryUseCase, logger=logger)

    forget_file_use_case = providers.Factory(ForgetFileUseCase, logger=logger)

    search_files_use_case = providers.Factory(SearchFilesUseCase, logger=logger)

    fetch_file_use_case = providers.Factory(FetchFileUseCase, logger=logger)

    expand_file_relations_use_case = providers.Factory(
        _build_expand_file_relations_use_case,
        logger=logger,
    )


def create_test_container() -> TestContainer:
    """Create a TestContainer for use in tests.

    Returns:
        TestContainer with in-memory repos and mock logger.
    """
    return TestContainer()
