"""ConfigurationService and Pydantic settings tests.

Verifies:
- AppSettings loads default values when no env vars set
- DatabaseConfig validates URL format
- MnemosyneConfig has correct fields and defaults
- ConfigurationService.from_env() reads from environment/.env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from src.infrastructure.config.configuration_service import (
    AppSettings,
    ConfigurationService,
    DatabaseConfig,
    MnemosyneConfig,
)


# ---------------------------------------------------------------------------
# AppSettings defaults
# ---------------------------------------------------------------------------


class TestAppSettingsDefaults:
    """AppSettings loads default values when no env vars set."""

    def test_default_server_name(self) -> None:
        """server_name defaults to 'bensyne'."""
        settings = AppSettings(
            database_url="sqlite:///:memory:",
            mnemosyne_base_url="http://localhost:8000",
        )
        assert settings.server_name == "bensyne"

    def test_default_server_version(self) -> None:
        """server_version defaults to '1.0.0'."""
        settings = AppSettings(
            database_url="sqlite:///:memory:",
            mnemosyne_base_url="http://localhost:8000",
        )
        assert settings.server_version == "1.0.0"

    def test_default_host(self) -> None:
        """host defaults to '0.0.0.0'."""
        settings = AppSettings(
            database_url="sqlite:///:memory:",
            mnemosyne_base_url="http://localhost:8000",
        )
        assert settings.host == "0.0.0.0"

    def test_default_port(self) -> None:
        """port defaults to 3000."""
        settings = AppSettings(
            database_url="sqlite:///:memory:",
            mnemosyne_base_url="http://localhost:8000",
        )
        assert settings.port == 3000

    def test_custom_values(self) -> None:
        """AppSettings accepts custom values for all fields."""
        settings = AppSettings(
            server_name="custom",
            server_version="2.0.0",
            host="127.0.0.1",
            port=8080,
            database_url="sqlite:///:memory:",
            mnemosyne_base_url="http://localhost:8000",
        )
        assert settings.server_name == "custom"
        assert settings.server_version == "2.0.0"
        assert settings.host == "127.0.0.1"
        assert settings.port == 8080

    def test_nested_configs(self) -> None:
        """AppSettings composes DatabaseConfig and MnemosyneConfig via properties."""
        settings = AppSettings(
            database_url="sqlite:///:memory:",
            database_pool_size=5,
            mnemosyne_base_url="http://localhost:9000",
            mnemosyne_timeout=60,
        )

        assert settings.database.url == "sqlite:///:memory:"
        assert settings.database.pool_size == 5
        assert settings.mnemosyne.base_url == "http://localhost:9000"
        assert settings.mnemosyne.timeout == 60


# ---------------------------------------------------------------------------
# DatabaseConfig
# ---------------------------------------------------------------------------


class TestDatabaseConfig:
    """DatabaseConfig has correct fields, defaults, and validation."""

    def test_default_pool_values(self) -> None:
        """DatabaseConfig uses default pool values."""
        db = DatabaseConfig(url="sqlite:///:memory:")
        assert db.pool_size == 10
        assert db.max_overflow == 20
        assert db.pool_timeout == 30

    def test_custom_pool_values(self) -> None:
        """DatabaseConfig accepts custom pool values."""
        db = DatabaseConfig(
            url="sqlite:///:memory:",
            pool_size=5,
            max_overflow=10,
            pool_timeout=15,
        )
        assert db.pool_size == 5
        assert db.max_overflow == 10
        assert db.pool_timeout == 15

    def test_validates_url_format(self) -> None:
        """DatabaseConfig requires a non-empty URL."""
        with pytest.raises(ValidationError):
            DatabaseConfig(url="")

    def test_requires_url(self) -> None:
        """DatabaseConfig requires url field."""
        with pytest.raises(ValidationError):
            DatabaseConfig()  # type: ignore[call-arg]

    def test_accepts_sqlite_url(self) -> None:
        """DatabaseConfig accepts sqlite URL format."""
        db = DatabaseConfig(url="sqlite:///test.db")
        assert db.url == "sqlite:///test.db"

    def test_accepts_postgres_url(self) -> None:
        """DatabaseConfig accepts postgres URL format."""
        db = DatabaseConfig(url="postgresql://user:pass@localhost:5432/db")
        assert db.url == "postgresql://user:pass@localhost:5432/db"


# ---------------------------------------------------------------------------
# MnemosyneConfig
# ---------------------------------------------------------------------------


class TestMnemosyneConfig:
    """MnemosyneConfig has correct fields and defaults."""

    def test_default_timeout(self) -> None:
        """MnemosyneConfig defaults timeout to 30."""
        mn = MnemosyneConfig(base_url="http://localhost:8000")
        assert mn.timeout == 30

    def test_default_max_retries(self) -> None:
        """MnemosyneConfig defaults max_retries to 3."""
        mn = MnemosyneConfig(base_url="http://localhost:8000")
        assert mn.max_retries == 3

    def test_custom_values(self) -> None:
        """MnemosyneConfig accepts custom values."""
        mn = MnemosyneConfig(
            base_url="http://localhost:9000",
            timeout=60,
            max_retries=5,
        )
        assert mn.base_url == "http://localhost:9000"
        assert mn.timeout == 60
        assert mn.max_retries == 5

    def test_requires_base_url(self) -> None:
        """MnemosyneConfig requires base_url field."""
        with pytest.raises(ValidationError):
            MnemosyneConfig()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ConfigurationService
# ---------------------------------------------------------------------------


class TestConfigurationService:
    """ConfigurationService.from_env() reads from environment/.env."""

    def test_from_env_returns_service(self) -> None:
        """from_env() returns a ConfigurationService instance."""
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["MNEMOSYNE_BASE_URL"] = "http://localhost:8000"
        try:
            svc = ConfigurationService.from_env()
            assert isinstance(svc, ConfigurationService)
            assert isinstance(svc.settings, AppSettings)
        finally:
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("MNEMOSYNE_BASE_URL", None)

    def test_from_env_reads_env_vars(self) -> None:
        """from_env() reads values from environment variables."""
        os.environ["SERVER_NAME"] = "custom_server"
        os.environ["SERVER_PORT"] = "9999"
        os.environ["DATABASE_URL"] = "sqlite:///test.db"
        os.environ["MNEMOSYNE_BASE_URL"] = "http://localhost:8000"
        try:
            svc = ConfigurationService.from_env()
            assert svc.settings.server_name == "custom_server"
            assert svc.settings.port == 9999
            assert svc.settings.database.url == "sqlite:///test.db"
            assert svc.settings.mnemosyne.base_url == "http://localhost:8000"
        finally:
            for key in ["SERVER_NAME", "SERVER_PORT", "DATABASE_URL", "MNEMOSYNE_BASE_URL"]:
                os.environ.pop(key, None)

    def test_from_env_reads_dotenv(self, tmp_path: Path) -> None:
        """from_env() reads from .env file when env vars are not set."""
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "SERVER_NAME=dotenv_server\n"
            "SERVER_PORT=7777\n"
            "DATABASE_URL=sqlite:///dotenv.db\n"
            "MNEMOSYNE_BASE_URL=http://localhost:8000\n"
        )

        # Ensure no conflicting env vars
        for key in ["SERVER_NAME", "SERVER_PORT", "DATABASE_URL", "MNEMOSYNE_BASE_URL"]:
            os.environ.pop(key, None)

        # Create a subclass that points to our .env file
        class TestAppSettings(AppSettings):
            model_config = SettingsConfigDict(
                env_file=str(dotenv_path),
                env_file_encoding="utf-8",
                extra="ignore",
            )

        class TestConfigurationService(ConfigurationService):
            @classmethod
            def from_env(cls) -> "TestConfigurationService":
                settings = TestAppSettings()
                return cls(settings)

        svc = TestConfigurationService.from_env()

        assert svc.settings.server_name == "dotenv_server"
        assert svc.settings.port == 7777
        assert svc.settings.database.url == "sqlite:///dotenv.db"
        assert svc.settings.mnemosyne.base_url == "http://localhost:8000"

    def test_settings_exposed_on_service(self) -> None:
        """ConfigurationService exposes settings attribute."""
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["MNEMOSYNE_BASE_URL"] = "http://localhost:8000"
        try:
            svc = ConfigurationService.from_env()
            assert svc.settings.server_name == "bensyne"
            assert svc.settings.server_version == "1.0.0"
        finally:
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("MNEMOSYNE_BASE_URL", None)
