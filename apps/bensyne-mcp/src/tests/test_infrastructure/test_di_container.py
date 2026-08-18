"""DI Container tests — container wiring and override capability.

Verifies:
- Container provides correct singleton instances for infrastructure dependencies
- Container supports overriding providers for test isolation
- Container wires up repository implementations (in-memory for test, database for production)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dependency_injector import providers

from src.infrastructure.di import (
    Container,
    ProductionContainer,
    TestContainer,
    create_test_container,
)


class TestProductionContainerSingletons:
    """ProductionContainer provides correct singleton instances."""

    def test_logger_is_singleton(self) -> None:
        """Logger provider returns the same instance on repeated calls."""
        container = ProductionContainer()
        logger1 = container.logger()
        logger2 = container.logger()
        assert logger1 is logger2

    def test_bank_manager_is_singleton(self) -> None:
        """BankManager provider returns the same instance on repeated calls."""
        container = ProductionContainer()
        bm1 = container.bank_manager()
        bm2 = container.bank_manager()
        assert bm1 is bm2

    def test_memory_bank_router_is_singleton(self) -> None:
        """MemoryBankRouter provider returns the same instance on repeated calls."""
        from unittest.mock import patch

        container = ProductionContainer()
        # Router creates a real Mnemosyne instance on init; mock the client to avoid
        # hitting the real library in unit tests.
        with patch("src.infrastructure.bank.router.MnemosyneClient"):
            r1 = container.memory_bank_router()
            r2 = container.memory_bank_router()
            assert r1 is r2

    def test_memory_repository_is_singleton(self) -> None:
        """MemoryRepository provider returns the same instance on repeated calls."""
        container = ProductionContainer()
        repo1 = container.memory_repository()
        repo2 = container.memory_repository()
        assert repo1 is repo2

    def test_memory_bank_repository_is_singleton(self) -> None:
        """MemoryBankRepository provider returns the same instance on repeated calls."""
        container = ProductionContainer()
        repo1 = container.memory_bank_repository()
        repo2 = container.memory_bank_repository()
        assert repo1 is repo2

    def test_providers_return_correct_types(self) -> None:
        """Each provider returns the expected type."""
        from unittest.mock import patch

        from src.infrastructure.mnemosyne.bank_manager import BankManager
        from src.infrastructure.bank.router import MemoryBankRouter
        from src.tests.test_domain.domain_test_utils import (
            InMemoryMemoryBankRepository,
            InMemoryMemoryRepository,
        )

        container = ProductionContainer()

        # logger — structlog BoundLogger has info method
        logger = container.logger()
        assert hasattr(logger, "info")

        # bank_manager
        bm = container.bank_manager()
        assert isinstance(bm, BankManager)

        # memory_bank_router — mock MnemosyneClient to avoid real library init
        with patch("src.infrastructure.bank.router.MnemosyneClient"):
            router = container.memory_bank_router()
            assert isinstance(router, MemoryBankRouter)

        # memory_repository — production container uses in-memory as default
        repo = container.memory_repository()
        assert isinstance(repo, InMemoryMemoryRepository)

        # memory_bank_repository
        bank_repo = container.memory_bank_repository()
        assert isinstance(bank_repo, InMemoryMemoryBankRepository)


class TestContainerOverride:
    """Container supports overriding providers for test isolation."""

    def test_override_logger_with_mock(self) -> None:
        """Overriding logger provider replaces the default with a mock."""
        container = ProductionContainer()
        mock_logger = MagicMock()

        with container.override_providers(logger=providers.Singleton(lambda: mock_logger)):
            logger = container.logger()
            assert logger is mock_logger

        # After override context, original provider is restored
        restored = container.logger()
        assert restored is not mock_logger

    def test_override_memory_repository_with_mock(self) -> None:
        """Overriding memory_repository provider replaces with a mock."""
        container = ProductionContainer()
        mock_repo = MagicMock()

        with container.override_providers(memory_repository=providers.Singleton(lambda: mock_repo)):
            repo = container.memory_repository()
            assert repo is mock_repo

        # After override context, original provider is restored
        restored = container.memory_repository()
        assert restored is not mock_repo

    def test_override_multiple_providers(self) -> None:
        """Multiple providers can be overridden simultaneously."""
        container = ProductionContainer()
        mock_logger = MagicMock()
        mock_repo = MagicMock()

        with container.override_providers(
            logger=providers.Singleton(lambda: mock_logger),
            memory_repository=providers.Singleton(lambda: mock_repo),
        ):
            assert container.logger() is mock_logger
            assert container.memory_repository() is mock_repo

        # Both restored
        assert container.logger() is not mock_logger
        assert container.memory_repository() is not mock_repo


class TestTestContainerProviders:
    """TestContainer provides test-friendly defaults with in-memory repos."""

    def test_test_container_provides_in_memory_repos(self) -> None:
        """TestContainer wires in-memory repositories by default."""
        container = TestContainer()

        from src.tests.test_domain.domain_test_utils import (
            InMemoryMemoryBankRepository,
            InMemoryMemoryRepository,
        )

        repo = container.memory_repository()
        assert isinstance(repo, InMemoryMemoryRepository)

        bank_repo = container.memory_bank_repository()
        assert isinstance(bank_repo, InMemoryMemoryBankRepository)

    def test_create_test_container_returns_container(self) -> None:
        """create_test_container() returns a container with test providers."""
        container = create_test_container()
        # dependency-injector wraps DeclarativeContainer in DynamicContainer,
        # so we check the declarative_parent instead of isinstance
        assert container.declarative_parent is TestContainer

    def test_test_container_logger_is_mock(self) -> None:
        """TestContainer provides a mock logger by default."""
        container = TestContainer()
        logger = container.logger()
        assert hasattr(logger, "info")  # LoggerMock has info method

    def test_test_container_logger_is_logger_mock(self) -> None:
        """TestContainer logger is LoggerMock instance."""
        from src.utils.structured_logging import LoggerMock

        container = TestContainer()
        logger = container.logger()
        assert isinstance(logger, LoggerMock)


# ---------------------------------------------------------------------------
# Per-bank file-metadata factories (D25) — wiring and single-instance identity
# ---------------------------------------------------------------------------


class TestFileMetadataBundleFactory:
    """file_metadata_bundle builds one connection manager + 3 repositories per bank."""

    def test_bundle_resolves_storage_objects(self, tmp_path) -> None:
        """Bundle resolves a connection manager and the 3 file repositories."""
        from src.infrastructure.di import FileMetadataBundle
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

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")

        assert isinstance(bundle, FileMetadataBundle)
        assert isinstance(bundle.connection_manager, FileMetadataConnectionManager)
        assert isinstance(bundle.file_repository, FileRepository)
        assert isinstance(bundle.chunk_repository, FileChunkRepository)
        assert isinstance(bundle.relation_repository, FileRelationRepository)

    def test_bundle_shares_single_connection_manager(self, tmp_path) -> None:
        """All 3 repositories are wired to the bundle's single connection manager."""
        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")

        assert bundle.file_repository._conn_manager is bundle.connection_manager
        assert bundle.chunk_repository._conn_manager is bundle.connection_manager
        assert bundle.relation_repository._conn_manager is bundle.connection_manager


class TestFileServiceFactory:
    """file_service builds FileService from a bundle with the container logger."""

    def test_file_service_reuses_bundle_repositories(self, tmp_path) -> None:
        """FileService gets the exact repository instances from the bundle."""
        from src.application.services.file_service import FileService

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        service = container.file_service(bundle=bundle)

        assert isinstance(service, FileService)
        assert service.file_repository is bundle.file_repository
        assert service.chunk_repository is bundle.chunk_repository
        assert service.relation_repository is bundle.relation_repository

    def test_file_service_uses_container_logger(self, tmp_path) -> None:
        """FileService logger is the container's logger singleton."""
        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        service = container.file_service(bundle=bundle)

        assert service._logger is container.logger()


class TestFileUseCaseFactories:
    """Use case factories produce use cases wired to the same container objects."""

    def test_fetch_file_use_case_shares_injected_file_service(self, tmp_path) -> None:
        """fetch_file_use_case injects the exact FileService instance given."""
        from src.application.use_cases.fetch_file_use_case import FetchFileUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        instance = MagicMock()

        use_case = container.fetch_file_use_case(mnemosyne_client=instance, file_service=file_service)

        assert isinstance(use_case, FetchFileUseCase)
        assert use_case.file_service is file_service
        assert use_case.mnemosyne_client is instance

    def test_remember_memory_use_case_shares_container_objects(self, tmp_path) -> None:
        """remember_memory_use_case shares the FileService and hash index service instances."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        hash_index_service = container.hash_index_service(memory_bank="bank")
        instance = MagicMock()

        use_case = container.remember_memory_use_case(
            memory_repository=instance,
            hash_index_service=hash_index_service,
            file_service=file_service,
        )

        assert isinstance(use_case, RememberMemoryUseCase)
        assert use_case.file_service is file_service
        assert use_case.hash_index_service is hash_index_service
        assert use_case.memory_repository is instance

    def test_recall_memory_use_case_shares_enrichment_service(self, tmp_path) -> None:
        """recall_memory_use_case shares the FileEnrichmentService instance."""
        from src.application.services.file_enrichment_service import FileEnrichmentService
        from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        enrichment = container.file_enrichment_service(file_service=file_service)
        instance = MagicMock()

        use_case = container.recall_memory_use_case(
            mnemosyne_client=instance,
            file_enrichment_service=enrichment,
        )

        assert isinstance(use_case, RecallMemoryUseCase)
        assert use_case.file_enrichment_service is enrichment
        assert enrichment._file_service is file_service

    def test_forget_memory_use_case_shares_container_objects(self, tmp_path) -> None:
        """forget_memory_use_case shares FileService, hash index and bank type checker."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        hash_index_service = container.hash_index_service(memory_bank="bank")
        checker = container.bank_type_checker(data_dir=tmp_path)
        instance = MagicMock()

        use_case = container.forget_memory_use_case(
            mnemosyne_client=instance,
            hash_index_service=hash_index_service,
            file_service=file_service,
            bank_type_checker=checker,
        )

        assert isinstance(use_case, ForgetMemoryUseCase)
        assert use_case.file_service is file_service
        assert use_case.hash_index_service is hash_index_service
        assert use_case.bank_type_checker is checker

    def test_search_files_use_case_shares_injected_file_service(self, tmp_path) -> None:
        """search_files_use_case injects the exact FileService instance given."""
        from src.application.use_cases.search_files_use_case import SearchFilesUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        instance = MagicMock()

        use_case = container.search_files_use_case(mnemosyne_client=instance, file_service=file_service)

        assert isinstance(use_case, SearchFilesUseCase)
        assert use_case.file_service is file_service

    def test_expand_file_relations_use_case_shares_bundle_relation_repository(self, tmp_path) -> None:
        """expand_file_relations_use_case wires FileService and relation repo from one bundle."""
        from src.application.use_cases.expand_file_relations_use_case import (
            ExpandFileRelationsUseCase,
        )

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        instance = MagicMock()

        use_case = container.expand_file_relations_use_case(mnemosyne_client=instance, bundle=bundle)

        assert isinstance(use_case, ExpandFileRelationsUseCase)
        assert use_case.relation_repository is bundle.relation_repository
        # FileService must come from the SAME bundle (single connection manager)
        assert use_case.file_service.file_repository is bundle.file_repository
        assert use_case.file_service.chunk_repository is bundle.chunk_repository


class TestFileMetadataSupportFactories:
    """hash_index_service and bank_type_checker factories."""

    def test_hash_index_service_factory(self) -> None:
        """hash_index_service factory builds a HashIndexService for the bank."""
        from src.infrastructure.mcp.hash_index_service import HashIndexService

        container = ProductionContainer()
        service = container.hash_index_service(memory_bank="bank")

        assert isinstance(service, HashIndexService)
        assert service.memory_bank == "bank"

    def test_bank_type_checker_detects_file_metadata_banks(self, tmp_path) -> None:
        """bank_type_checker returns file_metadata when the bank DB exists."""
        container = ProductionContainer()
        bank_db = tmp_path / "banks" / "bank-a" / "file_metadata.db"
        bank_db.parent.mkdir(parents=True)
        bank_db.touch()

        checker = container.bank_type_checker(data_dir=tmp_path)

        assert checker("bank-a") == "file_metadata"
        assert checker("unknown-bank") == "pure_memories"

    def test_bank_type_checker_default_bank_path(self, tmp_path) -> None:
        """Default bank resolves file_metadata.db at the data_dir root."""
        container = ProductionContainer()
        (tmp_path / "file_metadata.db").touch()

        checker = container.bank_type_checker(data_dir=tmp_path)

        assert checker("default") == "file_metadata"


class TestTestContainerFileFactories:
    """TestContainer inherits the file-metadata factories with the mock logger."""

    def test_test_container_file_service_uses_mock_logger(self, tmp_path) -> None:
        """TestContainer file_service wires the LoggerMock singleton."""
        from src.utils.structured_logging import LoggerMock

        container = TestContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        service = container.file_service(bundle=bundle)

        assert service._logger is container.logger()
        assert isinstance(service._logger, LoggerMock)

    def test_test_container_use_case_factories_resolve(self, tmp_path) -> None:
        """TestContainer use case factories resolve with mock logger."""
        from src.application.use_cases.fetch_file_use_case import FetchFileUseCase

        container = TestContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        instance = MagicMock()

        use_case = container.fetch_file_use_case(mnemosyne_client=instance, file_service=file_service)

        assert isinstance(use_case, FetchFileUseCase)
        assert use_case.file_service is file_service
