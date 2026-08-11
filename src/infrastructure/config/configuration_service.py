"""Configuration service using Pydantic BaseSettings.

Provides typed configuration from environment variables and .env files.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Database URL must not be empty")
        return v


class MnemosyneConfig(BaseModel):
    """Mnemosyne service configuration."""

    base_url: str
    timeout: int = 30
    max_retries: int = 3


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    server_name: str = Field(default="bensyne", alias="SERVER_NAME")
    server_version: str = Field(default="1.0.0", alias="SERVER_VERSION")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=3000, alias="SERVER_PORT")

    database_url: str = Field(alias="DATABASE_URL")
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")

    mnemosyne_base_url: str = Field(alias="MNEMOSYNE_BASE_URL")
    mnemosyne_timeout: int = Field(default=30, alias="MNEMOSYNE_TIMEOUT")
    mnemosyne_max_retries: int = Field(default=3, alias="MNEMOSYNE_MAX_RETRIES")

    @property
    def database(self) -> DatabaseConfig:
        """Construct DatabaseConfig from flat env-var fields."""
        return DatabaseConfig(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout=self.database_pool_timeout,
        )

    @property
    def mnemosyne(self) -> MnemosyneConfig:
        """Construct MnemosyneConfig from flat env-var fields."""
        return MnemosyneConfig(
            base_url=self.mnemosyne_base_url,
            timeout=self.mnemosyne_timeout,
            max_retries=self.mnemosyne_max_retries,
        )


class ConfigurationService:
    """Service that provides application configuration.

    Loads settings from environment variables or .env file via
    Pydantic BaseSettings.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    @classmethod
    def from_env(cls) -> "ConfigurationService":
        """Create a ConfigurationService from environment variables or .env file."""
        settings = AppSettings()
        return cls(settings)
