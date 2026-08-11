"""Unit tests for FileService summary integration.

Verifies that:
- FileService.create_file accepts summary
- update_file accepts summary
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from src.domain.entities.file import File, FileStatus, SourceType
from src.domain.result import Result
from src.utils.structured_logging import LoggerMock

from src.application.services.file_service import FileService  # noqa: E402

NOW = datetime(2026, 1, 1, 0, 0, 0)
VALID_HASH = "a" * 64

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.AGENT_SESSION,
    status: FileStatus = FileStatus.PENDING,
    summary: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        hash=VALID_HASH,
        file_type=None,
        size=None,
        language=None,
        summary=summary,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def file_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def chunk_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def relation_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def memory_repo() -> MagicMock:
    return MagicMock()

@pytest.fixture
def service(
    file_repo: MagicMock,
    chunk_repo: MagicMock,
    relation_repo: MagicMock,
    memory_repo: MagicMock,
) -> FileService:
    return FileService(
        file_repository=file_repo,
        chunk_repository=chunk_repo,
        relation_repository=relation_repo,
        logger=LoggerMock(),
        memory_client=memory_repo,
    )

# ===================================================================
# create_file with summary
# ===================================================================

class TestCreateFileWithSummary:
    """create_file accepts summary in file_data and persists it."""

    def test_create_file_with_summary(self, service: FileService, file_repo: MagicMock) -> None:
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "summary": "A file about configuration",
            "hash": VALID_HASH,
        }
        expected_file = _a_file(
            id="f1",
            path="/tmp/test.txt",
            source_type=SourceType.FILE_SYSTEM,
            summary="A file about configuration",
        )
        file_repo.save_file.return_value = Result.ok(expected_file)

        result = service.create_file(file_data)

        assert result.is_ok is True
        assert result.value.summary == "A file about configuration"
        file_repo.save_file.assert_called_once()

    def test_create_file_without_summary(self, service: FileService, file_repo: MagicMock) -> None:
        file_data = {
            "id": "f1",
            "path": "/tmp/test.txt",
            "source_type": SourceType.FILE_SYSTEM,
            "hash": VALID_HASH,
        }
        expected_file = _a_file(
            id="f1",
            path="/tmp/test.txt",
            source_type=SourceType.FILE_SYSTEM,
        )
        file_repo.save_file.return_value = Result.ok(expected_file)

        result = service.create_file(file_data)

        assert result.is_ok is True
        assert result.value.summary is None

# ===================================================================
# update_file with summary
# ===================================================================

class TestUpdateFileWithSummary:
    """update_file accepts summary and updates it via the entity."""

    def test_update_file_with_summary(self,
        service: FileService,
        file_repo: MagicMock,
    ) -> None:
        existing = _a_file(id="f1", summary=None)
        file_repo.get_file_by_id.return_value = Result.ok(existing)

        updated = _a_file(id="f1", summary="New summary text")
        file_repo.save_file.return_value = Result.ok(updated)

        result = service.update_file("f1", summary="New summary text")

        assert result.is_ok is True
        file_repo.save_file.assert_called_once()
