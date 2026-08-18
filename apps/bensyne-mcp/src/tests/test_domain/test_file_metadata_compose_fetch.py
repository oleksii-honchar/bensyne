"""Unit tests for FileMetadata.compose_fetch — the full fetch shape composed
inside the aggregate (Task 11, Option 3).

The aggregate owns the fetch composition (dedup by memory_id, sort by
(chunk_index, start_line), whole-file reconstruction with gap indicators, and
the neighbor window). These tests pin the composed BODY shape directly against
the aggregate so FetchFileUseCase can be a pure delegator that only wraps the
body with the optional `file` block.

The composed body carries exactly four keys:
    content, chunks, reconstruction_status, missing_chunks

Default (whole-file) mode: 6-key chunk dicts.
Neighbor mode: content="" + 7-key chunk dicts (+ section_header).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File
from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.models.file_chunk_model import ContentType as CT
from src.domain.models.file_model import FileStatus, SourceType
from src.utils.result import Result

NOW = datetime(2026, 1, 1, 0, 0, 0)


def _file(id: str = "f1", path: str = "/tmp/test.txt") -> File:
    return File(
        id=id,
        path=path,
        source_type=SourceType.AGENT_SESSIONS,
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
        metadata={},
        created_at=NOW,
        updated_at=NOW,
    )


def _chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
    start_line: int = 1,
    end_line: int = 10,
    section_header: str | None = None,
    content_hash: str | None = "abc",
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=start_line,
        end_line=end_line,
        content_hash=content_hash,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=section_header,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _aggregate(chunks: list[FileChunk]) -> FileMetadata:
    result = FileMetadata.of(_file(), chunks=chunks, relations=[])
    assert result.is_ok
    return result.value


def _mnemosyne(contents: dict[str, str]):
    """Callable mirroring MnemosyneClient.get — returns {"content": ...} or None."""
    return lambda mid: {"content": contents[mid]} if mid in contents else None


# ---------------------------------------------------------------------------
# Whole-file composition
# ---------------------------------------------------------------------------


class TestComposeFetchWhole:
    def test_composes_content_from_ordered_chunks(self) -> None:
        chunks = [
            _chunk(id="c1", memory_id="mem_1", chunk_index=0, start_line=1, end_line=10),
            _chunk(id="c2", memory_id="mem_2", chunk_index=1, start_line=11, end_line=20),
        ]
        agg = _aggregate(chunks)
        mnemosyne = _mnemosyne({"mem_1": "Line 1 to 10", "mem_2": "Line 11 to 20"})

        result = agg.compose_fetch(mnemosyne)

        assert result.is_ok is True
        body = result.value
        assert set(body.keys()) == {"content", "chunks", "reconstruction_status", "missing_chunks"}
        assert body["content"] == "Line 1 to 10\nLine 11 to 20"
        assert body["reconstruction_status"] == "complete"
        assert body["missing_chunks"] == []
        assert len(body["chunks"]) == 2

    def test_chunk_dicts_are_six_keys(self) -> None:
        agg = _aggregate([_chunk(id="c1", memory_id="mem_1", chunk_index=0)])
        result = agg.compose_fetch(_mnemosyne({"mem_1": "Some content"}))

        assert result.is_ok is True
        c = result.value["chunks"][0]
        assert set(c.keys()) == {
            "memory_id",
            "chunk_index",
            "start_line",
            "end_line",
            "content",
            "chunk_hash",
        }
        assert c["memory_id"] == "mem_1"
        assert c["chunk_index"] == 0
        assert c["start_line"] == 1
        assert c["end_line"] == 10
        assert c["content"] == "Some content"
        assert c["chunk_hash"] == "abc"

    def test_sorts_by_chunk_index_then_start_line(self) -> None:
        # Insertion order is scrambled; composition must sort by (chunk_index, start_line).
        agg = _aggregate(
            [
                _chunk(id="c3", memory_id="mem_3", chunk_index=2, start_line=21, end_line=30),
                _chunk(id="c1", memory_id="mem_1", chunk_index=0, start_line=1, end_line=10),
                _chunk(id="c2", memory_id="mem_2", chunk_index=1, start_line=11, end_line=20),
            ]
        )
        result = agg.compose_fetch(
            _mnemosyne({"mem_1": "Chunk 0", "mem_2": "Chunk 1", "mem_3": "Chunk 2"})
        )

        assert result.is_ok is True
        body = result.value
        assert body["content"] == "Chunk 0\nChunk 1\nChunk 2"
        assert [c["chunk_index"] for c in body["chunks"]] == [0, 1, 2]

    def test_deduplicates_by_memory_id(self) -> None:
        agg = _aggregate(
            [
                _chunk(id="c1", memory_id="mem_1", chunk_index=0),
                _chunk(id="c2", memory_id="mem_1", chunk_index=1),  # duplicate memory_id
            ]
        )
        result = agg.compose_fetch(_mnemosyne({"mem_1": "Deduplicated content"}))

        assert result.is_ok is True
        body = result.value
        assert len(body["chunks"]) == 1
        assert body["chunks"][0]["memory_id"] == "mem_1"
        assert body["content"] == "Deduplicated content"

    def test_gap_indicator_and_partial_when_memory_missing(self) -> None:
        agg = _aggregate(
            [
                _chunk(id="c1", memory_id="mem_1", chunk_index=0),
                _chunk(id="c2", memory_id="mem_2", chunk_index=1),
                _chunk(id="c3", memory_id="mem_3", chunk_index=2),
            ]
        )
        result = agg.compose_fetch(_mnemosyne({"mem_1": "Chunk 0", "mem_3": "Chunk 2"}))

        assert result.is_ok is True
        body = result.value
        assert body["reconstruction_status"] == "partial"
        assert body["missing_chunks"] == ["mem_2"]
        assert "<< missing chunk" in body["content"]
        # The missing chunk's entry still carries its chunk_hash + position.
        missing_entry = next(c for c in body["chunks"] if c["memory_id"] == "mem_2")
        assert missing_entry["content"] == ""
        assert missing_entry["chunk_hash"] == "abc"

    def test_empty_chunks_yield_partial_empty_body(self) -> None:
        # The chunk-fetch-failure path composes an empty aggregate → the
        # degraded (partial) body, identical to the old _build_partial_response.
        agg = _aggregate([])
        result = agg.compose_fetch(_mnemosyne({}))

        assert result.is_ok is True
        body = result.value
        assert body["content"] == ""
        assert body["chunks"] == []
        assert body["reconstruction_status"] == "partial"
        assert body["missing_chunks"] == []

    def test_compose_fetch_emits_no_events(self) -> None:
        # The fetch path composes content without emitting
        # FileContentComposedEvent (byte-identity with the pre-Task-11 fetch).
        agg = _aggregate([_chunk(id="c1", memory_id="mem_1", chunk_index=0)])
        result = agg.compose_fetch(_mnemosyne({"mem_1": "x"}))

        assert result.is_ok is True
        assert result.events == []


# ---------------------------------------------------------------------------
# Neighbor-chunk window
# ---------------------------------------------------------------------------


def _five_chunks(file_id: str = "f1") -> list[FileChunk]:
    return [
        _chunk(
            id=f"c{i}",
            file_id=file_id,
            memory_id=f"mem_{i}",
            chunk_index=i,
            start_line=i * 10 + 1,
            end_line=(i + 1) * 10,
            section_header=f"Section {i}" if i % 2 == 0 else None,
        )
        for i in range(5)
    ]


class TestComposeFetchNeighbor:
    def test_window_returns_seven_key_chunks_with_empty_content(self) -> None:
        agg = _aggregate(_five_chunks())
        mnemosyne = lambda mid: {"content": f"content of {mid}"}

        result = agg.compose_fetch(mnemosyne, center_chunk_index=2, adjacent_chunks=1)

        assert result.is_ok is True
        body = result.value
        assert body["content"] == ""
        assert [c["chunk_index"] for c in body["chunks"]] == [1, 2, 3]
        for c in body["chunks"]:
            assert set(c.keys()) == {
                "memory_id",
                "chunk_index",
                "start_line",
                "end_line",
                "content",
                "section_header",
                "chunk_hash",
            }
        by_index = {c["chunk_index"]: c for c in body["chunks"]}
        assert by_index[1]["memory_id"] == "mem_1"
        assert by_index[1]["section_header"] is None
        assert by_index[2]["section_header"] == "Section 2"
        assert by_index[3]["content"] == "content of mem_3"
        assert body["reconstruction_status"] == "complete"
        assert body["missing_chunks"] == []

    def test_clamps_window_at_start_of_file(self) -> None:
        agg = _aggregate(_five_chunks())
        result = agg.compose_fetch(_mnemosyne({}), center_chunk_index=0, adjacent_chunks=2)

        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [0, 1, 2]

    def test_clamps_window_at_end_of_file(self) -> None:
        agg = _aggregate(_five_chunks())
        result = agg.compose_fetch(_mnemosyne({}), center_chunk_index=4, adjacent_chunks=2)

        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [2, 3, 4]

    def test_zero_adjacent_returns_center_only(self) -> None:
        agg = _aggregate(_five_chunks())
        result = agg.compose_fetch(_mnemosyne({}), center_chunk_index=2, adjacent_chunks=0)

        assert result.is_ok is True
        assert [c["chunk_index"] for c in result.value["chunks"]] == [2]

    def test_center_below_zero_is_ko_without_querying_mnemosyne(self) -> None:
        agg = _aggregate(_five_chunks())
        calls: list[str] = []
        mnemosyne = lambda mid: calls.append(mid) or {"content": f"c{mid}"}

        result = agg.compose_fetch(mnemosyne, center_chunk_index=-1, adjacent_chunks=1)

        assert result.is_ko is True
        assert result.errors[0].error_code == "CENTER_CHUNK_INDEX_OUT_OF_RANGE"
        assert calls == []

    def test_center_at_total_chunks_is_ko(self) -> None:
        agg = _aggregate(_five_chunks())
        result = agg.compose_fetch(_mnemosyne({}), center_chunk_index=5, adjacent_chunks=1)

        assert result.is_ko is True
        assert result.errors[0].error_code == "CENTER_CHUNK_INDEX_OUT_OF_RANGE"

    def test_neighbor_missing_memory_marks_partial(self) -> None:
        agg = _aggregate(_five_chunks())
        # Only mem_2 is present in the window [1,2,3]; mem_1 and mem_3 missing.
        result = agg.compose_fetch(
            _mnemosyne({"mem_2": "content of mem_2"}), center_chunk_index=2, adjacent_chunks=1
        )

        assert result.is_ok is True
        body = result.value
        assert body["reconstruction_status"] == "partial"
        assert sorted(body["missing_chunks"]) == ["mem_1", "mem_3"]
        present = next(c for c in body["chunks"] if c["memory_id"] == "mem_2")
        assert present["content"] == "content of mem_2"
