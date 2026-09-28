"""Unit test: rebuild_projection only called on chunk 0 of re-ingested files.

Uses mocks to verify the fix in materialize_file_context.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from src.application.services.file_service import FileService
from src.domain.models.file_context_model import (
    FileContext,
    FileContextEdge,
    FileContextParentUnit,
)
from src.domain.models.file_model import FileRole, SourceType
from src.domain.models.file_relation_model import RelationType
from src.utils.structured_logging import LoggerMock


def make_context(
    file_hash: str = "test-hash",
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> FileContext:
    """Create a FileContext for testing."""
    return FileContext(
        contract_version=1,
        file_path="/tmp/test.md",
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        section_header=None,
        start_line=None,
        end_line=None,
        source_type=SourceType.AGENT_PERSONA,
        file_role=FileRole.DOCS,
        language=None,
        file_hash=file_hash,
        chunk_hash=None,
        summary=None,
        parent_unit=None,
        edges=None,
        tags=(),
        extra={},
    )


class TestRebuildProjectionFinalChunk:
    """rebuild_projection is called only on the final chunk of a re-ingested file."""

    def test_single_chunk_triggers_rebuild(self):
        """Single-chunk file: chunk 0/0 is the final chunk → rebuild triggered."""
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()

        # Simulate stored file with different hash
        stored_file = MagicMock()
        stored_file.id = "file-1"
        stored_file.hash = "old-hash"
        file_repo.get_file_by_id.return_value = type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": stored_file,
        })()

        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        service.rebuild_projection = MagicMock(return_value=type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })())

        context = make_context(
            file_hash="new-hash",
            chunk_index=0,
            total_chunks=1,
        )
        service.materialize_file_context("test-bank", context, "memory-1")

        # rebuild should have been called because chunk_index == total_chunks - 1
        service.rebuild_projection.assert_called_once()

    def test_chunk_zero_triggers_rebuild(self):
        """Multi-chunk file: chunk 0 (first chunk) triggers rebuild.

        Rebuild is triggered on chunk 0, not the final chunk, so that old
        chunks are pruned before any new chunks are ingested. This prevents
        rebuild from pruning the file_chunks rows of chunks ingested earlier
        in the same re-ingest session.
        """
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()

        stored_file = MagicMock()
        stored_file.id = "file-1"
        stored_file.hash = "old-hash"
        file_repo.get_file_by_id.return_value = type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": stored_file,
        })()

        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        service.rebuild_projection = MagicMock(return_value=type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })())

        # Chunk 0 of 2 — first chunk, rebuild
        context = make_context(
            file_hash="new-hash",
            chunk_index=0,
            total_chunks=2,
        )
        service.materialize_file_context("test-bank", context, "memory-1")

        # rebuild should have been called on chunk 0
        service.rebuild_projection.assert_called_once()

    def test_non_first_chunk_no_rebuild(self):
        """Multi-chunk file: chunks after chunk 0 do NOT trigger rebuild."""
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()

        stored_file = MagicMock()
        stored_file.id = "file-1"
        stored_file.hash = "old-hash"
        file_repo.get_file_by_id.return_value = type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": stored_file,
        })()

        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        service.rebuild_projection = MagicMock(return_value=type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })())

        # Chunk 1 of 2 — not first, no rebuild
        context = make_context(
            file_hash="new-hash",
            chunk_index=1,
            total_chunks=2,
        )
        service.materialize_file_context("test-bank", context, "memory-1")

        # rebuild should NOT have been called (already done on chunk 0)
        service.rebuild_projection.assert_not_called()

    def test_same_hash_no_rebuild(self):
        """Same hash → no rebuild regardless of chunk index."""
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()

        stored_file = MagicMock()
        stored_file.id = "file-1"
        stored_file.hash = "same-hash"
        file_repo.get_file_by_id.return_value = type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": stored_file,
        })()

        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        service.rebuild_projection = MagicMock(return_value=type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })())

        # Same hash — no rebuild even on final chunk
        context = make_context(
            file_hash="same-hash",
            chunk_index=0,
            total_chunks=1,
        )
        service.materialize_file_context("test-bank", context, "memory-1")

        service.rebuild_projection.assert_not_called()

    def test_new_file_no_rebuild(self):
        """New file (no stored file) → no rebuild."""
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()

        file_repo.get_file_by_id.return_value = type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })()

        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        service.rebuild_projection = MagicMock(return_value=type("Result", (), {
            "is_ko": False,
            "is_ok": True,
            "value": None,
        })())

        context = make_context(
            file_hash="new-hash",
            chunk_index=0,
            total_chunks=1,
        )
        service.materialize_file_context("test-bank", context, "memory-1")

        service.rebuild_projection.assert_not_called()