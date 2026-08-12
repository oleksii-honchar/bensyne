"""FileChunk validation model using Pydantic."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from src.domain.value_objects.file_hash import FileHash


class ContentType(str, Enum):
    """Content type classification for file chunks."""

    TEXT = "text"
    CODE = "code"
    CONFIG = "config"
    IMAGE = "image"
    BINARY = "binary"
    UNKNOWN = "unknown"


class FileChunkSchema(BaseModel):
    """Pydantic model for FileChunk entity validation."""

    id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)
    memory_id: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    start_line: int = Field(default=0, ge=0)
    end_line: int = Field(default=0, ge=0)
    content_hash: str | None = None
    content_type: ContentType = Field(default=ContentType.UNKNOWN)
    is_partial: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, v: str | None) -> str | None:
        if v is None:
            return v
        result = FileHash.of(v)
        if result.is_ko:
            raise ValueError(f"Invalid content hash: {v}")
        return v

    @model_validator(mode="after")
    def validate_line_range(self) -> "FileChunkSchema":
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line})"
            )
        return self
