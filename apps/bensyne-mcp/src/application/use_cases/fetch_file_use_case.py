"""FetchFileUseCase — reconstruct file content from its memory chunks.

Flow:
1. Look up file by file_id
2. Retrieve all chunks via file_chunks table
3. Order by chunk_index (primary), start_line (secondary)
4. Deduplicate by memory_id
5. Reconstruct content with line continuity
6. Return with file metadata
"""

from __future__ import annotations

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_entity import File
from src.domain.file_chunk_entity import FileChunk
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository


class FetchFileUseCase(BaseUseCase[dict, dict]):
    """Orchestrates file content reconstruction from memory chunks."""

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        file_repository: FileRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.chunk_repository = chunk_repository
        self.file_repository = file_repository

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

        Default mode (no center_chunk_index): whole-file reconstruction — unchanged.
        Neighbor mode (center_chunk_index provided): returns only the window
        [center - N .. center + N] clamped to 0..total_chunks-1, in ascending
        order, each chunk with content + position + section_header.

        Validation decisions (Result pattern, no exceptions):
        - adjacent_chunks outside 0..5 ⇒ ADJACENT_CHUNKS_OUT_OF_RANGE
        - center_chunk_index < 0 or >= total_chunks ⇒ CENTER_CHUNK_INDEX_OUT_OF_RANGE
          (error over clamp: signals bad agent input rather than silently shifting the window)
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
        file_result = self.file_repository.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])
        file = file_result.value

        self.logger.debug(
            "File retrieved",
            use_case="fetch_file",
            method="execute_internal",
            file_id=file_id,
            file_path=file.path,
        )

        # Step 2: Get chunks
        chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
        if not chunks_result.is_ok:
            return self._build_partial_response(file, include_metadata)

        chunks: list[FileChunk] = chunks_result.value

        self.logger.debug(
            "Chunks retrieved",
            use_case="fetch_file",
            method="execute_internal",
            file_id=file_id,
            chunks_count=len(chunks),
        )

        # Step 3: Deduplicate by memory_id (keep first occurrence)
        chunks = self._deduplicate_chunks(chunks)

        # Step 4: Sort by chunk_index (primary), start_line (secondary)
        chunks = sorted(chunks, key=lambda c: (c.chunk_index, c.start_line))

        # Step 4b: Neighbor mode — validate center and slice the window
        if center_chunk_index is not None:
            total_chunks = len(chunks)
            if center_chunk_index < 0 or center_chunk_index >= total_chunks:
                return Result.ko(
                    [
                        ErrorWithDetails(
                            "CENTER_CHUNK_INDEX_OUT_OF_RANGE",
                            {
                                "center_chunk_index": center_chunk_index,
                                "total_chunks": total_chunks,
                            },
                        )
                    ]
                )
            low = max(0, center_chunk_index - adjacent_chunks)
            high = min(total_chunks - 1, center_chunk_index + adjacent_chunks)
            return self._build_neighbor_response(file, chunks[low : high + 1], include_metadata)

        # Step 5: Reconstruct content and build chunk details
        content, chunk_details, missing = self._reconstruct_content(chunks)

        # Step 6: Determine reconstruction status
        status = "complete" if chunks and not missing else "partial"

        self.logger.info(
            "File content reconstructed",
            use_case="fetch_file",
            method="execute_internal",
            file_id=file_id,
            chunks_count=len(chunk_details),
            status=status,
            missing_chunks_count=len(missing),
        )

        return Result.ok(
            {
                "file": self._file_to_dict(file, len(chunks)) if include_metadata else None,
                "content": content,
                "chunks": chunk_details,
                "reconstruction_status": status,
                "missing_chunks": missing,
            }
        )

    # ------------------------------------------------------------------
    # Reconstruction
    # ------------------------------------------------------------------

    def _deduplicate_chunks(self, chunks: list[FileChunk]) -> list[FileChunk]:
        """Remove duplicate chunks by memory_id, keeping first occurrence."""
        seen: set[str] = set()
        result: list[FileChunk] = []
        for chunk in chunks:
            if chunk.memory_id not in seen:
                seen.add(chunk.memory_id)
                result.append(chunk)
        return result

    def _reconstruct_content(
        self,
        chunks: list[FileChunk],
    ) -> tuple[str, list[dict], list[str]]:
        """Reconstruct file content from ordered chunks.

        Returns (content, chunk_details, missing_memory_ids).
        """
        content_parts: list[str] = []
        chunk_details: list[dict] = []
        missing: list[str] = []

        for chunk in chunks:
            memory = self.mnemosyne_client.get(chunk.memory_id)

            if memory and isinstance(memory, dict) and memory.get("content"):
                content = memory["content"]
                content_parts.append(content)
                chunk_details.append(self._chunk_to_dict(chunk, content))
            else:
                # Missing memory — add gap indicator
                content_parts.append(self._gap_indicator(chunk))
                missing.append(chunk.memory_id)
                chunk_details.append(self._chunk_to_dict(chunk, None))

        return ("\n".join(content_parts), chunk_details, missing)

    def _gap_indicator(self, chunk: FileChunk) -> str:
        """Generate a gap indicator for a missing chunk."""
        return f"<< missing chunk {chunk.memory_id} (index={chunk.chunk_index}, lines={chunk.start_line}-{chunk.end_line}) >>"

    def _chunk_to_dict(self, chunk: FileChunk, content: str | None) -> dict:
        """Convert a FileChunk to a dict for the response.

        `chunk_hash` is the chunk row's stored content_hash (null-tolerant —
        legacy rows without a content hash surface as null, not an error).
        """
        return {
            "memory_id": chunk.memory_id,
            "chunk_index": chunk.chunk_index,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": content or "",
            "chunk_hash": chunk.content_hash,
        }

    # ------------------------------------------------------------------
    # Neighbor-chunk mode
    # ------------------------------------------------------------------

    def _build_neighbor_response(
        self,
        file: File,
        chunks: list[FileChunk],
        include_metadata: bool,
    ) -> Result[dict]:
        """Build the neighbor-mode response for a clamped chunk window.

        Each chunk carries content (mnemosyne lookup by memory_id), position
        (chunk_index, start_line/end_line) and section_header. No full-file
        reconstruction is performed.
        """
        chunk_details: list[dict] = []
        missing: list[str] = []

        for chunk in chunks:
            memory = self.mnemosyne_client.get(chunk.memory_id)
            content: str | None = None
            if memory and isinstance(memory, dict) and memory.get("content"):
                content = memory["content"]
            else:
                missing.append(chunk.memory_id)

            chunk_details.append(
                {
                    "memory_id": chunk.memory_id,
                    "chunk_index": chunk.chunk_index,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": content or "",
                    "section_header": chunk.section_header,
                    "chunk_hash": chunk.content_hash,
                }
            )

        self.logger.info(
            "Neighbor window built",
            use_case="fetch_file",
            method="_build_neighbor_response",
            file_id=file.id,
            window_size=len(chunk_details),
            missing_chunks_count=len(missing),
        )

        return Result.ok(
            {
                "file": self._file_to_dict(file, len(chunks)) if include_metadata else None,
                "content": "",
                "chunks": chunk_details,
                "reconstruction_status": "complete" if not missing else "partial",
                "missing_chunks": missing,
            }
        )

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------

    def _build_partial_response(self, file: File, include_metadata: bool) -> Result[dict]:
        """Build a partial response when chunk retrieval fails."""
        return Result.ok(
            {
                "file": self._file_to_dict(file, 0) if include_metadata else None,
                "content": "",
                "chunks": [],
                "reconstruction_status": "partial",
                "missing_chunks": [],
            }
        )

    def _file_to_dict(self, file: File, total_chunks: int) -> dict:
        """Convert a File entity to a dict for the response.

        `file_hash` is the File row's stored hash (null-tolerant for legacy rows).
        """
        return {
            "id": file.id,
            "path": file.path,
            "source_type": file.source_type.value,
            "file_role": file.file_type or "",
            "total_chunks": total_chunks,
            "keywords": file.aggregated_keywords,
            "tags": file.aggregated_tags,
            "average_importance": 0.5,
            "created_at": file.created_at.isoformat() if file.created_at else None,
            "updated_at": file.updated_at.isoformat() if file.updated_at else None,
            "metadata": {},
            "file_hash": file.hash,
        }
