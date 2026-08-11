"""FileHash value object for file deduplication."""

import re

from dataclasses import dataclass

from src.domain.result import ErrorWithDetails, Result

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class FileHash:
    """Immutable value object encapsulating a SHA-256 file hash."""

    hash_value: str

    @classmethod
    def of(cls, hash_value: str) -> "Result[FileHash]":
        """Create a FileHash from a hash string, validating SHA-256 format.

        Returns Result.ok(FileHash) on valid input, Result.ko on invalid input.
        """
        if not isinstance(hash_value, str) or not _SHA256_PATTERN.match(hash_value):
            return Result.ko([
                ErrorWithDetails(
                    "INVALID_FILE_HASH",
                    {"given": hash_value, "expected": "64 hex characters (SHA-256)"},
                )
            ])
        return Result.ok(cls(hash_value=hash_value))
