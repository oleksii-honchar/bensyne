"""FetchFileUseCase — reconstruct file content from its memory chunks.

The use case is a thin orchestrator (Task 11, Option 3): it loads the file
and its chunks through FileService, delegates all composition to the
FileMetadata aggregate (compose_fetch), and wraps the composed body with the
optional ``file`` block. It holds no local reconstruction logic and no chunk
or file repository — composition of invariant state lives in the aggregate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_metadata_aggregate import FileMetadata
from src.utils.result import ErrorWithDetails, Result

if TYPE_CHECKING:
    from src.application.services.file_service import FileService


class FetchFileUseCase(BaseUseCase[dict, dict]):
    """Orchestrates file content reconstruction by delegating to the aggregate."""

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        file_service: FileService,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.file_service = file_service

    ADJACENT_CHUNKS_MIN = 0
    ADJACENT_CHUNKS_MAX = 5

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that file_id is present and non-empty."""
        file_id = parameters.get("file_id")
        if not file_id:
            return Result.ko([ErrorWithDetails("FILE_ID_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute file content reconstruction.

        Default mode (no center_chunk_index): whole-file reconstruction.
        Neighbor mode (center_chunk_index provided): a window
        [center - N .. center + N] clamped to 0..total_chunks-1, each chunk
        with content + position + section_header.

        Validation decisions (Result pattern, no exceptions):
        - adjacent_chunks outside 0..5 ⇒ ADJACENT_CHUNKS_OUT_OF_RANGE
          (input validation, before any load)
        - center_chunk_index not present among stored chunk_index values ⇒
          CENTER_CHUNK_INDEX_OUT_OF_RANGE (raised inside compose_fetch;
          available_chunk_indexes in details; error over clamp: signals bad
          agent input rather than silently shifting the window)
        """
        file_id = parameters["file_id"]
        include_metadata = parameters.get("include_metadata", False)
        center_chunk_index: int | None = parameters.get("center_chunk_index")
        adjacent_chunks: int = parameters.get("adjacent_chunks", 1)

        if center_chunk_index is not None and not (
            self.ADJACENT_CHUNKS_MIN <= adjacent_chunks <= self.ADJACENT_CHUNKS_MAX
        ):
            return Result.ko(
                [
                    ErrorWithDetails(
                        "ADJACENT_CHUNKS_OUT_OF_RANGE",
                        {
                            "adjacent_chunks": adjacent_chunks,
                            "allowed_range": [self.ADJACENT_CHUNKS_MIN, self.ADJACENT_CHUNKS_MAX],
                        },
                    )
                ]
            )

        self.logger.info(
            "Fetching file content",
            use_case="fetch_file",
            method="execute_internal",
            file_id=file_id,
            include_metadata=include_metadata,
            center_chunk_index=center_chunk_index,
            adjacent_chunks=adjacent_chunks if center_chunk_index is not None else None,
        )

        # Step 1: Get file
        file_result = self.file_service.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])
        file = file_result.value

        # Step 2: Get chunks (a fetch failure degrades to an empty aggregate,
        # whose composition yields the partial body — no local composition here).
        chunks_result = self.file_service.get_chunks_by_file_id(file_id)
        chunks: list[FileChunk] = chunks_result.value if chunks_result.is_ok else []

        # Step 3: Delegate composition to the aggregate, then wrap the body
        # with the optional file block. The file block is the canonical
        # File.to_dict() verbatim — a single source at every retrieval site
        # (D24.1 / gate 5); total_chunks is projection state re-aggregated on
        # the write path, so the entity field is authoritative here.
        aggregate_result = FileMetadata.of(file, chunks=chunks, relations=[])
        if aggregate_result.is_ko:
            return aggregate_result
        aggregate = aggregate_result.value

        composed = aggregate.compose_fetch(
            self.mnemosyne_client.get,
            center_chunk_index=center_chunk_index,
            adjacent_chunks=adjacent_chunks,
        )
        if composed.is_ko:
            return composed
        body = composed.value
        if not body:
            return Result.ko([ErrorWithDetails("FETCH_COMPOSE_FAILED", {"file_id": file_id})])

        return Result.ok(
            {
                "file": file.to_dict() if include_metadata else None,
                **body,
            }
        )
