"""Integration tests for File.summary field through the full stack.

Verifies that summary persists through:
- File creation with SQLite repository
- File retrieval from SQLite repository
- Aggregate retrieval with summary
- Content reconstruction with summary
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.services.file_service import FileService
from src.domain.file_entity import File, FileStatus, SourceType
from src.utils.result import Result
from src.infrastructure.storage.sqlite.file_chunk_repository import (
    FileChunkRepository,
)
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import (
    FileRelationRepository,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.structured_logging import LoggerMock

VALID_HASH = "a" * 64

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bank_dir(tmp_path: Path) -> Path:
    return tmp_path / "test_bank"

@pytest.fixture
def conn_manager(bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
    yield mgr
    mgr.close()

@pytest.fixture
def file_repo(conn_manager: FileMetadataConnectionManager) -> FileRepository:
    return FileRepository(conn_manager)

@pytest.fixture
def chunk_repo(conn_manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(conn_manager)

@pytest.fixture
def relation_repo(conn_manager: FileMetadataConnectionManager) -> FileRelationRepository:
    return FileRelationRepository(conn_manager)

@pytest.fixture
def service(
    file_repo: FileRepository,
    chunk_repo: FileChunkRepository,
    relation_repo: FileRelationRepository,
) -> FileService:
    return FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=LoggerMock(),
        memory_client=None,
    )

# ===================================================================
# Summary through FileService + SQLite
# ===================================================================

class TestSummaryThroughService:
    """Summary persists through FileService.create_file and retrieval."""

    def test_create_file_with_summary_returns_from_repo(self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        file_data = {
            "id": "f_sum_1",
            "path": "/tmp/with_summary.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "summary": "This file contains important config data",
            "hash": VALID_HASH,
        }

        create_result = service.create_file(file_data)
        assert create_result.is_ok is True
        assert create_result.value.summary == "This file contains important config data"

        # Retrieve from repository to verify persistence
        get_result = file_repo.get_file_by_id("f_sum_1")
        assert get_result.is_ok is True
        assert get_result.value is not None
        assert get_result.value.summary == "This file contains important config data"

    def test_create_file_without_summary_returns_none(self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        file_data = {
            "id": "f_sum_2",
            "path": "/tmp/no_summary.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }

        create_result = service.create_file(file_data)
        assert create_result.is_ok is True
        assert create_result.value.summary is None

        get_result = file_repo.get_file_by_id("f_sum_2")
        assert get_result.is_ok is True
        assert get_result.value is not None
        assert get_result.value.summary is None

    def test_aggregate_with_summary(self,
        service: FileService,
    ) -> None:
        """FileMetadataAggregate returned by get_file includes summary."""
        file_data = {
            "id": "f_sum_3",
            "path": "/tmp/agg_summary.txt",
            "source_type": SourceType.AGENT_SESSION,
            "summary": "Aggregate summary test",
            "hash": VALID_HASH,
        }

        service.create_file(file_data)

        agg_result = service.get_file("f_sum_3")
        assert agg_result.is_ok is True
        assert agg_result.value.file.summary == "Aggregate summary test"

    def test_update_file_summary(self,
        service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """update_file can set or change the summary field."""
        file_data = {
            "id": "f_sum_5",
            "path": "/tmp/update_summary.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }

        service.create_file(file_data)

        # Update with summary
        update_result = service.update_file("f_sum_5", summary="Updated summary")
        assert update_result.is_ok is True

        # Verify in repository
        get_result = file_repo.get_file_by_id("f_sum_5")
        assert get_result.is_ok is True
        assert get_result.value is not None
        assert get_result.value.summary == "Updated summary"
