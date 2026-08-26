"""End-to-end integration for getPersonaStatus (Task 4 / spec §4.4).

Runs the full stack against REAL per-bank SQLite:
  * MnemosyneClient          — real mnemosyne.db in a temp data dir
  * FileMetadataConnectionManager + FileChunkRepository — real file_metadata.db

The only things mocked are the logger. This proves the counting contract
against the actual storage layout:

  * total                    — every working+episodic memory in the bank
  * node_memories            — memory ids present in file_chunks (file-backed)
  * occasional_memories      — non-file, valid_until null or in the future
  * expired_occasional_memories — non-file, valid_until in the past
  * materialization_due      — occasional_memories >= threshold

File association wins over temporality: a file-backed memory is a node even
when its valid_until is in the past.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.get_persona_status_use_case import (
    DEFAULT_MATERIALIZATION_THRESHOLD,
    GetPersonaStatusUseCase,
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

BANK = "persona_status_bank"
PAST = "2000-01-01T00:00:00"
FUTURE = "2999-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def mnemosyne(tmp_path: Path) -> Generator[MnemosyneClient, None, None]:
    client = MnemosyneClient(memory_bank=BANK, data_dir=str(tmp_path / "data"))
    yield client
    # No explicit close on MnemosyneClient in the current codebase; the
    # thread-local conn is released on process exit / next fixture isolation.


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / "file_metadata" / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def chunk_repository(manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(manager)


@pytest.fixture
def use_case(
    mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository
) -> GetPersonaStatusUseCase:
    return GetPersonaStatusUseCase(
        mnemosyne_client=mnemosyne,
        file_chunk_repository=chunk_repository,
        logger=LoggerMock(),
        materialization_threshold=DEFAULT_MATERIALIZATION_THRESHOLD,
    )


def _remember(mnemosyne: MnemosyneClient, tag: str, valid_until: str | None = None) -> str:
    """Remember one memory; assert it stored; return its real memory_id."""
    result = mnemosyne.remember(
        content=f"Experience note {tag} for the persona architect",
        source="integration-test",
        valid_until=valid_until,
    )
    assert result.is_ok, f"remember failed: {result.errors}"
    mid = result.value
    assert mid, f"expected a memory_id for {tag}, got {mid!r}"
    return mid


def _make_chunk_id(file_id: str, memory_id: str) -> str:
    return f"fc_{file_id}_{memory_id}"


def _file_back(chunk_repository: FileChunkRepository, bank: str, path: str, memory_id: str) -> None:
    """Persist a File row + one FileChunk row so memory_id is file-backed."""
    file_id = f"{bank}_{path.replace('/', '_')}"
    now = datetime(2026, 1, 1, 0, 0, 0)
    file_row = File(
        id=file_id,
        path=path,
        source_type=SourceType.VAULT,
        file_role=FileRole.DOCS,
        hash=None,
        file_type=None,
        size=None,
        language="markdown",
        aggregated_keywords=[],
        aggregated_tags=[],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=1,
        average_importance=0.5,
        metadata={},
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
        section_header="## Section",
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=now,
        updated_at=now,
    )
    assert chunk_repository.save_chunk(chunk).is_ok


# ===================================================================
# Classification — file-backed vs occasional vs expired
# ===================================================================


class TestGetPersonaStatusClassification:
    def test_classifies_node_occasional_and_expired(
        self, mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository, use_case
    ) -> None:
        # 2 file-backed (node) + 1 occasional (no expiry, not file) + 1 expired
        # occasional (past valid_until, not file) = 4 total.
        mem_a = _remember(mnemosyne, "a")
        mem_b = _remember(mnemosyne, "b")
        mem_c = _remember(mnemosyne, "c", valid_until=PAST)
        mem_d = _remember(mnemosyne, "d", valid_until=FUTURE)

        # File back mem_a and mem_d.
        _file_back(chunk_repository, BANK, "/persona/a.md", mem_a)
        _file_back(chunk_repository, BANK, "/persona/d.md", mem_d)

        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok, f"execute failed: {result.errors}"
        value = result.value
        assert value == {
            "total": 4,
            "node_memories": 2,          # mem_a, mem_d (file-backed)
            "occasional_memories": 1,    # mem_b (no expiry, not file)
            "expired_occasional_memories": 1,  # mem_c (past, not file)
            "materialization_due": False,      # 1 < 10
        }

    def test_file_backing_wins_over_past_valid_until(
        self, mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository, use_case
    ) -> None:
        """A file-backed memory with a PAST valid_until is a node, not expired."""
        mem_node_past = _remember(mnemosyne, "node_past", valid_until=PAST)
        mem_expired = _remember(mnemosyne, "expired", valid_until=PAST)

        _file_back(chunk_repository, BANK, "/persona/node_past.md", mem_node_past)

        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        value = result.value
        assert value["total"] == 2
        assert value["node_memories"] == 1            # mem_node_past (file-backed)
        assert value["occasional_memories"] == 0
        assert value["expired_occasional_memories"] == 1  # mem_expired (past, not file)

    def test_future_valid_until_is_not_expired(
        self, mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository, use_case
    ) -> None:
        mem_future = _remember(mnemosyne, "future", valid_until=FUTURE)
        assert _is_future(memory_id=mem_future, mnemosyne=mnemosyne)

        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        value = result.value
        # Not file-backed and not expired → occasional.
        assert value["occasional_memories"] == 1
        assert value["expired_occasional_memories"] == 0

    def test_empty_bank_reports_all_zero(self, use_case) -> None:
        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        assert result.value == {
            "total": 0,
            "node_memories": 0,
            "occasional_memories": 0,
            "expired_occasional_memories": 0,
            "materialization_due": False,
        }


# ===================================================================
# Materialization threshold — flip at the boundary
# ===================================================================


class TestMaterializationThreshold:
    def test_due_at_exact_threshold(self, mnemosyne: MnemosyneClient, use_case) -> None:
        # Exactly 10 non-file, non-expired memories → due True.
        for i in range(10):
            _remember(mnemosyne, f"t{i}")
        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        value = result.value
        assert value["occasional_memories"] == 10
        assert value["materialization_due"] is True

    def test_not_due_below_threshold(self, mnemosyne: MnemosyneClient, use_case) -> None:
        # 9 non-file, non-expired memories → due False.
        for i in range(9):
            _remember(mnemosyne, f"t{i}")
        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        value = result.value
        assert value["occasional_memories"] == 9
        assert value["materialization_due"] is False

    def test_expired_do_not_count_toward_threshold(
        self, mnemosyne: MnemosyneClient, use_case
    ) -> None:
        # 12 memories but 3 are expired (past valid_until) → only 9 count, not due.
        for i in range(9):
            _remember(mnemosyne, f"live_{i}")
        for i in range(3):
            _remember(mnemosyne, f"dead_{i}", valid_until=PAST)
        result = use_case.execute({"memory_bank": BANK})
        assert result.is_ok
        value = result.value
        assert value["total"] == 12
        assert value["occasional_memories"] == 9
        assert value["expired_occasional_memories"] == 3
        assert value["materialization_due"] is False

    def test_custom_threshold_respected(
        self, mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository
    ) -> None:
        # 2 occasional + threshold 2 → due True.
        for i in range(2):
            _remember(mnemosyne, f"live_{i}")
        strict_uc = GetPersonaStatusUseCase(
            mnemosyne_client=mnemosyne,
            file_chunk_repository=chunk_repository,
            logger=LoggerMock(),
            materialization_threshold=2,
        )
        result = strict_uc.execute({"memory_bank": BANK})
        assert result.is_ok
        assert result.value["materialization_due"] is True


# ===================================================================
# Infrastructure method — list_memory_validities
# ===================================================================


class TestListMemoryValidities:
    def test_returns_id_valid_until_pairs_for_all_memories(
        self, mnemosyne: MnemosyneClient
    ) -> None:
        mem_no_expiry = _remember(mnemosyne, "no_expiry")
        mem_past = _remember(mnemosyne, "past", valid_until=PAST)
        mem_future = _remember(mnemosyne, "future", valid_until=FUTURE)

        pairs = mnemosyne.list_memory_validities()
        by_id = {mid: vu for mid, vu in pairs}

        # Every written memory is present (including the expired one).
        assert mem_no_expiry in by_id
        assert mem_past in by_id
        assert mem_future in by_id
        # valid_until is round-tripped (None for unset).
        assert by_id[mem_no_expiry] is None or by_id[mem_no_expiry] == ""
        assert by_id[mem_past] is not None
        assert by_id[mem_future] is not None

    def test_expired_memories_are_still_returned(self, mnemosyne: MnemosyneClient) -> None:
        """The count needs expired memories — they must NOT be filtered out."""
        _remember(mnemosyne, "live")
        mem_dead = _remember(mnemosyne, "dead", valid_until=PAST)

        ids = {mid for mid, _ in mnemosyne.list_memory_validities()}
        assert mem_dead in ids


# ===================================================================
# Infrastructure method — get_file_backed_memory_ids
# ===================================================================


class TestGetFileBackedMemoryIds:
    def test_returns_distinct_file_backed_memory_ids(
        self, mnemosyne: MnemosyneClient, chunk_repository: FileChunkRepository
    ) -> None:
        mem_a = _remember(mnemosyne, "a")
        mem_b = _remember(mnemosyne, "b")
        mem_c = _remember(mnemosyne, "c")

        _file_back(chunk_repository, BANK, "/persona/a.md", mem_a)
        # mem_b: back it from a SECOND file to prove distinct/dedup + multiple files.
        _file_back(chunk_repository, BANK, "/persona/b1.md", mem_b)
        _file_back(chunk_repository, BANK, "/persona/b2.md", mem_b)
        # mem_c: never file-backed.

        backed = chunk_repository.get_file_backed_memory_ids()
        assert backed == {mem_a, mem_b}  # mem_c excluded, mem_b deduped to one id


# ===================================================================
# Validation — missing/empty memory_bank
# ===================================================================


class TestGetPersonaStatusValidation:
    def test_missing_memory_bank_is_validation_error(self, use_case) -> None:
        result = use_case.execute({})
        assert not result.is_ok
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes

    def test_empty_memory_bank_is_validation_error(self, use_case) -> None:
        result = use_case.execute({"memory_bank": ""})
        assert not result.is_ok
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_future(memory_id: str, mnemosyne: MnemosyneClient) -> bool:
    pairs = dict(mnemosyne.list_memory_validities())
    vu = pairs.get(memory_id)
    if not vu:
        return False
    candidate = str(vu).strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    return datetime.fromisoformat(candidate) > datetime.now()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
