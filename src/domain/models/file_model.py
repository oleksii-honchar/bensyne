"""File validation model using Pydantic."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

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


class FileSchema(BaseModel):
    """Pydantic model for File entity validation."""

    id: str
    path: str = Field(min_length=1)
    source_type: SourceType
    hash: Optional[str] = None
    file_type: Optional[str] = None
    size: Optional[int] = Field(default=None, ge=0)
    language: Optional[str] = None
    aggregated_keywords: List[str] = Field(default_factory=list)
    aggregated_tags: List[str] = Field(default_factory=list)
    status: FileStatus = Field(default=FileStatus.PENDING)
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        result = FileHash.of(v)
        if result.is_ko:
            raise ValueError(f"Invalid file hash: {v}")
        return v
