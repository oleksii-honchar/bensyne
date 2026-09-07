"""Integration test: getPersonaEntryNode returns file content when memory text is empty.

Regression guard for the bug where the memory broker's cached `text` field for
a persona node was empty (or stale) while the canonical content lived in the
FileChunk on disk. After the fix, the use case falls back to reading the node
file from the filesystem when the memory content is empty.

Scenario:
1. Create a persona node file on disk with known content.
2. Create a memory with empty content.
3. Link the memory to the file via the file_chunks table.
4. Call getPersonaEntryNode.
5. Assert returned text is the file content, not empty.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.get_persona_entry_node_use_case import (
    GetPersonaEntryNodeUseCase,
)
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus
from src.domain.models.file_model import FileRole, SourceType
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.structured_logging import LoggerMock

BANK = "agent-persona_empty_memory_test"


# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite + real filesystem (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def mnemosyne(tmp_path: Path) -> Generator[MnemosyneClient, None, None]:
    client = MnemosyneClient(memory_bank=BANK, data_dir=str(tmp_path / "data"))
    yield client


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / "file_metadata" / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def chunk_repository(manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(manager)


@pytest.fixture
def file_repository(manager: FileMetadataConnectionManager) -> FileRepository:
    return FileRepository(manager)


@pytest.fixture
def use_case(
    mnemosyne: MnemosyneClient,
    chunk_repository: FileChunkRepository,
    file_repository: FileRepository,
) -> GetPersonaEntryNodeUseCase:
    return GetPersonaEntryNodeUseCase(
        file_repository=file_repository,
        file_chunk_repository=chunk_repository,
        mnemosyne_client=mnemosyne.get,
        logger=LoggerMock(),
    )


def _remember(mnemosyne: MnemosyneClient, content: str) -> str:
    """Store content in mnemosyne (the memory layer). Returns the memory_id."""
    result = mnemosyne.remember(
        content=content,
        source="integration-test",
    )
    assert result.is_ok, f"remember failed: {result.errors}"
    return result.value


def _make_chunk_id(file_id: str, memory_id: str) -> str:
    return f"fc_{file_id}_{memory_id}"


def _file_back(
    chunk_repository: FileChunkRepository,
    bank: str,
    path: str,
    memory_id: str,
    metadata: dict | None = None,
) -> str:
    """Persist a File row (with persona metadata) + one FileChunk row.

    Returns the file_id.
    """
    file_id = f"{bank}_{path.replace('/', '_')}"
    now = datetime(2026, 1, 1, 0, 0, 0)
    file_row = File(
        id=file_id,
        path=path,
        source_type=SourceType.AGENT_PERSONA,
        file_role=FileRole.DOCS,
        hash=None,
        file_type=None,
        size=None,
        language="markdown",
        aggregated_keywords=[],
        aggregated_tags=["persona-node"],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=1,
        average_importance=0.5,
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )
    assert FileRepository(chunk_repository._conn_manager).save_file(file_row).is_ok

    chunk = FileChunk(
        id=_make_chunk_id(file_id, memory_id),
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=0,
        start_line=1,
        end_line=40,
        content_hash=None,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header="## Entry",
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=now,
        updated_at=now,
    )
    assert chunk_repository.save_chunk(chunk).is_ok
    return file_id


def _entry_metadata(node_id: str = "00-entry") -> dict:
    return {
        "persona.node_id": node_id,
        "persona.title": "Enter: load grounding and ICM skill, locate entry + state",
        "persona.entry": "true",
        "persona.conditions": '["user points at an ICM workspace"]',
        "persona.veto": '["operating on an ICM workspace without the icm-specialist skill"]',
        "persona.created": "2026-08-26",
        "persona.updated": "2026-08-26",
        "persona.status": "active",
    }


# ===================================================================
# Test: filesystem fallback when memory content is empty
# ===================================================================


class TestEmptyMemoryFilesystemFallback:
    def test_falls_back_to_file_when_memory_content_empty(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
        tmp_path: Path,
    ) -> None:
        """When the memory broker returns empty content, getPersonaEntryNode
        reads the node file from the filesystem (the same content that racochu
        ingested)."""

        # 1. Create the node file on disk with known content.
        node_file = tmp_path / "agent-personas" / "icm-operator" / "00-entry.md"
        node_file.parent.mkdir(parents=True, exist_ok=True)
        file_content = (
            "---\n"
            "id: 00-entry\n"
            "title: \"Enter: load grounding and ICM skill, locate entry + state\"\n"
            "---\n"
            "Load the icm-specialist skill, find the workspace root,\n"
            "and inspect .vault/ for existing project context. If a prior\n"
            "ICM state file exists in the workspace, load it; otherwise\n"
            "begin a fresh operator session."
        )
        node_file.write_text(file_content, encoding="utf-8")

        # 2. Store a memory with EMPTY content (simulating the buggy cached
        #    state where the broker's text field is empty/stale).
        empty_mem = _remember(mnemosyne, "")

        # 3. Register the file metadata with the entry flag, linked to the empty
        #    memory via the file_chunks table.
        file_id = _file_back(
            chunk_repository,
            BANK,
            str(node_file),
            empty_mem,
            metadata=_entry_metadata(),
        )

        # 4. Call getPersonaEntryNode.
        result = use_case.execute({"memory_bank": BANK})

        # 5. Verify it fell back to the filesystem content.
        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value

        assert value["file_id"] == file_id
        assert value["memory_id"] == empty_mem
        # The memory broker returned empty; the filesystem fallback must have
        # restored the actual content.
        assert value["text"] != "", "text should not be empty — filesystem fallback failed"
        assert "icm-specialist skill" in value["text"]
        assert "load it" in value["text"]
        # The title comes from file metadata (not frontmatter parsing).
        assert value["title"] == "Enter: load grounding and ICM skill, locate entry + state"
        assert value["metadata"]["persona.node_id"] == "00-entry"
        assert value["tags"] == ["persona-node", "00-entry"]

    def test_no_fallback_needed_when_memory_content_present(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
        tmp_path: Path,
    ) -> None:
        """When the memory broker returns content, that content is used (no
        filesystem read). This is the baseline path and also a regression guard
        against always reading from disk."""

        node_file = tmp_path / "agent-personas" / "icm-operator" / "00-entry-b.md"
        node_file.parent.mkdir(parents=True, exist_ok=True)
        file_content = (
            "---\n"
            "id: 00-entry\n"
            "title: Enter\n"
            "---\n"
            "DISK-ONLY: This text should not appear when memory content is present."
        )
        node_file.write_text(file_content, encoding="utf-8")

        # Memory has the real content — the broker is in sync.
        memory_content = (
            "Memory has the correct content. "
            "Load the icm-specialist skill and find the workspace root."
        )
        memory_id = _remember(mnemosyne, memory_content)

        file_id = _file_back(
            chunk_repository,
            BANK,
            str(node_file),
            memory_id,
            metadata=_entry_metadata(node_id="00-entry-b"),
        )

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value
        assert value["file_id"] == file_id
        assert value["memory_id"] == memory_id
        # Memory content is used, not the disk content.
        assert value["text"] == memory_content
        assert "DISK-ONLY" not in value["text"]

    def test_empty_memory_and_missing_file_yields_empty_text(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
        tmp_path: Path,
    ) -> None:
        """Edge case: memory is empty AND the node file doesn't exist on disk.
        The use case must not crash — it returns empty text (the original
        pre-fallback behavior)."""

        # Memory has empty content.
        empty_mem = _remember(mnemosyne, "")

        # File metadata registered, but no actual file on disk.
        missing_path = tmp_path / "agent-personas" / "nonexistent" / "00-entry.md"
        file_id = _file_back(
            chunk_repository,
            BANK,
            str(missing_path),
            empty_mem,
            metadata=_entry_metadata(node_id="00-missing"),
        )

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value
        assert value["file_id"] == file_id
        assert value["memory_id"] == empty_mem
        # No crash; empty text is acceptable when there's nothing on disk.
        assert value["text"] == ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
