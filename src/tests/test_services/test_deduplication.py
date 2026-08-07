"""Deduplication module tests — hash extraction and index integration functions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.tools.deduplication import (
    extract_file_hash,
    find_memory_by_hash,
    index_file_hash,
    is_file_based_memory,
    remove_hash_index_entry,
)


class TestIsFileBasedMemory:
    """is_file_based_memory checks for fileHash in metadata."""

    def test_returns_true_when_file_hash_in_metadata(self) -> None:
        args = {"content": "test", "metadata": {"fileHash": "abc123"}}
        assert is_file_based_memory(args) is True

    def test_returns_false_when_no_metadata_key(self) -> None:
        args = {"content": "test"}
        assert is_file_based_memory(args) is False

    def test_returns_false_when_metadata_empty(self) -> None:
        args = {"content": "test", "metadata": {}}
        assert is_file_based_memory(args) is False

    def test_returns_false_when_file_hash_not_in_metadata(self) -> None:
        args = {"content": "test", "metadata": {"otherKey": "value"}}
        assert is_file_based_memory(args) is False

    def test_returns_false_when_metadata_is_none(self) -> None:
        args = {"content": "test", "metadata": None}
        assert is_file_based_memory(args) is False

    def test_returns_true_with_other_metadata_keys(self) -> None:
        args = {"content": "test", "metadata": {"fileHash": "abc123", "hardwareId": "hw1"}}
        assert is_file_based_memory(args) is True


class TestExtractFileHash:
    """extract_file_hash returns fileHash string or None."""

    def test_returns_hash_when_present(self) -> None:
        args = {"content": "test", "metadata": {"fileHash": "sha256abc"}}
        assert extract_file_hash(args) == "sha256abc"

    def test_returns_none_when_no_metadata(self) -> None:
        args = {"content": "test"}
        assert extract_file_hash(args) is None

    def test_returns_none_when_metadata_empty(self) -> None:
        args = {"content": "test", "metadata": {}}
        assert extract_file_hash(args) is None

    def test_returns_none_when_file_hash_absent(self) -> None:
        args = {"content": "test", "metadata": {"otherKey": "value"}}
        assert extract_file_hash(args) is None

    def test_returns_none_when_metadata_is_none(self) -> None:
        args = {"content": "test", "metadata": None}
        assert extract_file_hash(args) is None

    def test_returns_hash_with_other_metadata(self) -> None:
        args = {"content": "test", "metadata": {"fileHash": "abc", "hardwareId": "hw1"}}
        assert extract_file_hash(args) == "abc"

    def test_returns_empty_string_when_hash_is_empty(self) -> None:
        args = {"content": "test", "metadata": {"fileHash": ""}}
        assert extract_file_hash(args) == ""


class TestFindMemoryByHash:
    """find_memory_by_hash delegates to hash_index.lookup()."""

    def test_returns_memory_id_when_found(self) -> None:
        mock_index = MagicMock()
        mock_index.lookup.return_value = "mem_001"
        result = find_memory_by_hash(mock_index, "abc123")
        assert result == "mem_001"
        mock_index.lookup.assert_called_once_with("abc123")

    def test_returns_none_when_not_found(self) -> None:
        mock_index = MagicMock()
        mock_index.lookup.return_value = None
        result = find_memory_by_hash(mock_index, "abc123")
        assert result is None
        mock_index.lookup.assert_called_once_with("abc123")


class TestIndexFileHash:
    """index_file_hash delegates to hash_index.store()."""

    def test_stores_mapping(self) -> None:
        mock_index = MagicMock()
        index_file_hash(mock_index, "abc123", "mem_001")
        mock_index.store.assert_called_once_with("abc123", "mem_001")

    def test_stores_different_mapping(self) -> None:
        mock_index = MagicMock()
        index_file_hash(mock_index, "xyz789", "mem_002")
        mock_index.store.assert_called_once_with("xyz789", "mem_002")


class TestRemoveHashIndexEntry:
    """remove_hash_index_entry delegates to hash_index.remove()."""

    def test_removes_entry(self) -> None:
        mock_index = MagicMock()
        mock_index.remove.return_value = "abc123"
        remove_hash_index_entry(mock_index, "mem_001")
        mock_index.remove.assert_called_once_with("mem_001")

    def test_no_side_effect_on_return_value(self) -> None:
        mock_index = MagicMock()
        mock_index.remove.return_value = None
        result = remove_hash_index_entry(mock_index, "mem_not_found")
        mock_index.remove.assert_called_once_with("mem_not_found")
        # Function returns None regardless
        assert result is None
