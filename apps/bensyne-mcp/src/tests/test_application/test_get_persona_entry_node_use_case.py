"""Unit tests for GetPersonaEntryNodeUseCase (D2, RC2).

The use case locates a persona bank's entry node — the file whose
``files.metadata`` carries ``persona.entry == "true"`` — and returns its
``file_id`` (the id ``expandFileRelations`` requires, per the RC4 file-tools
contract).

Persona nodes live in the **file metadata store** (``file_metadata.db``), not in
mnemosyne.db: racochu's ``AgentPersonaChunkingStrategy`` writes the persona
metadata to ``files.metadata`` (via ``formatPersonaNodeMetadata``) and the
``decision_next`` edges to ``file_relations``. The memory layer (mnemosyne.db)
stores the node *content*; ``file_chunks.memory_id`` is the link. So the use
case:
  * finds the entry file via ``FileRepository.list_files()`` (persona.entry),
  * resolves the node content via ``FileChunkRepository.get_chunks_by_file_id``
    + ``mnemosyne_client(memory_id)`` — the same composition path
    ``expandFileRelations`` uses.

Dependencies are mocked: this is a pure application-layer unit test. Assertions
are on the returned node dict and error codes only — no logger assertions.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pytest

from src.application.use_cases.get_persona_entry_node_use_case import (
    GetPersonaEntryNodeUseCase,
)
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File
from src.domain.models.file_model import FileStatus, SourceType
from src.utils.result import Result
from src.utils.structured_logging import LoggerMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now()


def _file(id: str, metadata: dict, path: Optional[str] = None) -> File:
    return File(
        id=id,
        path=path or f"/agent-personas/{id}.md",
        source_type=SourceType.AGENT_PERSONA,
        file_role=None,
        hash=None,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=[],
        aggregated_tags=["persona-node"],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=1,
        average_importance=0.5,
        metadata=metadata,
        created_at=_now(),
        updated_at=_now(),
    )


def _file_chunk(file_id: str, memory_id: str, chunk_index: int = 0) -> FileChunk:
    now = _now()
    return FileChunk(
        id=f"chunk-{memory_id}",
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=1,
        content_hash="h",
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=now,
        updated_at=now,
    )


def _entry_metadata() -> dict:
    return {
        "persona.node_id": "00-entry",
        "persona.title": "Entry Node",
        "persona.entry": "true",
        "persona.conditions": "[]",
        "persona.veto": "[]",
    }


def _non_entry_metadata() -> dict:
    return {
        "persona.node_id": "010-next",
        "persona.title": "Non Entry Node",
        "persona.entry": "false",
        "persona.conditions": "[]",
        "persona.veto": "[]",
    }


def _mock_file_repository(files: List[File]):
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.list_files.return_value = Result.ok(files)
    return repo


def _mock_chunk_repository(chunks_by_file: dict):
    from unittest.mock import MagicMock

    repo = MagicMock()

    def _lookup(file_id: str) -> Result[list]:
        return Result.ok(chunks_by_file.get(file_id, []))

    repo.get_chunks_by_file_id.side_effect = _lookup
    return repo


def _mock_content_fetcher(content_by_memory: dict):
    """mnemosyne_client is a (memory_id) -> dict | None callable."""

    def _get(memory_id: str) -> Optional[dict]:
        return content_by_memory.get(memory_id)

    return _get


def _use_case(
    files: List[File],
    chunks_by_file: dict,
    content_by_memory: dict,
) -> GetPersonaEntryNodeUseCase:
    return GetPersonaEntryNodeUseCase(
        file_repository=_mock_file_repository(files),
        file_chunk_repository=_mock_chunk_repository(chunks_by_file),
        mnemosyne_client=_mock_content_fetcher(content_by_memory),
        logger=LoggerMock(),
    )


def _execute(use_case: GetPersonaEntryNodeUseCase, bank: str = "agent-persona_researcher"):
    return use_case.execute({"memory_bank": bank})


# ---------------------------------------------------------------------------
# Happy path — one entry node
# ---------------------------------------------------------------------------


class TestEntryNodeFound:
    def test_returns_entry_file_with_valid_file_id(self) -> None:
        """A bank with exactly one persona.entry='true' file returns that node + file_id."""
        files = [
            _file("file_entry_1", _entry_metadata()),
            _file("file_other_1", _non_entry_metadata()),
        ]
        uc = _use_case(
            files,
            {"file_entry_1": [_file_chunk("file_entry_1", "mem_entry_1")]},
            {"mem_entry_1": {"id": "mem_entry_1", "content": "Start read frame"}},
        )

        result = _execute(uc)

        assert result.is_ok, f"use case returned ko: {result.errors}"
        value = result.value
        assert value["file_id"] == "file_entry_1"
        assert value["memory_id"] == "mem_entry_1"
        # title comes from persona metadata
        assert value["title"] == "Entry Node"
        # text is the node content resolved via mnemosyne
        assert value["text"] == "Start read frame"

    def test_returns_full_node_contract_shape(self) -> None:
        """The response contract is exactly the six documented keys."""
        files = [_file("file_entry_1", _entry_metadata())]
        uc = _use_case(
            files,
            {"file_entry_1": [_file_chunk("file_entry_1", "mem_entry_1")]},
            {"mem_entry_1": {"id": "mem_entry_1", "content": "x"}},
        )

        result = _execute(uc)
        value = result.value

        assert set(value.keys()) == {
            "memory_id",
            "file_id",
            "title",
            "text",
            "metadata",
            "tags",
        }

    def test_metadata_is_returned_as_dict(self) -> None:
        """The entry file's metadata is returned as a dict (persona keys intact)."""
        files = [_file("file_entry_1", _entry_metadata())]
        uc = _use_case(
            files,
            {"file_entry_1": [_file_chunk("file_entry_1", "mem_entry_1")]},
            {"mem_entry_1": {"id": "mem_entry_1", "content": "x"}},
        )

        value = _execute(uc).value

        assert value["metadata"]["persona.node_id"] == "00-entry"
        assert value["metadata"]["persona.entry"] == "true"

    def test_ignores_non_entry_files(self) -> None:
        """Files with persona.entry != 'true' are never chosen as the entry node."""
        files = [
            _file("file_a", _non_entry_metadata()),
            _file("file_b", _non_entry_metadata()),
        ]
        uc = _use_case(files, {}, {})

        result = _execute(uc)

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "ENTRY_NODE_NOT_FOUND" in codes


# ---------------------------------------------------------------------------
# file_id robustness
# ---------------------------------------------------------------------------


class TestFileIdRobustness:
    def test_file_id_is_none_when_no_chunk_row(self) -> None:
        """If the entry file has no FileChunk row, memory_id/text degrade gracefully."""
        files = [_file("file_entry_1", _entry_metadata())]
        uc = _use_case(files, {}, {})  # no chunks for file_entry_1

        result = _execute(uc)

        assert result.is_ok, f"use case returned ko: {result.errors}"
        assert result.value["file_id"] == "file_entry_1"
        assert result.value["memory_id"] is None
        assert result.value["text"] == ""

    def test_file_id_is_the_rc4_contract_id(self) -> None:
        """file_id is the entry File.id (what expandFileRelations consumes), never the memory_id."""
        files = [_file("file_rc4", _entry_metadata())]
        uc = _use_case(
            files,
            {"file_rc4": [_file_chunk("file_rc4", "mem_rc4")]},
            {"mem_rc4": {"id": "mem_rc4", "content": "x"}},
        )

        value = _execute(uc).value

        assert value["file_id"] == "file_rc4"
        assert value["file_id"] != value["memory_id"]


# ---------------------------------------------------------------------------
# No entry node
# ---------------------------------------------------------------------------


class TestEntryNodeNotFound:
    def test_empty_bank_returns_entry_node_not_found(self) -> None:
        """A bank with no files returns ENTRY_NODE_NOT_FOUND (no throw)."""
        uc = _use_case([], {}, {})

        result = _execute(uc)

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "ENTRY_NODE_NOT_FOUND" in codes

    def test_multiple_entry_nodes_returns_one_deterministically(self) -> None:
        """If several entry files exist, the one with the smallest node_id wins (stable)."""
        # Two entry files; the one with the lower node_id must be chosen.
        meta_a = {**_entry_metadata(), "persona.node_id": "010-later"}
        meta_b = {**_entry_metadata(), "persona.node_id": "000-first"}
        files = [_file("file_a", meta_a), _file("file_b", meta_b)]
        uc = _use_case(
            files,
            {
                "file_a": [_file_chunk("file_a", "mem_a")],
                "file_b": [_file_chunk("file_b", "mem_b")],
            },
            {
                "mem_a": {"id": "mem_a", "content": "a"},
                "mem_b": {"id": "mem_b", "content": "b"},
            },
        )

        value = _execute(uc).value

        assert value["file_id"] == "file_b"
        assert value["memory_id"] == "mem_b"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_memory_bank_is_a_validation_error(self) -> None:
        uc = _use_case([], {}, {})

        result = uc.execute({})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes

    def test_empty_memory_bank_is_a_validation_error(self) -> None:
        uc = _use_case([], {}, {})

        result = uc.execute({"memory_bank": ""})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
