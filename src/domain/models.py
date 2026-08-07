"""Data models and schemas."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ServerConfig:
    """Server configuration."""

    name: str = "bensyne"
    version: str = "1.0.0"
    transport: str = "streamable-http"
    host: str = "0.0.0.0"
    port: int = 3000


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"  # noqa: A003
    log_file: Optional[str] = None


@dataclass(frozen=True)
class InstancePoolConfig:
    """Instance pool configuration."""

    max_instances: int = 50
    eviction_timeout: int = 300
    data_dir: str = "/data/mnemosyne/data"
    default_bank: str = "default"


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration."""

    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    instance_pool: InstancePoolConfig = field(default_factory=InstancePoolConfig)


@dataclass(frozen=True)
class MemoryBankInfo:
    """Memory bank information for list_banks and registry state."""

    name: str
    bank: str
    status: str
    memory_count: int
    created_at: str
    last_accessed: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "bank": self.bank,
            "status": self.status,
            "memory_count": self.memory_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
        }


@dataclass(frozen=True)
class InstanceInfo:
    """Instance information for a running Mnemosyne instance."""

    memory_bank: str
    db_path: str
    status: str
    created_at: float
    last_accessed: float

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "memory_bank": self.memory_bank,
            "db_path": self.db_path,
            "status": self.status,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
        }


@dataclass(frozen=True)
class ToolResponse:
    """Standardized response from MCP tool operations."""

    status: str
    data: Optional[dict] = None
    memory_bank: str = "default"
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "status": self.status,
            "data": self.data,
            "memory_bank": self.memory_bank,
            "error": self.error,
        }
