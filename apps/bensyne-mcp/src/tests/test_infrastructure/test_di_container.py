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
