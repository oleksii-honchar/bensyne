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

from typing import Dict, List, Optional

from src.infrastructure.mnemosyne.client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.entities.file import File
from src.domain.entities.file_chunk import FileChunk
from src.domain.interfaces import FileChunkRepository, FileRepository
from src.domain.result import ErrorWithDetails, Result


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

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that file_id is present and non-empty."""
        file_id = parameters.get("file_id")
        if not file_id:
            return Result.ko([ErrorWithDetails("FILE_ID_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute file content reconstruction."""
        file_id = parameters["file_id"]
        include_metadata = parameters.get("include_metadata", False)

        # Step 1: Get file
        file_result = self.file_repository.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])
        file = file_result.value

        # Step 2: Get chunks
        chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
        if not chunks_result.is_ok:
            return self._build_partial_response(file, include_metadata)

        chunks: List[FileChunk] = chunks_result.value

        # Step 3: Deduplicate by memory_id (keep first occurrence)
        chunks = self._deduplicate_chunks(chunks)

        # Step 4: Sort by chunk_index (primary), start_line (secondary)
        chunks = sorted(chunks, key=lambda c: (c.chunk_index, c.start_line))

        # Step 5: Reconstruct content and build chunk details
        content, chunk_details, missing = self._reconstruct_content(chunks)

        # Step 6: Determine reconstruction status
        status = "complete" if chunks and not missing else "partial"

        return Result.ok({
            "file": self._file_to_dict(file, len(chunks)) if include_metadata else None,
            "content": content,
            "chunks": chunk_details,
            "reconstruction_status": status,
            "missing_chunks": missing,
        })

    # ------------------------------------------------------------------
    # Reconstruction
    # ------------------------------------------------------------------

    def _deduplicate_chunks(self, chunks: List[FileChunk]) -> List[FileChunk]:
        """Remove duplicate chunks by memory_id, keeping first occurrence."""
        seen: set[str] = set()
        result: List[FileChunk] = []
        for chunk in chunks:
            if chunk.memory_id not in seen:
                seen.add(chunk.memory_id)
                result.append(chunk)
        return result

    def _reconstruct_content(
        self,
        chunks: List[FileChunk],
    ) -> tuple[str, List[dict], List[str]]:
        """Reconstruct file content from ordered chunks.

        Returns (content, chunk_details, missing_memory_ids).
        """
        content_parts: List[str] = []
        chunk_details: List[dict] = []
        missing: List[str] = []

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

    def _chunk_to_dict(self, chunk: FileChunk, content: Optional[str]) -> dict:
        """Convert a FileChunk to a dict for the response."""
        return {
            "memory_id": chunk.memory_id,
            "chunk_index": chunk.chunk_index,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": content or "",
        }

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------

    def _build_partial_response(self, file: File, include_metadata: bool) -> Result[dict]:
        """Build a partial response when chunk retrieval fails."""
        return Result.ok({
            "file": self._file_to_dict(file, 0) if include_metadata else None,
            "content": "",
            "chunks": [],
            "reconstruction_status": "partial",
            "missing_chunks": [],
        })

    def _file_to_dict(self, file: File, total_chunks: int) -> dict:
        """Convert a File entity to a dict for the response."""
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
        }
