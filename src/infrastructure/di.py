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
"""

from __future__ import annotations

from dependency_injector import containers, providers

from src.domain.models import InstancePoolConfig
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.services.bank.router import MemoryBankRouter
from src.tests.test_domain.domain_test_utils import (
    InMemoryMemoryBankRepository,
    InMemoryMemoryRepository,
)
from src.utils.structured_logging import LoggerMock, get_logger


class Container(containers.DeclarativeContainer):
    """Base declarative container with common provider definitions."""

    # -- Infrastructure providers --

    logger = providers.Singleton(get_logger, "bensyne")

    bank_manager = providers.Singleton(
        BankManager,
        data_dir="/data/mnemosyne",
    )

    memory_bank_router = providers.Singleton(
        MemoryBankRouter,
        config=InstancePoolConfig(),
    )

    # -- Repository providers --

    memory_repository = providers.Singleton(InMemoryMemoryRepository)

    memory_bank_repository = providers.Singleton(InMemoryMemoryBankRepository)


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
    """

    logger = providers.Singleton(LoggerMock)

    memory_repository = providers.Singleton(InMemoryMemoryRepository)

    memory_bank_repository = providers.Singleton(InMemoryMemoryBankRepository)

    memory_bank_router = providers.Singleton(
        MemoryBankRouter,
        config=InstancePoolConfig(),
    )


def create_test_container() -> TestContainer:
    """Create a TestContainer for use in tests.

    Returns:
        TestContainer with in-memory repos and mock logger.
    """
    return TestContainer()
