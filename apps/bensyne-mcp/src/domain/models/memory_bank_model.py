"""Memory bank validation model using Pydantic."""

import re

from pydantic import BaseModel, Field, field_validator


class MemoryBankSchema(BaseModel):
    """Pydantic model for memory bank validation."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    status: str = Field(default="registered")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", v):
            raise ValueError(
                "Memory bank name must contain only alphanumeric characters and underscores"
            )
        return v
