"""Unit tests for GetPersonaStatusUseCase (Task 4 / spec §4.4, ADR-8).

The use case classifies every memory in a persona bank into exactly one of three
buckets and derives the materialization signal:
  * node_memories               — file-backed (id present in the chunk index)
  * occasional_memories         — non-file, non-expired (valid_until null or future)
  * expired_occasional_memories — non-file, valid_until in the past

Dependencies (MnemosyneClient.list_memory_validities,
FileChunkRepository.get_file_backed_memory_ids) are mocked: this is a pure
application-layer unit test. Assertions are on the returned count dict only —
no logger assertions.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pytest

from src.application.use_cases.get_persona_status_use_case import (
    GetPersonaStatusUseCase,
)
from src.utils.structured_logging import LoggerMock


PAST = "2000-01-01T00:00:00"
FUTURE = "2999-01-01T00:00:00"


def _use_case(
    validities: List[Tuple[str, Optional[str]]],
    file_backed: set[str],
    threshold: int = 10,
) -> GetPersonaStatusUseCase:
    client = _mock_client(validities)
    chunk_repository = _mock_chunk_repository(file_backed)
    return GetPersonaStatusUseCase(
        mnemosyne_client=client,
        file_chunk_repository=chunk_repository,
        logger=LoggerMock(),
        materialization_threshold=threshold,
    )


def _mock_client(validities: List[Tuple[str, Optional[str]]]):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.list_memory_validities.return_value = validities
    return client


def _mock_chunk_repository(file_backed: set[str]):
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.get_file_backed_memory_ids.return_value = file_backed
    return repo


def _execute(use_case: GetPersonaStatusUseCase) -> dict:
    result = use_case.execute({"memory_bank": "agent-persona_architect"})
    assert result.is_ok, f"use case returned ko: {result.errors}"
    return result.value


# ---------------------------------------------------------------------------
# Classification — exact counts for all five fields
# ---------------------------------------------------------------------------


class TestClassification:
    def test_mixed_bank_counts_all_five_fields_exactly(self) -> None:
        """file-backed + non-file-active + non-file-expired all land in the right buckets."""
        # 3 node (file-backed), 2 occasional (active non-file), 2 expired (past non-file)
        validities = [
            ("node1", None),
            ("node2", None),
            ("node3", FUTURE),
            ("occ1", None),
            ("occ2", FUTURE),
            ("exp1", PAST),
            ("exp2", PAST),
        ]
        file_backed = {"node1", "node2", "node3"}
        uc = _use_case(validities, file_backed)

        value = _execute(uc)

        assert value["total"] == 7
        assert value["node_memories"] == 3
        assert value["occasional_memories"] == 2
        assert value["expired_occasional_memories"] == 2
        # 2 occasional < default threshold 10 -> not due
        assert value["materialization_due"] is False

    def test_total_equals_sum_of_node_and_non_file(self) -> None:
        """total must equal node_memories + occasional_memories + expired_occasional_memories."""
        validities = [
            ("node1", None),
            ("occ1", None),
            ("occ2", None),
            ("exp1", PAST),
        ]
        file_backed = {"node1"}
        uc = _use_case(validities, file_backed)

        value = _execute(uc)

        assert value["total"] == 4
        assert value["node_memories"] + value["occasional_memories"] + value["expired_occasional_memories"] == 4

    def test_node_memory_with_past_valid_until_is_still_a_node(self) -> None:
        """File association wins over temporality: a file-backed memory is a node even if its valid_until is past."""
        validities = [
            ("node1", PAST),  # file-backed, past expiry -> still node, NOT counted as expired
            ("occ1", PAST),  # non-file, past -> expired
        ]
        file_backed = {"node1"}
        uc = _use_case(validities, file_backed)

        value = _execute(uc)

        assert value["node_memories"] == 1
        assert value["expired_occasional_memories"] == 1
        assert value["occasional_memories"] == 0
        assert value["total"] == 2

    def test_empty_bank_all_zeros_not_due(self) -> None:
        validities: List[Tuple[str, Optional[str]]] = []
        uc = _use_case(validities, set())
        value = _execute(uc)

        assert value == {
            "total": 0,
            "node_memories": 0,
            "occasional_memories": 0,
            "expired_occasional_memories": 0,
            "materialization_due": False,
        }

    def test_only_expired_non_file(self) -> None:
        validities = [
            ("exp1", PAST),
            ("exp2", PAST),
        ]
        uc = _use_case(validities, set())
        value = _execute(uc)

        assert value["total"] == 2
        assert value["node_memories"] == 0
        assert value["occasional_memories"] == 0
        assert value["expired_occasional_memories"] == 2
        assert value["materialization_due"] is False

    def test_response_shape_is_exactly_the_five_fields(self) -> None:
        """The response contract is the five snake_case keys and nothing else."""
        uc = _use_case([("node1", None)], {"node1"})
        value = _execute(uc)

        assert set(value.keys()) == {
            "total",
            "node_memories",
            "occasional_memories",
            "expired_occasional_memories",
            "materialization_due",
        }


# ---------------------------------------------------------------------------
# Materialization threshold — flips at the boundary, configurable
# ---------------------------------------------------------------------------


class TestMaterializationThreshold:
    def test_due_true_when_occasional_exactly_at_default_threshold(self) -> None:
        """10 non-expired non-file memories with the default threshold -> due."""
        validities = [(f"node{i}", None) for i in range(3)] + [(f"occ{i}", None) for i in range(10)]
        file_backed = {f"node{i}" for i in range(3)}
        uc = _use_case(validities, file_backed)  # default threshold 10
        value = _execute(uc)

        assert value["occasional_memories"] == 10
        assert value["materialization_due"] is True

    def test_due_false_one_below_default_threshold(self) -> None:
        validities = [(f"occ{i}", None) for i in range(9)]
        uc = _use_case(validities, set())
        value = _execute(uc)

        assert value["occasional_memories"] == 9
        assert value["materialization_due"] is False

    def test_expired_do_not_count_toward_due(self) -> None:
        """Only non-expired occasional memories drive materialization_due."""
        # 9 active + 5 expired, threshold 10 -> 9 < 10 -> not due
        validities = [(f"occ{i}", None) for i in range(9)] + [(f"exp{i}", PAST) for i in range(5)]
        uc = _use_case(validities, set())
        value = _execute(uc)

        assert value["occasional_memories"] == 9
        assert value["expired_occasional_memories"] == 5
        assert value["materialization_due"] is False

    def test_threshold_is_configurable_lower(self) -> None:
        """A lower threshold flips due at fewer occasional memories."""
        validities = [(f"occ{i}", None) for i in range(3)]
        uc = _use_case(validities, set(), threshold=3)
        value = _execute(uc)

        assert value["occasional_memories"] == 3
        assert value["materialization_due"] is True

    def test_threshold_is_configurable_higher(self) -> None:
        validities = [(f"occ{i}", None) for i in range(3)]
        uc = _use_case(validities, set(), threshold=100)
        value = _execute(uc)

        assert value["occasional_memories"] == 3
        assert value["materialization_due"] is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_memory_bank_is_a_validation_error(self) -> None:
        uc = _use_case([], set())
        result = uc.execute({})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes

    def test_empty_memory_bank_is_a_validation_error(self) -> None:
        uc = _use_case([], set())
        result = uc.execute({"memory_bank": ""})

        assert result.is_ko
        codes = [e.error_code for e in (result.errors or [])]
        assert "MEMORY_BANK_REQUIRED" in codes


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
