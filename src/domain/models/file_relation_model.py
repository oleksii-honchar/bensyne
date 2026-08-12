"""FileRelation Pydantic model and enums."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RelationType(str, Enum):
    """Types of semantic relationships between files."""

    PARENT_CHILD = "parent_child"
    SIBLING = "sibling"
    BACKLINK = "backlink"
    FOLDER_HIERARCHY = "folder_hierarchy"
    CROSS_REFERENCE = "cross_reference"
    VERSION = "version"
    OVERRIDE = "override"
    DEPENDENCY = "dependency"
    RECOMMENDATION = "recommendation"


class Direction(str, Enum):
    """Directionality of a file relation."""

    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class FileRelationSchema(BaseModel):
    """Pydantic model for FileRelation entity validation."""

    id: str
    source_file_id: str = Field(min_length=1)
    target_file_id: str = Field(min_length=1)
    relation_type: RelationType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    direction: Direction = Field(default=Direction.UNIDIRECTIONAL)
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("source_file_id", "target_file_id")
    @classmethod
    def reject_empty_ids(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("File ID must not be empty")
        return v

    @field_validator("target_file_id")
    @classmethod
    def reject_self_relation(cls, v: str, info) -> str:
        source = info.data.get("source_file_id")
        if source and v == source:
            raise ValueError("source_file_id and target_file_id must be different")
        return v
