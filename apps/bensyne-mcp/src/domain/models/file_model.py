"""File validation model using Pydantic."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from src.domain.value_objects.file_hash import FileHash


class FileStatus(str, Enum):
    """File lifecycle status."""

    PENDING = "pending"
    INDEXED = "indexed"
    ARCHIVED = "archived"
    DELETED = "deleted"


class SourceType(str, Enum):
    """Source type classification for files."""

    AGENT_SESSION = "agent_session"
    FILE_SYSTEM = "file_system"
    GIT = "git"
    DATABASE = "database"
    EXTERNAL = "external"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class FileRole(str, Enum):
    """File role classification (mirrors the contract v1 ``file_role`` values)."""

    CONFIG = "config"
    CODE = "code"
    DOCS = "docs"


class FileSchema(BaseModel):
    """Pydantic model for File entity validation."""

    id: str
    path: str = Field(min_length=1)
    source_type: SourceType
    file_role: FileRole | None = None
    hash: str | None = None
    file_type: str | None = None
    size: int | None = Field(default=None, ge=0)
    language: str | None = None
    aggregated_keywords: list[str] = Field(default_factory=list)
    aggregated_tags: list[str] = Field(default_factory=list)
    status: FileStatus = Field(default=FileStatus.PENDING)
    summary: str | None = None
    total_chunks: int = Field(default=0, ge=0)
    average_importance: float = Field(default=0.5, gt=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, v: str | None) -> str | None:
        if v is None:
            return v
        result = FileHash.of(v)
        if result.is_ko:
            raise ValueError(f"Invalid file hash: {v}")
        return v
