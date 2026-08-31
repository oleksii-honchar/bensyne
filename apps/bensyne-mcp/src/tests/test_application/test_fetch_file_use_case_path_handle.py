"""Unit tests for FetchFileUseCase path_handle support (Task T3).

Covers the D-2/D-3/D-5 behaviors introduced by T3:
- resolution via ``path_handle`` alone (no file_id)
- regression: resolution via ``file_id`` alone behaves exactly as before
- success response always carries top-level ``file_id`` and ``path_handle``
- validation: at least one ref required -> ``FILE_REF_REQUIRED`` (replaces
  ``FILE_ID_REQUIRED``), details carry BOTH received values
- FILE_NOT_FOUND with a supplied file_id -> conflation candidates (trailing
  16 hex chars) + hint, each candidate with path_handle
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.utils.result import ErrorWithDetails, Result

NOW = datetime(2026, 1, 1, 0, 0, 0)

# A realistic 32-hex file id (real files in the bank end with distinct tails).
REAL_FILE_ID = "file_3cfb2e47c9343c293eed39f6b5dda5958"
# A chimeric id: middle is bogus but the trailing 16 hex chars match the real file.
CHIMERIC_FILE_ID = "file_1111222233334444555566667777" + REAL_FILE_ID[-16:]
PATH_HANDLE = "researcher/phase1_framing/130-proceed-on-waive.md"


def _a_file(
    id: str = REAL_FILE_ID,
    path: str = "/tmp/personas/researcher/researcher/phase1_framing/130-proceed-on-waive.md",
    source_type: SourceType = SourceType.AGENT_PERSONA,
    metadata: dict | None = None,
    total_chunks: int = 1,
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
        total_chunks=total_chunks,
        average_importance=0.5,
        metadata=metadata or {},
        created_at=NOW,
        updated_at=NOW,
    )



def _a_chunk(
    id: str = "c1",
    file_id: str = REAL_FILE_ID,
    memory_id: str = "mem_1",
    chunk_index: int = 0,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=1,
        end_line=10,
        content_hash="abc",
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
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
def logger() -> MagicMock:
    return MagicMock()



@pytest.fixture
def use_case(
    mnemosyne_client: MagicMock,
    file_service: MagicMock,
    logger: MagicMock,
) -> FetchFileUseCase:
    return FetchFileUseCase(
        mnemosyne_client=mnemosyne_client,
        file_service=file_service,
        logger=logger,
    )



# ---------------------------------------------------------------
# Resolve via path_handle (no file_id)
# ---------------------------------------------------------------



class TestFetchFileResolveByPathHandle:
    def test_returns_content_when_only_path_handle(
        self,
        use_case: FetchFileUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """fetchFile with only path_handle (no file_id) returns matching content."""
        file = _a_file(metadata={"path_handle": PATH_HANDLE})
        chunks = [_a_chunk()]
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "Persona node content"}

        result = use_case.execute(
            {"path_handle": PATH_HANDLE, "memory_bank": "bank"}
        )
        assert result.is_ok is True
        val = result.value
        assert val["content"] == "Persona node content"
        assert val["reconstruction_status"] == "complete"

    def test_resolution_uses_resolve_file_ref_with_both_refs(
        self,
        use_case: FetchFileUseCase,
        file_service: MagicMock,
    ) -> None:
        """The use case delegates to file_service.resolve_file_ref(file_id, path_handle)."""
        file = _a_file(metadata={"path_handle": PATH_HANDLE})
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok([])

        use_case.execute({"file_id": "some_id", "path_handle": PATH_HANDLE, "memory_bank": "bank"})
        file_service.resolve_file_ref.assert_called_once_with("some_id", PATH_HANDLE)


# ---------------------------------------------------------------
# Regression: file_id alone behaves as before
# ---------------------------------------------------------------


class TestFetchFileRegressionByFileId:
    def test_content_exactly_as_before_with_only_file_id(
        self,
        use_case: FetchFileUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Calling with only a valid file_id returns content exactly as before."""
        file = _a_file()
        chunks = [_a_chunk()]
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "Hello world"}

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value
        assert val["content"] == "Hello world"
        assert val["reconstruction_status"] == "complete"
        assert [c["memory_id"] for c in val["chunks"]] == ["mem_1"]


    def test_resolve_ref_called_with_file_id_and_none_handle(
        self,
        use_case: FetchFileUseCase,
        file_service: MagicMock,
    ) -> None:
        file = _a_file()
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok([])
        use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        file_service.resolve_file_ref.assert_called_once_with(REAL_FILE_ID, None)


# ---------------------------------------------------------------
# Success output: top-level file_id + path_handle ALWAYS present
# ---------------------------------------------------------------



class TestFetchFileTopLevelRefs:
    def test_top_level_file_id_and_path_handle_present_in_success(
        self,
        use_case: FetchFileUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """Success response contains top-level file_id and path_handle."""
        file = _a_file(
            id=REAL_FILE_ID,
            metadata={"path_handle": PATH_HANDLE},
        )
        chunks = [_a_chunk()]
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        val = result.value
        assert val["file_id"] == REAL_FILE_ID
        assert val["path_handle"] == PATH_HANDLE

    def test_top_level_refs_present_when_include_metadata_false(
        self,
        use_case: FetchFileUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """file_id/path_handle are present even when include_metadata=false (default)."""
        file = _a_file(
            id=REAL_FILE_ID,
            path="/tmp/personas/marker/personas/agent-personas/" + PATH_HANDLE,
            metadata={"path_handle": PATH_HANDLE},
        )
        chunks = [_a_chunk()]
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute(
            {"file_id": REAL_FILE_ID, "memory_bank": "bank", "include_metadata": False}
        )
        assert result.is_ok is True
        val = result.value
        assert val["file_id"] == REAL_FILE_ID
        assert val["path_handle"] == PATH_HANDLE
        assert val["file"] is None  # metadata block is not present

    def test_path_handle_derived_when_metadata_absent(
        self,
        use_case: FetchFileUseCase,
        mnemosyne_client: MagicMock,
        file_service: MagicMock,
    ) -> None:
        """When the file has no metadata.path_handle, the response derives it."""
        file = _a_file(
            id=REAL_FILE_ID,
            path="/Users/x/Documents/agent-rules-n-skills/agent-personas/" + PATH_HANDLE,
            metadata={},
        )
        chunks = [_a_chunk()]
        file_service.resolve_file_ref.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_client.get.return_value = {"content": "x"}

        result = use_case.execute({"file_id": REAL_FILE_ID, "memory_bank": "bank"})
        assert result.is_ok is True
        assert result.value["path_handle"] == PATH_HANDLE



# ---------------------------------------------------------------
# Validation: FILE_REF_REQUIRED replaces FILE_ID_REQUIRED
# ---------------------------------------------------------------



class TestFetchFileRefRequiredValidation:
    def test_neither_file_id_nor_path_handle_is_error(
        self,
        use_case: FetchFileUseCase,
    ) -> None:
        result = use_case.validate_params({})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_REF_REQUIRED"
        details = result.errors[0].details
        assert details == {"file_id": None, "path_handle": None}

        assert "FILE_ID_REQUIRED" not in {e.error_code for e in result.errors}


    def test_both_empty_strings_is_error(
        self,
        use_case: FetchFileUseCase,
    ) -> None:
        result = use_case.validate_params({"file_id": "", "path_handle": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_REF_REQUIRED"
        assert result.errors[0].details == {"file_id": "", "path_handle": ""}


    def test_file_id_alone_passes_validation(
        self,
        use_case: FetchFileUseCase,
    ) -> None:
        result = use_case.validate_params({"file_id": "f1"})
        assert result.is_ok is True

    def test_path_handle_alone_passes_validation(
        self,
        use_case: FetchFileUseCase,
    ) -> None:
        result = use_case.validate_params({"path_handle": "agent-a/00-entry.md"})
        assert result.is_ok is True

    def test_file_id_required_no_longer_in_validation_path(
        self,
        use_case: FetchFileUseCase,
    ) -> None:
        """FILE_ID_REQUIRED no longer appears in this use case's validation path."""
        result = use_case.validate_params({})
        codes = {e.error_code for e in result.errors}
        assert "FILE_ID_REQUIRED" not in codes
        assert "FILE_REF_REQUIRED" in codes



# ---------------------------------------------------------------
# FILE_NOT_FOUND with chimeric file_id -> conflation candidates + hint
# ---------------------------------------------------------------



class TestFetchFileNotFoundCandidates:
    def test_chimeric_file_id_yields_candidates_with_path_handle(
        self,
        use_case: FetchFileUseCase,
        file_service: MagicMock,
    ) -> None:
        """chimeric file_id that resolves to nothing returns FILE_NOT_FOUND
        with details.candidates listing the real file sharing the id's trailing
        16 hex chars, each with path_handle, plus the conflation hint."""
        real_file = _a_file(
            id=REAL_FILE_ID,
            path="/Users/x/Documents/agent-rules-n-skills/agent-personas/" + PATH_HANDLE,
            metadata={"path_handle": PATH_HANDLE},
        )
        file_service.resolve_file_ref.return_value = Result.ok(None)
        file_service.file_repository.find_files_by_id_suffix.return_value = Result.ok([real_file])
        file_service.get_chunks_by_file_id.return_value = Result.ok([])  # defensive

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
        real_file.id.endswith(tail) is True
        file_service.file_repository.find_files_by_id_suffix.assert_called_once_with(tail)



    def test_candidates_empty_when_no_suffix_match(
        self,
        use_case: FetchFileUseCase,
        file_service: MagicMock,
    ) -> None:
        file_service.resolve_file_ref.return_value = Result.ok(None)
        file_service.file_repository.find_files_by_id_suffix.return_value = Result.ok([])
        result = use_case.execute({"file_id": "file_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert result.errors[0].details["candidates"] == []


    def test_supplied_file_id_without_match_builds_no_candidates(
        self,
        use_case: FetchFileUseCase,
        file_service: MagicMock,
    ) -> None:
        """When only path_handle is supplied and it does not resolve, FILE_NOT_FOUND
        carries no candidates (candidates require an id suffix)."""
        file_service.resolve_file_ref.return_value = Result.ok(None)
        result = use_case.execute({"path_handle": "no/such/file.md", "memory_bank": "bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert "candidates" not in result.errors[0].details
