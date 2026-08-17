"""FileService — application service orchestrating file metadata operations.

Uses the FileMetadataAggregate for aggregate-level operations and the
repository pattern to interact with storage. Emits domain events on
state changes. All operations return Result[T].
"""

from __future__ import annotations

import hashlib

import structlog.stdlib
from src.domain.file_metadata_aggregate import FileMetadataAggregate
from src.domain.file_entity import File
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_relation_entity import Direction, FileRelation, RelationType
from src.domain.models.file_context_model import FileContext
from src.domain.models.file_model import FileStatus, SourceType
from src.utils.result import DomainEvent, ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository


def derive_file_id(bank: str, path: str) -> str:
    """Derive the deterministic file id for a bank+path pair (contract rule 2).

    Producers never send file ids — identity is derived so the same logical
    file always maps to the same row within a bank.
    """
    digest = hashlib.sha256(f"{bank}:{path}".encode("utf-8")).hexdigest()[:32]
    return f"file_{digest}"


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
        memory_client: object | None = None,
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
        hash: str | None = None,
        file_type: str | None = None,
        size: int | None = None,
        language: str | None = None,
        summary: str | None = None,
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
        updated_file_result = file.update_metadata(
            hash=hash,
            file_type=file_type,
            size=size,
            language=language,
            summary=summary,
        )
        if updated_file_result.is_ko:
            return updated_file_result

        save_result = self.file_repository.save_file(updated_file_result.value)
        # Propagate events from update_metadata alongside any from the save
        if save_result.is_ok and updated_file_result.has_events():
            return Result.ok(save_result.value, events=updated_file_result.events)
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
        deleted_file_result = file.mark_deleted()
        if deleted_file_result.is_ko:
            return deleted_file_result

        save_result = self.file_repository.save_file(deleted_file_result.value)
        if save_result.is_ko:
            return save_result

        # Forget symmetry (spec §6.4): the file row is SOFT-deleted, so ORM FK
        # CASCADE never fires — remove this file's relation rows explicitly.
        # Relations between other (non-deleted) files are untouched by design.
        relations_result = self.relation_repository.delete_relations_by_file_id(file_id)
        if relations_result.is_ko:
            return relations_result  # type: ignore[return-value]

        # Propagate events from mark_deleted
        if deleted_file_result.has_events():
            return Result.ok(save_result.value, events=deleted_file_result.events)
        return save_result

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    def link_chunk(
        self,
        file_id: str,
        memory_id: str,
        chunk_index: int,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> Result[FileChunk]:
        """Link a memory to a file as a chunk via the aggregate.

        Loads the aggregate, adds the chunk (enforcing uniqueness),
        persists the updated file metadata and the new chunk.
        Emits FileChunkAddedEvent on success.
        """
        self._log_info("Linking chunk", method="link_chunk", file_id=file_id, memory_id=memory_id)
        return self._with_aggregate(
            file_id,
            lambda agg: self._add_chunk_to_aggregate(
                agg,
                file_id,
                memory_id,
                chunk_index,
                start_line,
                end_line,
            ),
            method="link_chunk",
        )

    def _add_chunk_to_aggregate(
        self,
        file_metadata: FileMetadataAggregate,
        file_id: str,
        memory_id: str,
        chunk_index: int,
        start_line: int | None,
        end_line: int | None,
    ) -> Result[FileChunk]:
        """Build a FileChunk via FileChunk.of(), add to aggregate, persist."""
        sl = start_line if start_line is not None else 0
        el = end_line if end_line is not None else 0

        chunk_result = FileChunk.of(
            {
                "id": f"fc_{file_id}_{memory_id}",
                "file_id": file_id,
                "memory_id": memory_id,
                "chunk_index": chunk_index,
                "start_line": sl,
                "end_line": el,
            }
        )
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
        description: str | None = None,
    ) -> Result[FileRelation]:
        """Create a file relation via the aggregate.

        Loads the aggregate for the source file, adds the relation,
        and persists the new relation entity.
        Emits FileRelationCreatedEvent on success.
        """
        self._log_info(
            "Creating relation", method="create_relation", source_file_id=source_file_id, target_file_id=target_file_id
        )
        return self._with_aggregate(
            source_file_id,
            lambda agg: self._add_relation_to_aggregate(
                agg,
                source_file_id,
                target_file_id,
                relation_type,
                strength,
                description,
            ),
            method="create_relation",
        )

    def _add_relation_to_aggregate(
        self,
        file_metadata: FileMetadataAggregate,
        source_file_id: str,
        target_file_id: str,
        relation_type: RelationType,
        strength: float,
        description: str | None,
    ) -> Result[FileRelation]:
        """Build a FileRelation via FileRelation.of(), add to aggregate, persist."""
        relation_result = FileRelation.of(
            {
                "id": f"fr_{source_file_id}_{target_file_id}",
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "relation_type": relation_type,
                "strength": strength,
                "description": description,
            }
        )
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
        relation_types: list[RelationType] | None = None,
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
        relation_types: list[RelationType] | None = None,
        method: str = "get_file",
    ) -> Result[FileMetadataAggregate]:
        """Build a FileMetadataAggregate from repository data."""
        file_result = self.file_repository.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])

        file = file_result.value

        chunks: list[FileChunk] = []
        if include_chunks:
            chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
            chunks = chunks_result.value if chunks_result.is_ok else []

        relations: list[FileRelation] = []
        if include_relations:
            relations_result = self.relation_repository.get_relations_by_file_id(file_id)
            relations = relations_result.value if relations_result.is_ok else []

        if relation_types:
            relations = [r for r in relations if r.relation_type in relation_types]

        self._log_debug(
            "Aggregate built", method=method, file_id=file_id, chunk_count=len(chunks), relation_count=len(relations)
        )
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

    def find_files_by_memory(self, memory_id: str) -> Result[list[File]]:
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
        return self._with_aggregate(
            file_id,
            lambda agg: self._remove_chunk_from_aggregate(
                agg,
                file_id,
                memory_id,
            ),
            method="remove_chunk",
        )

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
            return chunks_result  # type: ignore[return-value]
        return Result.ok(len(chunks_result.value))

    # ------------------------------------------------------------------
    # Materialization API (remember-as-materializer, spec §4.1 / §4.3)
    # ------------------------------------------------------------------

    def materialize_file_context(
        self,
        bank: str,
        context: FileContext,
        memory_id: str,
    ) -> Result[dict]:
        """Materialize a unified chunk contract v1 payload into the file layer.

        Order (spec §4.1): upsert File by deterministic id → link FileChunk →
        per edge: stub-upsert target File (D4) + create relation → rebuild
        projection when the stored file_hash differs from the incoming one
        (spec §4.3, D5). When file_hash is absent on either side the rebuild
        branch never fires — upsert-only, still idempotent on
        file_id + memory_id.

        All upserts use ON CONFLICT DO UPDATE semantics (the repository's
        merge() convention); replace-style deletes are forbidden (DEC-0018).
        Failures are collected into the Result — no exception escapes.
        """
        self._log_info(
            "Materializing file context",
            method="materialize_file_context",
            bank=bank,
            path=context.file_path,
            memory_id=memory_id,
        )
        errors: list[ErrorWithDetails] = []
        events: list[DomainEvent] = []
        file_id = derive_file_id(bank, context.file_path)

        # 1. Read the stored file BEFORE upserting (rebuild decision needs it).
        stored_result = self.file_repository.get_file_by_id(file_id)
        if stored_result.is_ko:
            errors.append(ErrorWithDetails("MATERIALIZE_FILE_READ_ERROR", stored_result.errors[0].details))
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        stored_file = stored_result.value

        # 2. Rebuild the projection when the whole-file hash changed (D5).
        #    Runs BEFORE upserting the new chunk/relations so stale chunks of
        #    this file and its outbound relations are pruned first.
        rebuilt = False
        if stored_file is not None and stored_file.hash is not None and context.file_hash != stored_file.hash:
            rebuild_result = self.rebuild_projection(file_id, {memory_id})
            if rebuild_result.is_ko:
                errors.extend(rebuild_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            rebuilt = True

        # 3. Upsert the File row (deterministic id; status → INDEXED).
        file_result = self._upsert_materialized_file(bank, context, stored_file)
        if file_result.is_ko:
            errors.extend(file_result.errors)
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        events.extend(file_result.events)

        # 4. Link the FileChunk (PK = file_id + memory_id).
        chunk_result = self._link_materialized_chunk(file_id, context, memory_id)
        if chunk_result.is_ko:
            errors.extend(chunk_result.errors)
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        events.extend(chunk_result.events)

        # 5. Per edge: stub-upsert the target File (D4), then create the relation.
        relations_created = 0
        for edge in context.edges_list or []:
            target_file_id = derive_file_id(bank, edge.target_path)
            stub_result = self._ensure_target_stub(bank, edge.target_path, target_file_id)
            if stub_result.is_ko:
                errors.extend(stub_result.errors)
                continue
            events.extend(stub_result.events)

            relation_result = self._create_materialized_relation(
                file_id, target_file_id, edge.relation_type, edge.strength, edge.description
            )
            if relation_result.is_ko:
                errors.extend(relation_result.errors)
                continue
            events.extend(relation_result.events)
            relations_created += 1

        payload = {
            "file_id": file_id,
            "relations_created": relations_created,
            "rebuilt": rebuilt,
            "errors": [e.error_code for e in errors],
        }
        if errors:
            self._log_info(
                "Materialization completed with errors",
                method="materialize_file_context",
                file_id=file_id,
                error_count=len(errors),
            )
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        return Result.ok(payload, events=events)

    def rebuild_projection(self, file_id: str, keep_memory_ids: set[str]) -> Result[None]:
        """Rebuild a file's projection after a content change (spec §4.3, D5).

        Prunes the stale chunks of THIS file whose memory_id is not in the
        keep-set and deletes this file's relations; the caller recreates them
        from the incoming contract edges. Live memories of other files are
        untouched by construction.
        """
        self._log_info(
            "Rebuilding projection",
            method="rebuild_projection",
            file_id=file_id,
            keep_memory_ids=sorted(keep_memory_ids),
        )
        chunks_result = self.chunk_repository.delete_chunks_by_file_id(file_id, keep_memory_ids)
        if chunks_result.is_ko:
            return Result.ko(chunks_result.errors)  # type: ignore[return-value]
        relations_result = self.relation_repository.delete_relations_by_file_id(file_id)
        if relations_result.is_ko:
            return relations_result  # type: ignore[return-value]
        return Result.ok(None)

    def get_relations_by_file_id(self, file_id: str) -> Result[list[FileRelation]]:
        """Passthrough to the relation repository (enrichment consumer)."""
        self._log_info("Getting relations by file id", method="get_relations_by_file_id", file_id=file_id)
        return self.relation_repository.get_relations_by_file_id(file_id)

    def get_file_by_id(self, file_id: str) -> Result[File | None]:
        """Passthrough to the file repository (enrichment consumer)."""
        self._log_info("Getting file by id", method="get_file_by_id", file_id=file_id)
        return self.file_repository.get_file_by_id(file_id)

    def get_chunks_by_file_id(self, file_id: str) -> Result[list[FileChunk]]:
        """Passthrough to the chunk repository (enrichment consumer)."""
        self._log_info("Getting chunks by file id", method="get_chunks_by_file_id", file_id=file_id)
        return self.chunk_repository.get_chunks_by_file_id(file_id)

    def get_chunk_by_memory_id(self, memory_id: str) -> Result[FileChunk | None]:
        """Passthrough to the chunk repository (enrichment consumer)."""
        self._log_info("Getting chunk by memory id", method="get_chunk_by_memory_id", memory_id=memory_id)
        return self.chunk_repository.get_chunk_by_memory_id(memory_id)

    def get_related_file_by_id(self, file_id: str) -> Result[File | None]:
        """Passthrough resolving a relation's other end (enrichment consumer)."""
        self._log_info("Getting related file by id", method="get_related_file_by_id", file_id=file_id)
        return self.file_repository.get_file_by_id(file_id)

    # ------------------------------------------------------------------
    # Materialization helpers
    # ------------------------------------------------------------------

    def _upsert_materialized_file(
        self,
        bank: str,
        context: FileContext,
        stored_file: File | None,
    ) -> Result[File]:
        """Upsert the File row from a materialized contract (ON CONFLICT DO UPDATE)."""
        file_id = derive_file_id(bank, context.file_path)

        if stored_file is not None:
            # Merge extra into metadata — last-writer-wins per key.
            merged_metadata = {**stored_file.metadata, **context.extra}
            update_result = stored_file.update_metadata(
                hash=context.file_hash,
                file_role=context.file_role,
                language=context.language,
                summary=context.summary,
                total_chunks=context.total_chunks,
                metadata=merged_metadata,
            )
            if update_result.is_ko:
                return update_result
            candidate = update_result.value
            assert candidate is not None
            # Status → INDEXED (upsert never downgrades an indexed file).
            if candidate.status != FileStatus.INDEXED:
                index_result = candidate.mark_indexed()
                if index_result.is_ko:
                    return index_result
                candidate = index_result.value
                assert candidate is not None
                events = update_result.events + index_result.events
            else:
                events = update_result.events
        else:
            file_data = {
                "id": file_id,
                "path": context.file_path,
                "source_type": context.source_type,
                "file_role": context.file_role,
                "hash": context.file_hash,
                "language": context.language,
                "summary": context.summary,
                "total_chunks": context.total_chunks,
                "metadata": dict(context.extra),
                "status": FileStatus.INDEXED,
            }
            file_result = File.of(file_data)
            if file_result.is_ko:
                return file_result
            candidate = file_result.value
            assert candidate is not None
            events = file_result.events

        save_result = self.file_repository.save_file(candidate)
        if save_result.is_ko:
            return save_result
        saved = save_result.value
        assert saved is not None
        return Result.ok(saved, events=events)

    def _link_materialized_chunk(
        self,
        file_id: str,
        context: FileContext,
        memory_id: str,
    ) -> Result[FileChunk]:
        """Link the incoming chunk (id derived from file_id + memory_id)."""
        parent_ref = context.parent_unit.ref if context.parent_unit else None
        parent_summary = context.parent_unit.summary if context.parent_unit else None

        chunk_result = FileChunk.of(
            {
                "id": f"fc_{file_id}_{memory_id}",
                "file_id": file_id,
                "memory_id": memory_id,
                "chunk_index": context.chunk_index,
                "start_line": context.start_line if context.start_line is not None else 0,
                "end_line": context.end_line if context.end_line is not None else 0,
                "content_type": ContentType.TEXT,
                "is_partial": False,
                "section_header": context.section_header,
                "parent_unit_ref": parent_ref,
                "parent_unit_summary": parent_summary,
                "content_hash": context.chunk_hash,
            }
        )
        if chunk_result.is_ko:
            return chunk_result
        chunk = chunk_result.value
        assert chunk is not None

        save_result = self.chunk_repository.save_chunk(chunk)
        if save_result.is_ko:
            return save_result
        saved = save_result.value
        assert saved is not None
        return Result.ok(saved, events=chunk_result.events)

    def _ensure_target_stub(self, bank: str, target_path: str, target_file_id: str) -> Result[File]:
        """Ensure the edge target has a File row (D4 dangling-edge policy).

        Missing targets get a minimal PENDING stub (source_type unknown);
        existing files are left untouched.
        """
        existing_result = self.file_repository.get_file_by_id(target_file_id)
        if existing_result.is_ko:
            return Result.ko(existing_result.errors)  # type: ignore[return-value]
        if existing_result.value is not None:
            return Result.ok(existing_result.value)

        stub_data = {
            "id": target_file_id,
            "path": target_path,
            "source_type": SourceType.UNKNOWN,
            "status": FileStatus.PENDING,
        }
        stub_result = File.of(stub_data)
        if stub_result.is_ko:
            return Result.ko(stub_result.errors)  # type: ignore[return-value]
        stub = stub_result.value
        assert stub is not None

        save_result = self.file_repository.save_file(stub)
        if save_result.is_ko:
            return Result.ko(save_result.errors)  # type: ignore[return-value]
        saved = save_result.value
        assert saved is not None
        return Result.ok(saved, events=stub_result.events)

    def _create_materialized_relation(
        self,
        source_file_id: str,
        target_file_id: str,
        relation_type: RelationType,
        strength: float,
        description: str | None,
    ) -> Result[FileRelation]:
        """Create (or upsert) a relation; id includes the type to avoid collisions."""
        relation_result = FileRelation.of(
            {
                "id": f"fr_{source_file_id}_{target_file_id}_{relation_type.value}",
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "relation_type": relation_type,
                "strength": strength,
                "direction": Direction.UNIDIRECTIONAL,
                "description": description,
            }
        )
        if relation_result.is_ko:
            return Result.ko(relation_result.errors)  # type: ignore[return-value]
        relation = relation_result.value
        assert relation is not None

        save_result = self.relation_repository.save_relation(relation)
        if save_result.is_ko:
            return Result.ko(save_result.errors)  # type: ignore[return-value]
        saved = save_result.value
        assert saved is not None
        return Result.ok(saved, events=relation_result.events)

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
        aggregate_result = self._build_aggregate(file_id, include_chunks=True, include_relations=True, method=method)
        if aggregate_result.is_ko:
            return aggregate_result

        self._log_debug("Aggregate loaded", method=method, file_id=file_id)
        return operation(aggregate_result.value)
