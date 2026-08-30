"""End-to-end integration for getPersonaEntryNode (D2, RC2).

Runs the full stack against REAL per-bank SQLite:
  * MnemosyneClient          — real mnemosyne.db in a temp data dir (content)
  * FileMetadataConnectionManager + FileRepository/FileChunkRepository
                               — real file_metadata.db (persona metadata + edges)

The only thing mocked is the logger. This proves the entry-node discovery
contract against the ACTUAL storage layout that racochu produces:

  * The ``persona.entry == "true"`` flag lives in ``file_metadata.db:files.metadata``
    (written by racochu's ``AgentPersonaChunkingStrategy.formatPersonaNodeMetadata``).
  * The node *content* lives in mnemosyne.db; ``file_chunks.memory_id`` links it.
  * The use case finds the entry file via FileRepository and resolves content via
    the chunk→memory link (the same composition path expandFileRelations uses).

This layout is the one that regressed: the flag was once (wrongly) read from
mnemosyne.db ``metadata_json`` (empty for persona nodes).
"""

from __future__ import annotations

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

BANK = "agent-persona_entry_bank"


# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite (integration-grade)
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
    """Store node content in mnemosyne (the memory layer). Returns the memory_id."""
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

    The persona metadata (incl. ``persona.entry``) is written to ``files.metadata``
    — matching racochu's real behavior — while the content link goes via the chunk.
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


def _entry_metadata(node_id: str = "00-entry", entry: str = "true") -> dict:
    return {
        "persona.node_id": node_id,
        "persona.title": "Entry Node",
        "persona.entry": entry,
        "persona.conditions": "[]",
        "persona.veto": "[]",
    }


# ===================================================================
# Full use case flow — find entry file → chunk → memory → content
# ===================================================================


class TestUseCaseIntegration:
    def test_resolves_entry_node_with_file_id(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
    ) -> None:
        """Full flow: entry file (persona.entry in files.metadata) is found + content resolved."""
        mem_entry = _remember(mnemosyne, "Start read frame for persona architect")

        file_id = _file_back(
            chunk_repository,
            BANK,
            "/persona/entry.md",
            mem_entry,
            metadata=_entry_metadata(),
        )

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value

        assert value["file_id"] == file_id
        assert value["memory_id"] == mem_entry
        assert value["title"] == "Entry Node"
        assert "Start read frame" in value["text"]
        assert value["metadata"]["persona.node_id"] == "00-entry"
        assert value["tags"] == ["persona-node", "00-entry"]

    def test_entry_flag_is_read_from_files_metadata_not_memories(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
    ) -> None:
        """Regression guard: persona.content in mnemosyne.db does NOT make a node the
        entry — the flag must be in files.metadata (the layout that regressed)."""
        # A memory whose CONTENT mentions persona.entry must not be chosen; and a
        # memory with no persona metadata in mnemosyne is fine — the flag is on the file.
        mem = _remember(mnemosyne, "persona.entry: true is written into content text")

        # File WITHOUT persona.entry flag in metadata → not an entry node.
        _file_back(chunk_repository, BANK, "/persona/node.md", mem, metadata={})

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "ENTRY_NODE_NOT_FOUND" in codes

    def test_returns_none_memory_and_empty_text_when_no_chunk_row(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
    ) -> None:
        """Entry file exists (flag in files.metadata) but has no FileChunk row:
        file_id is returned, memory_id/text degrade gracefully."""
        # File with entry flag, but no chunk row created for it.
        now = datetime(2026, 1, 1, 0, 0, 0)
        file_row = File(
            id=f"{BANK}_entry_no_chunk",
            path="/persona/entry-no-chunk.md",
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
            total_chunks=0,
            average_importance=0.5,
            metadata=_entry_metadata(),
            created_at=now,
            updated_at=now,
        )
        assert FileRepository(chunk_repository._conn_manager).save_file(file_row).is_ok

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value

        assert value["file_id"] == file_row.id
        assert value["memory_id"] is None
        assert value["text"] == ""
        assert value["title"] == "Entry Node"

    def test_no_entry_node_returns_error(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
    ) -> None:
        """Files exist but none flagged persona.entry=true → ENTRY_NODE_NOT_FOUND."""
        mem = _remember(mnemosyne, "A non-entry node")
        _file_back(
            chunk_repository,
            BANK,
            "/persona/other.md",
            mem,
            metadata=_entry_metadata(node_id="01-other", entry="false"),
        )

        result = use_case.execute({"memory_bank": BANK})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "ENTRY_NODE_NOT_FOUND" in codes

    def test_multiple_entry_nodes_resolves_deterministically(
        self,
        mnemosyne: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        use_case: GetPersonaEntryNodeUseCase,
    ) -> None:
        """Two entry files: the smaller persona.node_id wins (stable, no crash)."""
        mem_a = _remember(mnemosyne, "Entry A content")
        mem_b = _remember(mnemosyne, "Entry B content")

        _file_back(
            chunk_repository,
            BANK,
            "/persona/a.md",
            mem_a,
            metadata=_entry_metadata(node_id="010-later"),
        )
        _file_back(
            chunk_repository,
            BANK,
            "/persona/b.md",
            mem_b,
            metadata=_entry_metadata(node_id="000-first"),
        )

        value = use_case.execute({"memory_bank": BANK}).value

        # 000-first < 010-later → file b wins
        expected_b = f"{BANK}_/persona/b.md".replace("/", "_")
        assert value["file_id"] == expected_b
        assert value["memory_id"] == mem_b


# ===================================================================
# Validation
# ===================================================================


class TestEntryNodeValidation:
    def test_missing_memory_bank_is_validation_error(
        self, use_case: GetPersonaEntryNodeUseCase
    ) -> None:
        result = use_case.execute({})
        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes

    def test_empty_memory_bank_is_validation_error(
        self, use_case: GetPersonaEntryNodeUseCase
    ) -> None:
        result = use_case.execute({"memory_bank": ""})
        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
