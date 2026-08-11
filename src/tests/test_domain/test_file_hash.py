
"""Unit tests for FileHash value object."""

import pytest

from src.domain.value_objects.file_hash import FileHash
from src.domain.result import Result


VALID_SHA256 = "a" * 64  # 64 hex characters


class TestFileHashOfValid:
    """FileHash.of accepts valid SHA-256 hash."""

    def test_of_returns_ok_for_valid_sha256(self):
        result = FileHash.of(VALID_SHA256)
        assert result.is_ok is True
        assert result.value.hash_value == VALID_SHA256

    def test_of_returns_ok_for_mixed_hex_sha256(self):
        hash_value = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        result = FileHash.of(hash_value)
        assert result.is_ok is True
        assert result.value.hash_value == hash_value

    def test_of_returns_ok_for_uppercase_hex(self):
        hash_value = "F" * 64
        result = FileHash.of(hash_value)
        assert result.is_ok is True
        assert result.value.hash_value == hash_value

    def test_file_hash_is_frozen(self):
        result = FileHash.of(VALID_SHA256)
        fh = result.value
        with pytest.raises(Exception):
            fh.hash_value = "b" * 64  # type: ignore


class TestFileHashOfInvalid:
    """FileHash.of rejects invalid hash formats."""

    def test_of_rejects_too_short(self):
        result = FileHash.of("a" * 32)
        assert result.is_ko is True

    def test_of_rejects_too_long(self):
        result = FileHash.of("a" * 128)
        assert result.is_ko is True

    def test_of_rejects_non_hex_characters(self):
        result = FileHash.of("g" * 64)
        assert result.is_ko is True

    def test_of_rejects_empty_string(self):
        result = FileHash.of("")
        assert result.is_ko is True

    def test_of_rejects_with_spaces(self):
        result = FileHash.of("a" * 32 + " " + "a" * 31)
        assert result.is_ko is True


class TestFileHashEquality:
    """Two FileHash instances with same hash_value are equal."""

    def test_same_hash_value_are_equal(self):
        result1 = FileHash.of(VALID_SHA256)
        result2 = FileHash.of(VALID_SHA256)
        assert result1.value == result2.value

    def test_different_hash_value_are_not_equal(self):
        result1 = FileHash.of(VALID_SHA256)
        result2 = FileHash.of("b" * 64)
        assert result1.value != result2.value

    def test_hash_value_is_consistent(self):
        result = FileHash.of(VALID_SHA256)
        fh = result.value
        assert hash(fh) == hash(fh)
