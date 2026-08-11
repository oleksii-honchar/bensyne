"""Memory validation model using Pydantic."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MemorySchema(BaseModel):
    """Pydantic model for memory validation."""

    id: str
    content: str = Field(min_length=1)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    source: str = Field(default="conversation")
    scope: str = Field(default="working")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    veracity: Optional[float] = Field(ge=0.0, le=1.0, default=None)
    metadata: Optional[dict] = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        valid_scopes = ["working", "episodic", "semantic", "suspended"]
        if v not in valid_scopes:
            raise ValueError(f"Invalid scope: {v}")
        return v
