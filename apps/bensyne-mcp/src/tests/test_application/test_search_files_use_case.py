"""Unit tests for SearchFilesUseCase — two-phase file search.

Phase 1: query memories via mnemosyne client.
Phase 2: enrich with file metadata, delegated to FileEnrichmentService (D7).

Response contract (stable per result):
- Non-file memory: memory_id, file=None, matched_memories=[], related_files_count,
  content_preview, importance, relevance_score (+ additive file_enrichment key).
- File-backed group: file{...}, matched_memories[...], related_files_count,
  related_files, summary, source_type_enrichment (+ additive file_enrichment block).

Filters (source_type / file_role) apply to phase-2 grouping only — pure memories
are never dropped.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk, ContentType
from src.domain.file_relation_entity import FileRelation, RelationType, Direction
from src.domain.models.file_model import FileRole
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock

NOW = datetime(2026, 1, 1, 0, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.AGENT_SESSIONS,
    file_role: FileRole | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
    total_chunks: int = 0,
    average_importance: float = 0.5,
    metadata: dict[str, str] | None = None,
    hash: str | None = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=file_role,
        hash=hash,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=FileStatus.INDEXED,
        summary=summary,
        total_chunks=total_chunks,
        average_importance=average_importance,
        metadata=metadata if metadata is not None else {},
        created_at=NOW,
        updated_at=NOW,
    )


def _a_chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
    section_header: str | None = None,
    content_hash: str | None = "abc",
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=0,
        content_hash=content_hash,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=section_header,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type=None,
    description: str | None = "",
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type or RelationType.SIBLING,
        strength=1.0,
        direction=Direction.UNIDIRECTIONAL,
        description=description,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mnemosyne_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def file_service() -> MagicMock:
    """FileService is the use case's only file-layer dependency (D11).

    Spec'd so mocks only expose real FileService methods and their Result
    return types are honored.
    """
    from src.application.services.file_service import FileService as _FileService

    return MagicMock(spec=_FileService)


@pytest.fixture
def logger() -> LoggerMock:
    return LoggerMock()


@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    file_service: MagicMock,
    logger: LoggerMock,
) -> SearchFilesUseCase:
    return SearchFilesUseCase(
        mnemosyne_client=mnemosyne_client,
        file_service=file_service,
        logger=logger,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseValidation:
    def test_returns_ko_when_query_empty(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({"query": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_returns_ko_when_query_missing(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_returns_ok_when_query_present(self, use_case: SearchFilesUseCase) -> None:
        result = use_case.validate_params({"query": "search term"})
        assert result.is_ok is True
        assert result.value["query"] == "search term"


# ---------------------------------------------------------------------------
# Phase 1 — No memories recalled
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseNoMemories:
    def test_returns_empty_results_when_no_memories(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        mnemosyne_client.recall.return_value = []

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        assert result.value["results"] == []
        assert result.value["total_count"] == 0


# ---------------------------------------------------------------------------
# Phase 2 — Memories with no file context (non-file memories)
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseNonFileMemories:
    def test_returns_non_file_memory_when_no_chunk(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Memory without file context should appear as non-file result."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Some memory", "importance": 0.8, "relevance_score": 0.9},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(None)

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1
        # Non-file memory: no file context
        r = results[0]
        assert r["memory_id"] == "mem_1"
        assert r["file"] is None
        assert r["matched_memories"] == []

    def test_non_file_result_has_stable_key_set(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Non-file result key set must be a superset of the legacy contract."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Some memory", "importance": 0.8, "relevance_score": 0.9},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(None)

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})

        r = result.value["results"][0]
        legacy_keys = {
            "memory_id",
            "file",
            "matched_memories",
            "related_files_count",
            "content_preview",
            "importance",
            "relevance_score",
        }
        assert legacy_keys <= set(r.keys())


# ---------------------------------------------------------------------------
# Phase 2 — Memories with file context (enriched)
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseFileMemories:
    def test_returns_enriched_file_result(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Memory with file context should be enriched with REAL file metadata."""
        file = _a_file(
            id="f1",
            path="/tmp/test.txt",
            keywords=["test"],
            tags=["docs"],
            total_chunks=3,
            average_importance=0.72,
            metadata={"session.id": "ses_123"},
        )
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "File content preview", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1
        r = results[0]
        assert r["file"] is not None
        # Real entity values — no zeros/empty stubs
        assert r["file"]["id"] == "f1"
        assert r["file"]["path"] == "/tmp/test.txt"
        assert r["file"]["keywords"] == ["test"]
        assert r["file"]["tags"] == ["docs"]
        assert r["file"]["total_chunks"] == 3
        assert r["file"]["average_importance"] == 0.72
        assert r["file"]["metadata"] == {"session.id": "ses_123"}
        assert len(r["matched_memories"]) == 1
        assert r["matched_memories"][0]["id"] == "mem_1"
        assert r["related_files_count"] == 0

    def test_file_result_has_stable_key_set(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """File result key set must be a superset of the legacy contract."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})

        r = result.value["results"][0]
        legacy_keys = {
            "file",
            "matched_memories",
            "related_files_count",
            "related_files",
            "summary",
            "source_type_enrichment",
        }
        assert legacy_keys <= set(r.keys())

    def test_file_dict_has_stable_key_set(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """File dict key set must be a superset of the legacy contract."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})

        r = result.value["results"][0]
        legacy_file_keys = {
            "id",
            "path",
            "source_type",
            "file_role",
            "total_chunks",
            "keywords",
            "tags",
            "average_importance",
            "metadata",
        }
        assert legacy_file_keys <= set(r["file"].keys())

    def test_groups_memories_by_file(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Multiple memories from same file should be grouped."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1", chunk_index=0)
        chunk2 = _a_chunk(id="c2", file_id="f1", memory_id="mem_2", chunk_index=1)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "First chunk", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Second chunk", "importance": 0.6, "relevance_score": 0.8},
        ]

        # Both memories map to same file
        file_service.get_chunk_by_memory_id.side_effect = lambda mid: Result.ok({"mem_1": chunk1, "mem_2": chunk2}.get(mid))
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = [chunk1, chunk2]

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 1  # Grouped into single file result
        r = results[0]
        assert r["file"]["id"] == "f1"
        assert len(r["matched_memories"]) == 2

    def test_matched_memories_include_chunk_info(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Matched memories should include chunk_index and the stored section_header."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(
            file_id="f1",
            memory_id="mem_1",
            chunk_index=2,
            section_header="## Chapter 3 — Enrichment Design Notes",
        )

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content preview here", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        r = result.value["results"][0]
        matched = r["matched_memories"]
        assert len(matched) == 1
        m = matched[0]
        assert m["id"] == "mem_1"
        assert m["chunk_index"] == 2
        assert m["importance"] == 0.7
        assert m["relevance_score"] == 0.85
        # section_header comes from the chunk row, not a stub ""
        assert m["section_header"] == "## Chapter 3 — Enrichment Design Notes"

    def test_matched_memory_section_header_none_when_chunk_has_no_header(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Chunk without a stored header ⇒ section_header is None (not stub "")."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})

        m = result.value["results"][0]["matched_memories"][0]
        assert m["section_header"] is None


# ---------------------------------------------------------------------------
# Phase 2 — Relations inclusion
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseRelations:
    def test_related_files_count_without_relations_flag(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """When include_relations is False (default), still count relations."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": False,
            }
        )

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["related_files_count"] == 1
        # Relations not expanded
        assert "related_files" not in r or r.get("related_files") is None

    def test_related_files_included_when_flag_true(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """When include_relations is True, include related file details."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2")
        related_file = _a_file(id="f2", path="/tmp/related.txt")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)

        def file_by_id_side_effect(file_id: str) -> Result[File]:
            if file_id == "f2":
                return Result.ok(related_file)
            return Result.ok(file)

        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = file_by_id_side_effect
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["related_files_count"] == 1
        assert "related_files" in r
        assert len(r["related_files"]) == 1
        rf = r["related_files"][0]
        assert rf["id"] == "f2"
        assert rf["path"] == "/tmp/related.txt"


# ---------------------------------------------------------------------------
# Phase 2 — source_type / file_role filters
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseFilters:
    def test_source_type_filter_keeps_only_matching_files(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """source_type=agent-sessions ⇒ only agent-sessions files in phase-2 output."""
        session_file = _a_file(id="f1", path="/tmp/session.md", source_type=SourceType.AGENT_SESSIONS)
        other_file = _a_file(id="f2", path="/repo/README.md", source_type=SourceType.VAULT)
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        chunk2 = _a_chunk(id="c2", file_id="f2", memory_id="mem_2")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Session note", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Readme line", "importance": 0.6, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.side_effect = lambda mid: Result.ok({"mem_1": chunk1, "mem_2": chunk2}.get(mid))

        def file_by_id(file_id: str) -> Result[File]:
            return Result.ok(session_file if file_id == "f1" else other_file)

        file_service.get_file_by_id.side_effect = file_by_id
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "source_type": "agent-sessions",
            }
        )

        assert result.is_ok is True
        file_results = [r for r in result.value["results"] if r["file"] is not None]
        assert len(file_results) == 1
        assert file_results[0]["file"]["id"] == "f1"
        assert file_results[0]["file"]["source_type"] == "agent-sessions"

    def test_file_role_filter_keeps_only_matching_files(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """file_role=docs ⇒ only docs-role files in phase-2 output."""
        docs_file = _a_file(id="f1", path="/tmp/guide.md", file_role=FileRole.DOCS)
        code_file = _a_file(id="f2", path="/app/main.py", file_role=FileRole.CODE)
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        chunk2 = _a_chunk(id="c2", file_id="f2", memory_id="mem_2")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Guide note", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Code line", "importance": 0.6, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.side_effect = lambda mid: Result.ok({"mem_1": chunk1, "mem_2": chunk2}.get(mid))

        def file_by_id(file_id: str) -> Result[File]:
            return Result.ok(docs_file if file_id == "f1" else code_file)

        file_service.get_file_by_id.side_effect = file_by_id
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "file_role": "docs",
            }
        )

        assert result.is_ok is True
        file_results = [r for r in result.value["results"] if r["file"] is not None]
        assert len(file_results) == 1
        assert file_results[0]["file"]["id"] == "f1"
        assert file_results[0]["file"]["file_role"] == "docs"

    def test_filters_do_not_drop_pure_memories(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Filters apply to phase-2 grouping only — pure memories always pass through."""
        vault_file = _a_file(id="f1", path="/vault/README.md", source_type=SourceType.VAULT)
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Readme line", "importance": 0.6, "relevance_score": 0.8},
            {"id": "mem_2", "content": "Standalone memory", "importance": 0.5, "relevance_score": 0.6},
        ]
        file_service.get_chunk_by_memory_id.side_effect = lambda mid: Result.ok(chunk if mid == "mem_1" else None)
        file_service.get_file_by_id.side_effect = lambda fid: Result.ok(vault_file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "source_type": "agent-sessions",
            }
        )

        assert result.is_ok is True
        results = result.value["results"]
        # Pure memory survives the filter; the non-matching (vault) file's memory is
        # demoted to non-file (never dropped). Both rows end up with file=None.
        non_file = [r for r in results if r["file"] is None]
        file_results = [r for r in results if r["file"] is not None]
        assert len(non_file) == 2
        assert {r["memory_id"] for r in non_file} == {"mem_1", "mem_2"}
        # No file-backed group survived the filter
        assert file_results == []


# ---------------------------------------------------------------------------
# Phase 2 — Mixed results (file + non-file memories)
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseMixedResults:
    def test_returns_both_file_and_non_file_memories(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Results should contain both file-backed and non-file memories."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "File content", "importance": 0.7, "relevance_score": 0.9},
            {"id": "mem_2", "content": "Standalone memory", "importance": 0.5, "relevance_score": 0.6},
        ]
        # mem_1 has file context, mem_2 does not
        file_service.get_chunk_by_memory_id.side_effect = lambda mid: Result.ok(chunk if mid == "mem_1" else None)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        results = result.value["results"]
        assert len(results) == 2

        # Non-file memory comes first (added to all_results before file results)
        r_non_file = [r for r in results if r["file"] is None]
        r_file = [r for r in results if r["file"] is not None]
        assert len(r_non_file) == 1
        assert len(r_file) == 1

        assert r_non_file[0]["memory_id"] == "mem_2"
        assert r_file[0]["file"]["id"] == "f1"


# ---------------------------------------------------------------------------
# Limit enforcement
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseLimit:
    def test_respects_limit_parameter(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Limit should be passed to mnemosyne recall."""
        mnemosyne_client.recall.return_value = []

        use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "limit": 3,
            }
        )

        mnemosyne_client.recall.assert_called_once_with("search term", 3)

    def test_uses_default_limit(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Default limit of 10 should be used when not specified."""
        mnemosyne_client.recall.return_value = []

        use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        mnemosyne_client.recall.assert_called_once_with("search term", 10)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestSearchFilesUseCaseErrors:
    def test_handles_recall_failure(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When mnemosyne recall fails, return Result.ko."""
        mnemosyne_client.recall.return_value = Result.ko([ErrorWithDetails("DATABASE_ERROR", {})])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ko is True
        assert result.errors[0].error_code == "DATABASE_ERROR"

    def test_continues_when_chunk_lookup_fails(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """If chunk lookup fails, treat memory as non-file (don't crash)."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ko([ErrorWithDetails("DB_ERROR", {})])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        # Should still return ok — treat as non-file memory
        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["file"] is None

    def test_continues_when_file_lookup_fails(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """If file lookup fails, treat memory as non-file."""
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {})])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        r = result.value["results"][0]
        assert r["file"] is None


# ---------------------------------------------------------------------------
# Dual-hash wire contract (D15) — searchFiles delegation to the shared
# FileEnrichmentService (D7): enrichment hashes flow through automatically
# ---------------------------------------------------------------------------


class TestSearchFilesEnrichmentHashDelegation:
    """searchFiles results carry the same enrichment hashes as recall via the
    shared FileEnrichmentService — the use case itself has no hash logic."""

    def test_enrichment_block_carries_hashes_via_shared_service(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """file_enrichment in searchFiles results surfaces file_hash (File row)
        and chunk_hash (the memory's chunk row) — same contract as recall."""
        file_hash = "f" * 64
        chunk_hash = "c" * 64
        file = _a_file(id="f1", path="/tmp/test.txt", hash=file_hash)
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0, content_hash=chunk_hash)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})
        assert result.is_ok is True

        r = result.value["results"][0]
        enrichment = r["file_enrichment"]
        assert enrichment is not None
        assert enrichment["file"]["file_hash"] == file_hash
        assert enrichment["chunk_hash"] == chunk_hash

    def test_enrichment_hash_null_tolerant_for_legacy_rows(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Legacy rows (NULL File.hash / NULL chunk content_hash) ⇒ hashes are
        null in the enrichment block, not errors (S7)."""
        file = _a_file(id="f1", hash=None)
        chunk = _a_chunk(file_id="f1", memory_id="mem_1", chunk_index=0, content_hash=None)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_relations_by_file_id.return_value = Result.ok([])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})
        assert result.is_ok is True

        enrichment = result.value["results"][0]["file_enrichment"]
        assert enrichment is not None
        assert enrichment["file"]["file_hash"] is None
        assert enrichment["chunk_hash"] is None

    def test_pure_memory_enrichment_null_in_search(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Pure memory (no chunk row) ⇒ file_enrichment stays null (D7) —
        no hashes invented for absent rows."""
        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.7, "relevance_score": 0.85},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(None)

        result = use_case.execute({"query": "q", "memory_bank": "my_bank"})
        assert result.is_ok is True

        r = result.value["results"][0]
        assert r["file_enrichment"] is None


# ---------------------------------------------------------------------------
# AC 9 — D44 edges population: searchFiles related_files[] carry
# summary + description (additive-only)
# ---------------------------------------------------------------------------


class TestRelatedFilesSummaryDescriptionSurfacing:
    """D44 (spec §3.2): searchFiles related_files[] entries gain the target
    File's whole-file `summary` + the traversed relation's `description` —
    additive-only, existing keys (id/path/source_type/relation_type/strength)
    untouched."""

    def test_related_files_entries_carry_target_summary_when_set(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Target File WITH a summary ⇒ related_files[] entry carries `summary`
        equal to it."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2", description="Link from A to B")
        related_file = _a_file(id="f2", path="/tmp/related.txt", summary="Summary of file B")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = (
            lambda fid: Result.ok(related_file) if fid == "f2" else Result.ok(file)
        )
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        r = result.value["results"][0]
        rf = r["related_files"][0]
        assert rf["id"] == "f2"
        assert rf["summary"] == "Summary of file B"

    def test_related_files_entries_carry_none_summary_when_target_has_no_summary(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Target File WITHOUT a summary ⇒ related_files[] entry carries
        `summary: None` (additive key always present)."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2")
        related_file = _a_file(id="f2", path="/tmp/related.txt", summary=None)

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = (
            lambda fid: Result.ok(related_file) if fid == "f2" else Result.ok(file)
        )
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        rf = result.value["results"][0]["related_files"][0]
        assert "summary" in rf
        assert rf["summary"] is None

    def test_related_files_entries_carry_traversed_relation_description(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """related_files[] entries carry the traversed relation's `description`."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2", description="Related by shared context")
        related_file = _a_file(id="f2", path="/tmp/related.txt")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = (
            lambda fid: Result.ok(related_file) if fid == "f2" else Result.ok(file)
        )
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        rf = result.value["results"][0]["related_files"][0]
        assert rf["id"] == "f2"
        assert rf["description"] == "Related by shared context"

    def test_related_files_entries_carry_none_description_when_unset(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """related_files[] entry for a relation with no description (None)
        carries `description: None` (additive key always present)."""
        file = _a_file(id="f1", path="/tmp/test.txt")
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        relation = _a_relation(source_file_id="f1", target_file_id="f2", description=None)
        related_file = _a_file(id="f2", path="/tmp/related.txt")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = (
            lambda fid: Result.ok(related_file) if fid == "f2" else Result.ok(file)
        )
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        rf = result.value["results"][0]["related_files"][0]
        assert "description" in rf
        assert rf["description"] is None

    def test_related_files_regression_existing_keys_intact(
        self,
        use_case: SearchFilesUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Regression: existing related_files keys (id/path/source_type/
        relation_type/strength) remain intact alongside the new keys."""
        file = _a_file(id="f1", path="/tmp/test.txt", source_type=SourceType.AGENT_SESSIONS)
        chunk = _a_chunk(file_id="f1", memory_id="mem_1")
        # Custom relation: non-default strength + real description (helper defaults
        # to strength=1.0, description="")
        relation = FileRelation(
            id="r_regr",
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
            strength=0.75,
            direction=Direction.UNIDIRECTIONAL,
            description="Extends base spec",
            created_at=NOW,
            updated_at=NOW,
        )
        related_file = _a_file(id="f2", path="/tmp/related.txt", source_type=SourceType.VAULT, summary="Spec file B")

        mnemosyne_client.recall.return_value = [
            {"id": "mem_1", "content": "Content", "importance": 0.5, "relevance_score": 0.8},
        ]
        file_service.get_chunk_by_memory_id.return_value = Result.ok(chunk)
        file_service.get_file_by_id.return_value = Result.ok(file)
        file_service.get_related_file_by_id.side_effect = (
            lambda fid: Result.ok(related_file) if fid == "f2" else Result.ok(file)
        )
        file_service.get_relations_by_file_id.return_value = Result.ok([relation])
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])

        result = use_case.execute(
            {
                "query": "search term",
                "memory_bank": "my_bank",
                "include_relations": True,
            }
        )

        assert result.is_ok is True
        rf = result.value["results"][0]["related_files"][0]
        # Existing keys — unchanged contract
        assert rf["id"] == "f2"
        assert rf["path"] == "/tmp/related.txt"
        assert rf["source_type"] == "vault"
        assert rf["relation_type"] == "sibling"
        assert rf["strength"] == 0.75
        # New additive keys coexist
        assert rf["summary"] == "Spec file B"
        assert rf["description"] == "Extends base spec"
