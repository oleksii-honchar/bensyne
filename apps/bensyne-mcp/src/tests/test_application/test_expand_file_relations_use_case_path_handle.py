"""Unit tests for ExpandFileRelationsUseCase path_handle support (Task T4).

Covers the D-2/D-3/D-5 behaviors introduced by T4, mirroring T3 (fetchFile):
- resolution via ``path_handle`` alone (no file_id)
- regression: resolution via ``file_id`` alone behaves as before
- validation: at least one ref required -> ``FILE_REF_REQUIRED`` (replaces
  ``FILE_ID_REQUIRED``), details carry BOTH received values
- FILE_NOT_FOUND with a supplied file_id -> conflation candidates (trailing
  16 hex chars) + hint, each candidate with path_handle
- enrichment: ``source_file`` and ``related_files[].file`` carry a derived
  ``path_handle`` key when derivable (and only then — so the canonical
  file block emitted when no handle exists is left untouched / shape-pinned)
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.file_relation_entity import Direction, FileRelation, RelationType
from src.utils.result import Result

NOW = datetime(2026, 1, 1, 0, 0, 0)

# A realistic 32-hex file id (real files in the bank end with distinct tails).
REAL_FILE_ID = "file_3cfb2e47c9343c293eed39f6b5dda5958"
# A chimeric id: middle is bogus but the trailing 16 hex chars match the real file.
CHIMERIC_FILE_ID = "file_1111222233334444555566667777" + REAL_FILE_ID[-16:]
PATH_HANDLE = "researcher/phase1_framing/130-proceed-on-waive.md"
PERSONA_PATH = "/Users/x/Documents/agent-rules-n-skills/agent-personas/" + PATH_HANDLE


def _a_file(
    id: str = REAL_FILE_ID,
    path: str = PERSONA_PATH,
    source_type: SourceType = SourceType.AGENT_PERSONA,
    metadata: dict | None = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=None,
        hash=None,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=[],
        aggregated_tags=[],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=0,
        average_importance=0.5,
        metadata=metadata or {},
        created_at=NOW,
        updated_at=NOW,
    )


def _a_aggregate(
    file: File,
    chunks: list[FileChunk] | None = None,
) -> FileMetadata:
    return FileMetadata.of(file, chunks=chunks or [], relations=[]).value


def _a_relation(
    id: str = "r1",
    source_file_id: str = REAL_FILE_ID,
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.SIBLING,
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type,
        strength=1.0,
        direction=Direction.UNIDIRECTIONAL,
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def mnemosyne_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def file_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def relation_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    file_service: MagicMock,
    relation_repo: MagicMock,
    logger: MagicMock,
) -> ExpandFileRelationsUseCase:
    return ExpandFileRelationsUseCase(
        mnemosyne_client=mnemosyne_client,
        file_service=file_service,
        relation_repository=relation_repo,
        logger=logger,
    )


# ---------------------------------------------------------------
# Resolve via path_handle (no file_id)
# ---------------------------------------------------------------


class TestExpandResolveByPathHandle:
    def test_expands_relations_when_only_path_handle(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """expandFileRelations with only path_handle (no file_id) expands relations
        of the resolved source file."""
        source = _a_file(id=REAL_FILE_ID, metadata={"path_handle": PATH_HANDLE})
        related = _a_file(id="f2", path="/tmp/related.txt", source_type=SourceType.AGENT_SESSIONS)
        rel = _a_relation(source_file_id=REAL_FILE_ID, target_file_id="f2")

        file_service.resolve_file_ref.return_value = Result.ok(source)
        # Related files are still fetched via get_file (returns an aggregate).
        file_service.get_file.return_value = Result.ok(_a_aggregate(related))
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"path_handle": PATH_HANDLE, "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value
        assert val["source_file"]["id"] == REAL_FILE_ID
        assert len(val["related_files"]) == 1
        assert val["related_files"][0]["file"]["id"] == "f2"

    def test_relations_queried_by_resolved_file_id(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When resolved by path_handle, relations are looked up by the resolved
        file's id (not the absent input file_id)."""
        source = _a_file(id=REAL_FILE_ID, metadata={"path_handle": PATH_HANDLE})
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({"path_handle": PATH_HANDLE, "memory_bank": "bank"})
        relation_repo.get_relations_by_file_id.assert_called_once_with(REAL_FILE_ID)

    def test_resolution_uses_resolve_file_ref_with_both_refs(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """The use case delegates to file_service.resolve_file_ref(file_id, path_handle)."""
        source = _a_file()
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        use_case.execute({"file_id": "some_id", "path_handle": PATH_HANDLE, "memory_bank": "bank"})
        file_service.resolve_file_ref.assert_called_once_with("some_id", PATH_HANDLE)


# ---------------------------------------------------------------
# Regression: file_id alone behaves as before
# ---------------------------------------------------------------


class TestExpandRegressionByFileId:
    def test_expands_relations_when_only_file_id(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """Calling with only a valid file_id expands relations exactly as before."""
        source = _a_file(id="f1", path="/tmp/source.txt", source_type=SourceType.AGENT_SESSIONS)
        related = _a_file(id="f2", path="/tmp/related.txt", source_type=SourceType.AGENT_SESSIONS)
        rel = _a_relation(source_file_id="f1", target_file_id="f2")

        file_service.resolve_file_ref.return_value = Result.ok(source)
        file_service.get_file.return_value = Result.ok(_a_aggregate(related))
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value
        assert val["source_file"]["id"] == "f1"
        assert len(val["related_files"]) == 1

    def test_resolve_ref_called_with_file_id_and_none_handle(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        source = _a_file(id="f1")
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])
        use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        file_service.resolve_file_ref.assert_called_once_with("f1", None)


# ---------------------------------------------------------------
# Validation: FILE_REF_REQUIRED replaces FILE_ID_REQUIRED
# ---------------------------------------------------------------


class TestExpandRefRequiredValidation:
    def test_neither_file_id_nor_path_handle_is_error(
        self,
        use_case: ExpandFileRelationsUseCase,
    ) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_REF_REQUIRED"
        assert result.errors[0].details == {"file_id": None, "path_handle": None}
        assert "FILE_ID_REQUIRED" not in {e.error_code for e in result.errors}

    def test_both_empty_strings_is_error(
        self,
        use_case: ExpandFileRelationsUseCase,
    ) -> None:
        result = use_case.validate_params({"file_id": "", "path_handle": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_REF_REQUIRED"
        assert result.errors[0].details == {"file_id": "", "path_handle": ""}

    def test_file_id_alone_passes_validation(
        self,
        use_case: ExpandFileRelationsUseCase,
    ) -> None:
        result = use_case.validate_params({"file_id": "f1"})
        assert result.is_ok is True

    def test_path_handle_alone_passes_validation(
        self,
        use_case: ExpandFileRelationsUseCase,
    ) -> None:
        result = use_case.validate_params({"path_handle": "agent-a/00-entry.md"})
        assert result.is_ok is True

    def test_file_id_required_no_longer_in_validation_path(
        self,
        use_case: ExpandFileRelationsUseCase,
    ) -> None:
        """FILE_ID_REQUIRED no longer appears in this use case's validation path."""
        result = use_case.validate_params({})
        codes = {e.error_code for e in result.errors}
        assert "FILE_ID_REQUIRED" not in codes
        assert "FILE_REF_REQUIRED" in codes


# ---------------------------------------------------------------
# FILE_NOT_FOUND with chimeric file_id -> conflation candidates + hint
# ---------------------------------------------------------------


class TestExpandNotFoundCandidates:
    def test_chimeric_file_id_yields_candidates_with_path_handle(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
    ) -> None:
        """chimeric file_id that resolves to nothing returns FILE_NOT_FOUND with
        details.candidates listing the real file sharing the id's trailing 16 hex
        chars, each with path_handle, plus the conflation hint."""
        real_file = _a_file(
            id=REAL_FILE_ID,
            path=PERSONA_PATH,
            metadata={"path_handle": PATH_HANDLE},
        )
        file_service.resolve_file_ref.return_value = Result.ok(None)
        file_service.file_repository.find_files_by_id_suffix.return_value = Result.ok([real_file])

        result = use_case.execute({"file_id": CHIMERIC_FILE_ID, "memory_bank": "bank"})
        assert result.is_ko is True
        error = result.errors[0]
        assert error.error_code == "FILE_NOT_FOUND"
        details = error.details
        assert "file_id" in details
        candidates = details["candidates"]
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["file_id"] == REAL_FILE_ID
        assert candidate["path_handle"] == PATH_HANDLE
        assert "hint" in details
        assert "conflation" in details["hint"]
        assert "path_handle" in details["hint"]

        tail = CHIMERIC_FILE_ID[-16:]
        file_service.file_repository.find_files_by_id_suffix.assert_called_once_with(tail)

    def test_candidates_empty_when_no_suffix_match(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
    ) -> None:
        file_service.resolve_file_ref.return_value = Result.ok(None)
        file_service.file_repository.find_files_by_id_suffix.return_value = Result.ok([])
        result = use_case.execute(
            {"file_id": "file_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "memory_bank": "bank"}
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert result.errors[0].details["candidates"] == []

    def test_supplied_path_handle_without_match_builds_no_candidates(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
    ) -> None:
        """When only path_handle is supplied and it does not resolve, FILE_NOT_FOUND
        carries no candidates (candidates require an id suffix)."""
        file_service.resolve_file_ref.return_value = Result.ok(None)
        result = use_case.execute({"path_handle": "no/such/file.md", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert "candidates" not in result.errors[0].details


# ---------------------------------------------------------------
# Enrichment: source_file carries a derived path_handle when present
# ---------------------------------------------------------------


class TestExpandSourceFileEnrichment:
    def test_source_file_includes_path_handle_when_derivable(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """source_file dict includes a path_handle key with the derived value
        when the source file has a derivable handle (via metadata)."""
        source = _a_file(id=REAL_FILE_ID, metadata={"path_handle": PATH_HANDLE})
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        assert result.value["source_file"]["path_handle"] == PATH_HANDLE

    def test_source_file_path_handle_derived_from_path_marker_when_metadata_absent(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """source_file path_handle is derived from the persona path marker when
        metadata.path_handle is absent."""
        source = _a_file(id=REAL_FILE_ID, path=PERSONA_PATH, metadata={})
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        assert result.value["source_file"]["path_handle"] == PATH_HANDLE

    def test_source_file_omits_path_handle_when_not_derivable(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When no path_handle is derivable, the source_file block is the canonical
        File.to_dict() verbatim (no path_handle key) — preserves the shape-pin."""
        source = _a_file(
            id="f1",
            path="/vault/notes/a.md",
            source_type=SourceType.AGENT_SESSIONS,
            metadata={},
        )
        file_service.resolve_file_ref.return_value = Result.ok(source)
        relation_repo.get_relations_by_file_id.return_value = Result.ok([])

        result = use_case.execute({"file_id": "f1", "memory_bank": "bank"})
        assert result.is_ok is True
        assert result.value["source_file"] == source.to_dict()
        assert "path_handle" not in result.value["source_file"]


# ---------------------------------------------------------------
# Enrichment: related_files[].file carries a derived path_handle when present
# ---------------------------------------------------------------


class TestExpandRelatedFileEnrichment:
    def test_related_file_includes_path_handle_when_derivable(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """related_files[].file includes a path_handle key with the derived value
        when the related file has a derivable handle."""
        source = _a_file(id=REAL_FILE_ID, metadata={"path_handle": PATH_HANDLE})
        related = _a_file(
            id="f2",
            path=PERSONA_PATH,
            metadata={"path_handle": "researcher/phase1_framing/131-other.md"},
        )
        rel = _a_relation(source_file_id=REAL_FILE_ID, target_file_id="f2")

        file_service.resolve_file_ref.return_value = Result.ok(source)
        file_service.get_file.return_value = Result.ok(_a_aggregate(related))
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        rf = result.value["related_files"][0]
        assert rf["file"]["id"] == "f2"
        assert rf["file"]["path_handle"] == "researcher/phase1_framing/131-other.md"

    def test_related_file_omits_path_handle_when_not_derivable(
        self,
        use_case: ExpandFileRelationsUseCase,
        file_service: MagicMock,
        relation_repo: MagicMock,
    ) -> None:
        """When a related file has no derivable handle, its file block is left
        as-is (no path_handle key added)."""
        source = _a_file(id=REAL_FILE_ID, metadata={"path_handle": PATH_HANDLE})
        related = _a_file(
            id="f2",
            path="/tmp/related.txt",
            source_type=SourceType.AGENT_SESSIONS,
            metadata={},
        )
        rel = _a_relation(source_file_id=REAL_FILE_ID, target_file_id="f2")

        file_service.resolve_file_ref.return_value = Result.ok(source)
        file_service.get_file.return_value = Result.ok(_a_aggregate(related))
        relation_repo.get_relations_by_file_id.return_value = Result.ok([rel])

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        rf = result.value["related_files"][0]
        assert rf["file"]["id"] == "f2"
        assert "path_handle" not in rf["file"]
