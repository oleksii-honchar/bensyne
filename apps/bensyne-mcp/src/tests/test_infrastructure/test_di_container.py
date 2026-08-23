"""DI Container tests — container wiring and override capability.

Verifies:
- Container provides correct singleton instances for infrastructure dependencies
- Container supports overriding providers for test isolation
- Container wires up repository implementations (in-memory for test, database for production)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import providers

from src.infrastructure.di import (
    Container,
    ProductionContainer,
    TestContainer,
    create_test_container,
)


@pytest.fixture
def router(tmp_path) -> "MemoryBankRouter":
    """MemoryBankRouter with a temp data_dir (MnemosyneClient mocked)."""
    from src.domain.config_models import InstancePoolConfig
    from src.infrastructure.bank.router import MemoryBankRouter

    with patch("src.infrastructure.bank.router.MnemosyneClient"):
        yield MemoryBankRouter(InstancePoolConfig(data_dir=str(tmp_path)))


class TestProductionContainerSingletons:
    """ProductionContainer provides correct singleton instances."""

    def test_logger_is_singleton(self) -> None:
        """Logger provider returns the same instance on repeated calls."""
        container = ProductionContainer()
        logger1 = container.logger()
        logger2 = container.logger()
        assert logger1 is logger2

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

    def test_memory_bank_repository_is_singleton(self, tmp_path, monkeypatch) -> None:
        """MemoryBankRepository provider returns the same instance on repeated calls."""
        # Real repository resolves DATA_DIR at resolution time — point it at a
        # temp dir so the test never touches the app's ./data (must stay clean).
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        repo1 = container.memory_bank_repository()
        repo2 = container.memory_bank_repository()
        assert repo1 is repo2

    def test_providers_return_correct_types(self, tmp_path, monkeypatch) -> None:
        """Each provider returns the expected type."""
        from unittest.mock import patch

        from src.infrastructure.bank.memory_bank_repository import MemoryBankRepository
        from src.infrastructure.bank.router import MemoryBankRouter
        from src.tests.test_domain.domain_test_utils import InMemoryMemoryRepository

        # Real repository resolves DATA_DIR at resolution time — temp dir only.
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()

        # logger — structlog BoundLogger has info method
        logger = container.logger()
        assert hasattr(logger, "info")

        # memory_bank_router — mock MnemosyneClient to avoid real library init
        with patch("src.infrastructure.bank.router.MnemosyneClient"):
            router = container.memory_bank_router()
            assert isinstance(router, MemoryBankRouter)

        # memory_repository — production container uses in-memory as default
        repo = container.memory_repository()
        assert isinstance(repo, InMemoryMemoryRepository)

        # memory_bank_repository — real SQLAlchemy-backed repository (Task 8),
        # NOT the test fake.
        bank_repo = container.memory_bank_repository()
        assert isinstance(bank_repo, MemoryBankRepository)


class TestMemoryBankServiceProvider:
    """memory_bank_service provider wiring (Task 8 — real repo + service singletons)."""

    def test_production_service_wired_to_real_repository(self, tmp_path, monkeypatch) -> None:
        """ProductionContainer memory_bank_service binds the real repository singleton."""
        from src.application.services.memory_bank_service import MemoryBankService
        from src.infrastructure.bank.memory_bank_repository import MemoryBankRepository

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        service = container.memory_bank_service()

        assert isinstance(service, MemoryBankService)
        assert isinstance(service.memory_bank_repository, MemoryBankRepository)
        assert service.memory_bank_repository is container.memory_bank_repository()

    def test_production_repository_db_path_matches_helper(self, tmp_path, monkeypatch) -> None:
        """Production repository DB file == memory_banks_db_path(resolve_data_dir())."""
        from src.infrastructure.bank.memory_bank_repository import (
            MemoryBankRepository,
            memory_banks_db_path,
        )
        from src.infrastructure.config.data_dir import resolve_data_dir

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        repo = container.memory_bank_repository()

        assert isinstance(repo, MemoryBankRepository)
        assert repo._db_path == memory_banks_db_path(resolve_data_dir())
        assert repo._db_path == Path(tmp_path) / "memory_banks.db"

    def test_memory_bank_service_is_singleton(self, tmp_path, monkeypatch) -> None:
        """memory_bank_service provider returns the same instance on repeated calls."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        assert container.memory_bank_service() is container.memory_bank_service()

    def test_test_container_service_uses_fake_repo_and_mock_logger(self) -> None:
        """TestContainer keeps the in-memory fake and binds LoggerMock."""
        from src.application.services.memory_bank_service import MemoryBankService
        from src.tests.test_domain.domain_test_utils import (
            InMemoryMemoryBankRepository,
        )
        from src.utils.structured_logging import LoggerMock

        container = TestContainer()
        service = container.memory_bank_service()

        assert isinstance(service, MemoryBankService)
        assert isinstance(service.memory_bank_repository, InMemoryMemoryBankRepository)
        assert service._logger is container.logger()
        assert isinstance(service._logger, LoggerMock)


class TestProductionBootstrap:
    """Integration-style: ProductionContainer + temp DATA_DIR bootstraps the v2 tree.

    Mirrors the main.py startup seed (config → container → ensure_default_bank)
    against a temp DATA_DIR so the app's real ./data dir stays clean.
    """

    DEFAULT_DESC = "Default personal memory — general conversation context, preferences, and facts"

    def test_ensure_default_bank_bootstraps_db_with_default_row(
        self, tmp_path, monkeypatch
    ) -> None:
        """Seeding creates memory_banks.db and a 'default' row."""
        from src.infrastructure.bank.memory_bank_repository import memory_banks_db_path

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        container.memory_bank_service().ensure_default_bank(self.DEFAULT_DESC)

        assert memory_banks_db_path(tmp_path).exists()

        bank = container.memory_bank_service().get_memory_bank("default").value
        assert bank is not None
        assert bank.name == "default"
        assert bank.description == self.DEFAULT_DESC
        assert bank.status == "registered"

    def test_ensure_default_bank_twice_does_not_duplicate_or_overwrite(
        self, tmp_path, monkeypatch
    ) -> None:
        """Calling twice with a different description keeps one row, original text."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        service = container.memory_bank_service()

        service.ensure_default_bank(self.DEFAULT_DESC)
        service.ensure_default_bank("a different startup description")

        banks = service.list_memory_banks().value
        assert banks is not None
        assert [b.name for b in banks] == ["default"]
        assert banks[0].description == self.DEFAULT_DESC

    def test_seed_produces_v2_tree_only(self, tmp_path, monkeypatch) -> None:
        """Seed creates data/memory_banks.db only; banks/default/ is lazy.

        No root data/mnemosyne.db, no data/default/ — the bank dir appears only
        when the router's write path is first used (get_bank_db_path).
        """
        from src.infrastructure.bank.memory_bank_repository import memory_banks_db_path

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        container = ProductionContainer()
        container.memory_bank_service().ensure_default_bank(self.DEFAULT_DESC)

        assert memory_banks_db_path(tmp_path).exists()
        assert not (tmp_path / "banks").exists()
        assert not (tmp_path / "mnemosyne.db").exists()
        assert not (tmp_path / "default").exists()

        # Lazy v2 creation via the router path authority on first client use.
        from unittest.mock import patch

        from src.domain.config_models import InstancePoolConfig
        from src.infrastructure.bank.router import MemoryBankRouter

        with patch("src.infrastructure.bank.router.MnemosyneClient"):
            tmp_router = MemoryBankRouter(InstancePoolConfig(data_dir=str(tmp_path)))
            db_path = tmp_router.get_bank_db_path("default")
            assert db_path == tmp_path / "banks" / "default" / "mnemosyne.db"
            assert db_path.parent.exists()


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

    def test_remember_memory_use_case_shares_container_objects(
        self, tmp_path, router
    ) -> None:
        """remember_memory_use_case shares the FileService and hash index service instances."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        hash_index_service = container.hash_index_service(
            memory_bank="bank", memory_bank_router=router
        )
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

    def test_forget_memory_use_case_shares_container_objects(
        self, tmp_path, router
    ) -> None:
        """forget_memory_use_case shares FileService, hash index and bank type checker."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase

        container = ProductionContainer()
        bundle = container.file_metadata_bundle(bank_dir=tmp_path / "bank")
        file_service = container.file_service(bundle=bundle)
        hash_index_service = container.hash_index_service(
            memory_bank="bank", memory_bank_router=router
        )
        checker = container.bank_type_checker(memory_bank_router=router)
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

    def test_hash_index_service_factory_uses_router_path(self, router) -> None:
        """hash_index_service factory builds a HashIndexService whose DB lands
        at router.get_hash_index_path(bank)."""
        from src.infrastructure.mcp.hash_index_service import HashIndexService

        container = ProductionContainer()
        service = container.hash_index_service(
            memory_bank="foo", memory_bank_router=router
        )

        assert isinstance(service, HashIndexService)
        assert service.memory_bank == "foo"
        expected = router.get_hash_index_path("foo")
        assert service._conn._db_path == expected

        service.store("sha256_di", "mem_di")
        assert expected.exists()
        assert expected == Path(router.config.data_dir) / "banks" / "foo" / "hash_index.db"

    def test_bank_type_checker_detects_file_metadata_banks(self, router) -> None:
        """bank_type_checker returns file_metadata when the bank DB exists."""
        container = ProductionContainer()
        bank_db = router.get_file_metadata_path("bank-a")
        bank_db.parent.mkdir(parents=True)
        bank_db.touch()

        checker = container.bank_type_checker(memory_bank_router=router)

        assert checker("bank-a") == "file_metadata"
        assert checker("unknown-bank") == "pure_memories"

    def test_bank_type_checker_default_bank_uniform_path(self, router) -> None:
        """Default bank resolves under banks/ (v2 uniform) — file_metadata.db
        at the data_dir root no longer counts."""
        container = ProductionContainer()
        # Old-layout root db must NOT make the default bank "file_metadata".
        (Path(router.config.data_dir) / "file_metadata.db").touch()

        checker = container.bank_type_checker(memory_bank_router=router)

        assert checker("default") == "pure_memories"

        # v2 uniform layout: banks/default/file_metadata.db DOES.
        default_db = router.get_file_metadata_path("default")
        default_db.parent.mkdir(parents=True)
        default_db.touch()
        assert checker("default") == "file_metadata"

    def test_bank_type_checker_uses_router_for_custom_bank(self, router) -> None:
        """Custom banks resolve via the router path authority (same method)."""
        container = ProductionContainer()
        custom_db = router.get_file_metadata_path("custom")
        custom_db.parent.mkdir(parents=True)
        custom_db.touch()

        checker = container.bank_type_checker(memory_bank_router=router)

        assert checker("custom") == "file_metadata"
        assert checker("default") == "pure_memories"


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
