"""API request/response models for memory operations."""

from typing import Any

from pydantic import BaseModel, Field


class MemoryOperationRequest(BaseModel):
    """Request model for memory operations."""

    content: str
    importance: float = Field(default=0.5)
    source: str = Field(default="conversation")
    scope: str = Field(default="working")
    memory_bank: str = Field(default="default")
    metadata: dict | None = None


class MemoryOperationResponse(BaseModel):
    """Response model for memory operations."""

    status: str
    memory_id: str | None = None
    memory_bank: str = Field(default="default")
    error: str | None = None


class MemorySearchRequest(BaseModel):
    """Request model for memory search."""

    query: str
    limit: int = Field(default=5)
    memory_bank: str = Field(default="default")


class MemorySearchResponse(BaseModel):
    """Response model for memory search."""

    results: list[Any]
    memory_bank: str
    total_count: int = Field(default=0)
