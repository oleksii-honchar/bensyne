"""FileService — application service orchestrating file metadata operations.

Uses the FileMetadataAggregate for aggregate-level operations and the
repository pattern to interact with storage. Emits domain events on
state changes. All operations return Result[T].
"""

from __future__ import annotations

from typing import List, Optional

import structlog.stdlib
from src.domain.aggregates.file_metadata_aggregate import FileMetadataAggregate
from src.domain.entities.file import File
from src.domain.entities.file_chunk import FileChunk
from src.domain.entities.file_relation import FileRelation, RelationType
from src.domain.interfaces import FileChunkRepository, FileRelationRepository, FileRepository
from src.domain.result import ErrorWithDetails, Result


class FileService:
    """Application service for file metadata operations.

    Orchestrates file creation, updates, deletion, chunk management,
    relation management, and content reconstruction using the
    FileMetadataAggregate and repository pattern.

    Memory storage model:
        Memories are NOT stored locally by Bensyne. They live in Mnemosyne
        (external memory service). The `memory_client` field is an optional
        pass-through to Mnemosyne. The primary production path for file
        content reconstruction goes through `FetchFileUseCase` which uses
        `mnemosyne_client.get()` directly.
    """

    def __init__(
        self,
        file_repository: FileRepository,
        chunk_repository: FileChunkRepository,
        relation_repository: FileRelationRepository,
        logger: structlog.stdlib.BoundLogger,
        memory_client: Optional[object] = None,
    ) -> None:
        self.file_repository = file_repository
        self.chunk_repository = chunk_repository
        self.relation_repository = relation_repository
        # Pass-through to Mnemosyne for memory content lookup during
        # file reconstruction. Not local storage — memories live in Mnemosyne.
        self.memory_client = memory_client
        self._logger = logger

    # ------------------------------------------------------------------
    # Structured logging helpers
    # ------------------------------------------------------------------

    def _log_info(self, event: str, **kwargs: object) -> None:
        """Emit an info-level structured log entry."""
        self._logger.info(event, service="file_service", **kwargs)

    def _log_debug(self, event: str, **kwargs: object) -> None:
        """Emit a debug-level structured log entry."""
        self._logger.debug(event, service="file_service", **kwargs)

    # ------------------------------------------------------------------
    # File CRUD
    # ------------------------------------------------------------------

    def create_file(self, file_data: dict) -> Result[File]:
        """Create a new file entity.

        Uses File.of() for validation and event emission, then persists
        via the file repository. Propagates domain events from File.of().
        """
        file_id = file_data.get("id", "<unknown>")
        self._log_info("Creating file", method="create_file", file_id=file_id)

        file_result = File.of(file_data)
        if file_result.is_ko:
            return file_result

        save_result = self.file_repository.save_file(file_result.value)
        if save_result.is_ok:
            self._log_debug("File saved to repository", method="create_file", file_id=file_id)
        # Propagate events from File.of() alongside any from the save
        if save_result.is_ok and file_result.has_events():
            return Result.ok(save_result.value, events=file_result.events)
        return save_result

    def update_file(
        self,
        file_id: str,
        hash: Optional[str] = None,
        file_type: Optional[str] = None,
        size: Optional[int] = None,
        language: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Result[File]:
        """Update file metadata fields.

        Finds the existing file, applies update_metadata(), and persists.
        Returns Result.ko if file not found or already deleted.
        """
        self._log_info("Updating file", method="update_file", file_id=file_id)

        find_result = self.file_repository.get_file_by_id(file_id)
        if not find_result.is_ok or find_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])

        file = find_result.value
        update_result = file.update_metadata(
            hash=hash,
            file_type=file_type,
            size=size,
            language=language,
            summary=summary,
        )
        if update_result.is_ko:
            return update_result

        save_result = self.file_repository.save_file(update_result.value)
        # Propagate events from update_metadata alongside any from the save
        if save_result.is_ok and update_result.has_events():
            return Result.ok(save_result.value, events=update_result.events)
        return save_result

    def delete_file(self, file_id: str) -> Result[File]:
        """Delete a file by marking it as DELETED.

        Returns Result.ko if file not found or already deleted.
        Emits FileDeletedEvent on success.
        """
        self._log_info("Deleting file", method="delete_file", file_id=file_id)

        find_result = self.file_repository.get_file_by_id(file_id)
        if not find_result.is_ok or find_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])

        file = find_result.value
        delete_result = file.mark_deleted()
        if delete_result.is_ko:
            return delete_result

        save_result = self.file_repository.save_file(delete_result.value)
        # Propagate events from mark_deleted
        if save_result.is_ok and delete_result.has_events():
            return Result.ok(save_result.value, events=delete_result.events)
        return save_result

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    def create_chunk(
        self,
        file_id: str,
        memory_id: str,
        chunk_index: int,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Result[FileChunk]:
        """Create a file-chunk relationship via the aggregate.

        Loads the aggregate, adds the chunk (enforcing uniqueness),
        persists the updated file metadata and the new chunk.
        Emits FileChunkAddedEvent on success.
        """
        self._log_info("Creating chunk", method="create_chunk", file_id=file_id, memory_id=memory_id)
        return self._with_aggregate(file_id, lambda agg: self._add_chunk_to_aggregate(
            agg, file_id, memory_id, chunk_index, start_line, end_line,
        ), method="create_chunk")

    def _add_chunk_to_aggregate(
        self,
        file_metadata: FileMetadataAggregate,
        file_id: str,
        memory_id: str,
        chunk_index: int,
        start_line: Optional[int],
        end_line: Optional[int],
    ) -> Result[FileChunk]:
        """Build a FileChunk via FileChunk.of(), add to aggregate, persist."""
        sl = start_line if start_line is not None else 0
        el = end_line if end_line is not None else 0

        chunk_result = FileChunk.of({
            "id": f"fc_{file_id}_{memory_id}",
            "file_id": file_id,
            "memory_id": memory_id,
            "chunk_index": chunk_index,
            "start_line": sl,
            "end_line": el,
        })
        if chunk_result.is_ko:
            return chunk_result

        chunk = chunk_result.value
        add_result = file_metadata.add_chunk(chunk)
        if add_result.is_ko:
            return add_result

        updated_file_metadata = add_result.value

        # Persist updated file metadata
        file_save_result = self.file_repository.save_file(updated_file_metadata.file)
        if file_save_result.is_ko:
            return file_save_result

        # Persist the chunk
        save_result = self.chunk_repository.save_chunk(chunk)
        if save_result.is_ko:
            return save_result

        # Combine events from chunk creation + aggregate add
        all_events = chunk_result.events + add_result.events
        return Result.ok(save_result.value, events=all_events)

    # ------------------------------------------------------------------
    # Relation operations
    # ------------------------------------------------------------------

    def create_relation(
        self,
        source_file_id: str,
        target_file_id: str,
        relation_type: RelationType,
        strength: float = 1.0,
        description: Optional[str] = None,
    ) -> Result[FileRelation]:
        """Create a file relation via the aggregate.

        Loads the aggregate for the source file, adds the relation,
        and persists the new relation entity.
        Emits FileRelationCreatedEvent on success.
        """
        self._log_info("Creating relation", method="create_relation",
                       source_file_id=source_file_id, target_file_id=target_file_id)
        return self._with_aggregate(source_file_id, lambda agg: self._add_relation_to_aggregate(
            agg, source_file_id, target_file_id, relation_type, strength, description,
        ), method="create_relation")

    def _add_relation_to_aggregate(
        self,
        file_metadata: FileMetadataAggregate,
        source_file_id: str,
        target_file_id: str,
        relation_type: RelationType,
        strength: float,
        description: Optional[str],
    ) -> Result[FileRelation]:
        """Build a FileRelation via FileRelation.of(), add to aggregate, persist."""
        relation_result = FileRelation.of({
            "id": f"fr_{source_file_id}_{target_file_id}",
            "source_file_id": source_file_id,
            "target_file_id": target_file_id,
            "relation_type": relation_type,
            "strength": strength,
            "description": description,
        })
        if relation_result.is_ko:
            return relation_result

        relation = relation_result.value
        add_result = file_metadata.add_relation(relation)
        if add_result.is_ko:
            return add_result

        # Persist the relation
        save_result = self.relation_repository.save_relation(relation)
        if save_result.is_ko:
            return save_result

        all_events = relation_result.events + add_result.events
        return Result.ok(save_result.value, events=all_events)

    # ------------------------------------------------------------------
    # Aggregate queries
    # ------------------------------------------------------------------

    def get_file(
        self,
        file_id: str,
        include_chunks: bool = True,
        include_relations: bool = True,
        relation_types: Optional[List[RelationType]] = None,
    ) -> Result[FileMetadataAggregate]:
        """Retrieve file with configurable chunks and relations as an aggregate.

        Args:
            file_id: The file identifier.
            include_chunks: Whether to load chunks from the repository.
            include_relations: Whether to load relations from the repository.
            relation_types: Optional filter for relation types (only applied
                when include_relations is True).
        """
        self._log_info("Getting file", method="get_file", file_id=file_id)
        return self._build_aggregate(
            file_id,
            include_chunks=include_chunks,
            include_relations=include_relations,
            relation_types=relation_types,
        )

    def _build_aggregate(
        self,
        file_id: str,
        include_chunks: bool = True,
        include_relations: bool = True,
        relation_types: Optional[List[RelationType]] = None,
        method: str = "get_file",
    ) -> Result[FileMetadataAggregate]:
        """Build a FileMetadataAggregate from repository data."""
        file_result = self.file_repository.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])

        file = file_result.value

        chunks: List[FileChunk] = []
        if include_chunks:
            chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
            chunks = chunks_result.value if chunks_result.is_ok else []

        relations: List[FileRelation] = []
        if include_relations:
            relations_result = self.relation_repository.get_relations_by_file_id(file_id)
            relations = relations_result.value if relations_result.is_ok else []

        if relation_types:
            relations = [r for r in relations if r.relation_type in relation_types]

        self._log_debug("Aggregate built", method=method, file_id=file_id,
                        chunk_count=len(chunks), relation_count=len(relations))
        return FileMetadataAggregate.of(file, chunks=chunks, relations=relations)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_file(self, file_data: dict) -> Result[File]:
        """Create or update a file entity.

        Checks if a file exists by path; if so, updates via File.of()
        with the new data, otherwise creates a new file.
        """
        file_id = file_data.get("id", "<unknown>")
        self._log_info("Upserting file", method="upsert_file", file_id=file_id)
        path = file_data.get("path", "")
        existing_result = self.file_repository.get_file_by_path(path)

        if existing_result.is_ok and existing_result.value is not None:
            # Update existing — rebuild with new data
            update_data = {**file_data}
            # Preserve existing id
            update_data["id"] = existing_result.value.id
            file_result = File.of(update_data)
            if file_result.is_ko:
                return file_result
            return self.file_repository.save_file(file_result.value)
        else:
            # Create new
            return self.create_file(file_data)

    # ------------------------------------------------------------------
    # Memory-based lookup
    # ------------------------------------------------------------------

    def find_files_by_memory(self, memory_id: str) -> Result[List[File]]:
        """Find files associated with a memory via chunk lookup."""
        self._log_info("Finding files by memory", method="find_files_by_memory", memory_id=memory_id)
        chunk_result = self.chunk_repository.get_chunk_by_memory_id(memory_id)
        if not chunk_result.is_ok or chunk_result.value is None:
            return Result.ok([])

        chunk = chunk_result.value
        file_result = self.file_repository.get_file_by_id(chunk.file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ok([])

        return Result.ok([file_result.value])

    # ------------------------------------------------------------------
    # Chunk removal and count
    # ------------------------------------------------------------------

    def remove_chunk(self, file_id: str, memory_id: str) -> Result[FileMetadataAggregate]:
        """Remove a chunk from a file by memory_id via the aggregate.

        Loads the aggregate, calls aggregate.remove_chunk(memory_id),
        persists the updated file and removes the chunk from the repository.
        Returns the updated aggregate on success.
        """
        self._log_info("Removing chunk", method="remove_chunk", file_id=file_id, memory_id=memory_id)
        return self._with_aggregate(file_id, lambda agg: self._remove_chunk_from_aggregate(
            agg, file_id, memory_id,
        ), method="remove_chunk")

    def _remove_chunk_from_aggregate(
        self,
        file_metadata: FileMetadataAggregate,
        file_id: str,
        memory_id: str,
    ) -> Result[FileMetadataAggregate]:
        """Remove chunk from aggregate, persist updated file, delete chunk from repo."""
        remove_result = file_metadata.remove_chunk(memory_id)
        if remove_result.is_ko:
            return remove_result

        updated_aggregate = remove_result.value

        # Persist updated file metadata
        file_save_result = self.file_repository.save_file(updated_aggregate.file)
        if file_save_result.is_ko:
            return file_save_result

        # Find and delete the chunk from the repository
        chunk = next((c for c in file_metadata.chunks if c.memory_id == memory_id), None)
        if chunk:
            self.chunk_repository.delete_chunk(chunk.id)

        return Result.ok(updated_aggregate, events=remove_result.events)

    def get_chunks_count_by_file_id(self, file_id: str) -> Result[int]:
        """Return the number of chunks for a given file."""
        chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
        if not chunks_result.is_ok:
            return chunks_result
        return Result.ok(len(chunks_result.value))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _with_aggregate(
        self,
        file_id: str,
        operation,
        method: str = "with_aggregate",
    ) -> Result:
        """Load aggregate for file_id, execute operation, return result.

        Returns Result.ko if file not found.
        """
        aggregate_result = self._build_aggregate(file_id, include_chunks=True, include_relations=True,
                                                 method=method)
        if aggregate_result.is_ko:
            return aggregate_result

        self._log_debug("Aggregate loaded", method=method, file_id=file_id)
        return operation(aggregate_result.value)
