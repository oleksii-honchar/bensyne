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
from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.domain.config_models import InstancePoolConfig
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.infrastructure.bank.router import MemoryBankRouter
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


def _build_bank_type_checker(data_dir: Path) -> Callable[[str], str]:
    """Build the forget-path bank type checker (mirrors MnemosyneClient path resolution).

    A bank is "file_metadata" if it has file metadata stored (SQLite DB exists),
    otherwise it's "pure_memories".
    Path resolution:
    - default bank: data_dir/file_metadata.db
    - custom bank:  data_dir/banks/bank_name/file_metadata.db
    """

    def _checker(bank_name: str) -> str:
        if bank_name == "default":
            db_path = data_dir / "file_metadata.db"
        else:
            db_path = data_dir / "banks" / bank_name / "file_metadata.db"
        return "file_metadata" if db_path.exists() else "pure_memories"

    return _checker


class Container(containers.DeclarativeContainer):
    """Base declarative container with common provider definitions."""

    # -- Infrastructure providers --

    logger = providers.Singleton(get_logger, "bensyne")

    bank_manager = providers.Singleton(
        BankManager,
        data_dir="/data",
    )

    memory_bank_router = providers.Singleton(
        MemoryBankRouter,
        config=InstancePoolConfig(),
    )

    # -- Repository providers --

    memory_repository = providers.Singleton(InMemoryMemoryRepository)

    memory_bank_repository = providers.Singleton(InMemoryMemoryBankRepository)

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

    hash_index_service = providers.Factory(HashIndexService)

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

    Repositories default to in-memory implementations here as placeholders.
    Replace with SQLAlchemy-backed implementations when Task 17+ is complete.
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

    memory_bank_repository = providers.Singleton(InMemoryMemoryBankRepository)

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
