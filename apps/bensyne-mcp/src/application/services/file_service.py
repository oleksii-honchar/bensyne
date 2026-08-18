"""FileService — application service orchestrating the file metadata layer.

The file layer is a *projection* (an index) of the memory layer: content lives
in Mnemosyne; this layer stores only identity (path, ``file_hash``, source
metadata), the file→memory links (``file_chunks``), and the file↔file edges
(``file_relations``). ``rememberMemory`` is the sole producer — it materializes
(builds/refreshes) the projection through idempotent upserts on the
``FileMetadata`` aggregate, which is the sole write root. Read paths
(searchFiles / fetchFile / expandFileRelations / recallMemory) only read the
projection and never write it. ``forgetMemory`` is the inverse: a file that
loses its last chunk becomes a DELETED tombstone whose child rows cascade away
at the single ``_persist`` chokepoint. Canonical concept home: spec §2
(projection model) + the ``materialization`` vault concept node (D26).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import structlog.stdlib
from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.file_entity import File
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_relation_entity import FileRelation, RelationType
from src.domain.models.file_context_model import FileContext
from src.domain.models.file_model import FileStatus, SourceType
from src.domain.models.file_props import FileProps
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
    """Application service for file metadata operations — the file layer's sole write root.

    Every write is: load the ``FileMetadata`` aggregate → a domain mutation
    (invariants + events) → one ``_persist`` call. All operations return
    ``Result[T]``.

    Unified write surface (the only ways File / FileChunk / FileRelation rows
    change):
        materialize_file_context(bank, context, memory_id) — remember (the sole
            producer): upsert File (deterministic id) + the FileChunk row +
            FileRelation rows; idempotent (a silent no-op on re-remember).
        update_file(bank, file_id, props) — typed, file-only partial metadata
            update (``FileProps``); ``Result.ko`` when the file is absent (no
            implicit create on this path).
        remove_chunk(file_id, memory_id) — forget: drop one chunk row (+ the
            file's keyword/importance/total_chunks re-aggregation).
        delete_file(file_id) — forget: DELETED tombstone (child rows cascade
            away at ``_persist``).
        rebuild_projection(file_id, keep_memory_ids) — the one sanctioned
            direct-repo write: a bulk wipe of stale chunk/relation rows on a
            ``file_hash`` change (D5).

    Single ``_persist`` chokepoint: FK-safe order file row → chunk rows →
    relation rows; the ``write_chunks`` / ``write_relations`` flags mirror what
    the flow loaded, and a DELETED file's chunk/relation rows are pruned first
    (D20). Event policy: one domain event per fact (an idempotent no-op emits
    none).

    Memories are NOT stored locally by Bensyne — they live in Mnemosyne. Content
    composition lives in the aggregate (``compose_fetch`` / ``compose_content``);
    ``FetchFileUseCase`` loads through this service and passes ``mnemosyne.get``
    as the chunk-content fetcher. Read passthroughs (``get_file`` and the
    ``get_*_by_*`` methods) expose the projection to the enrichment and fetch
    use cases.
    """

    def __init__(
        self,
        file_repository: FileRepository,
        chunk_repository: FileChunkRepository,
        relation_repository: FileRelationRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self.file_repository = file_repository
        self.chunk_repository = chunk_repository
        self.relation_repository = relation_repository
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

    def update_file(
        self,
        bank: str,
        file_id: str,
        props: FileProps,
    ) -> Result[File]:
        """Typed, file-only partial metadata update (D18/D23, spec §5).

        Loads the file-only aggregate, applies ``file.update_metadata(**props)``
        (destructuring — the Pydantic ``FileSchema`` remains the runtime
        validator), and persists the file row only. Chunk/relation rows stay
        byte-identical (spec §6.1). File absent ⇒ Result.ko — no implicit
        create on this path (creation is materialization's job; a bare-props
        create would fabricate identity). ``bank`` scopes the per-bank
        repositories; it is carried for API symmetry with
        ``materialize_file_context`` and for audit logging.
        """
        self._log_info("Updating file", method="update_file", bank=bank, file_id=file_id)

        aggregate_result = self._load_aggregate(
            file_id, include_chunks=False, include_relations=False, method="update_file"
        )
        if aggregate_result.is_ko:
            return aggregate_result

        file = aggregate_result.value.file
        updated_file_result = file.update_metadata(**props)
        if updated_file_result.is_ko:
            return updated_file_result

        # File-only flow: neither child collection was loaded, so neither is
        # written — chunk/relation rows stay byte-identical (spec §6.1).
        persist_result = self._persist(
            FileMetadata(file=updated_file_result.value, chunks=[], relations=[]),
            write_chunks=False,
            write_relations=False,
        )
        if persist_result.is_ko:
            return persist_result
        # Propagate events from update_metadata
        if updated_file_result.has_events():
            return Result.ok(persist_result.value, events=updated_file_result.events)
        return persist_result

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

        # Forget symmetry is the DELETED cascade (D20, spec §6.3): marking the
        # file DELETED and persisting it prunes this file's chunk rows AND its
        # relation rows (source OR target) at the _persist chokepoint, then
        # saves the tombstone. No explicit relation-prune lives here — the
        # cascade supersedes it. The write flags are vestigial on the DELETED
        # path (the cascade is status-driven); relations between other
        # (non-deleted) files are untouched by design.
        persist_result = self._persist(
            FileMetadata(file=deleted_file_result.value, chunks=[], relations=[]),
            write_chunks=False,
            write_relations=True,
        )
        if persist_result.is_ko:
            return persist_result

        # Propagate events from mark_deleted
        if deleted_file_result.has_events():
            return Result.ok(persist_result.value, events=deleted_file_result.events)
        return persist_result

    # ------------------------------------------------------------------
    # Aggregate queries
    # ------------------------------------------------------------------

    def get_file(
        self,
        file_id: str,
        include_chunks: bool = True,
        include_relations: bool = True,
        relation_types: list[RelationType] | None = None,
    ) -> Result[FileMetadata]:
        """Retrieve file with configurable chunks and relations as an aggregate.

        Args:
            file_id: The file identifier.
            include_chunks: Whether to load chunks from the repository.
            include_relations: Whether to load relations from the repository.
            relation_types: Optional filter for relation types (only applied
                when include_relations is True).
        """
        self._log_info("Getting file", method="get_file", file_id=file_id)
        aggregate_result = self._load_aggregate(
            file_id,
            include_chunks=include_chunks,
            include_relations=include_relations,
            method="get_file",
        )
        if aggregate_result.is_ko:
            return aggregate_result

        aggregate = aggregate_result.value
        if relation_types:
            aggregate = FileMetadata(
                file=aggregate.file,
                chunks=aggregate.chunks,
                relations=[r for r in aggregate.relations if r.relation_type in relation_types],
            )
        return Result.ok(aggregate)

    def _load_aggregate(
        self,
        file_id: str,
        include_chunks: bool = True,
        include_relations: bool = True,
        method: str = "load_aggregate",
    ) -> Result[FileMetadata]:
        """Load the FileMetadata aggregate — one repository query per requested collection.

        Read half of the persistence contract (spec §3.2): the write flags
        later passed to _persist mirror these load flags, so a flow never
        writes rows it did not load.
        """
        file_result = self.file_repository.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])

        file = file_result.value

        chunks: list[FileChunk] = []
        if include_chunks:
            chunks_result = self.chunk_repository.get_chunks_by_file_id(file_id)
            if chunks_result.is_ko:
                return chunks_result
            chunks = chunks_result.value

        relations: list[FileRelation] = []
        if include_relations:
            relations_result = self.relation_repository.get_relations_by_file_id(file_id)
            if relations_result.is_ko:
                return relations_result
            relations = relations_result.value

        self._log_debug(
            "Aggregate built", method=method, file_id=file_id, chunk_count=len(chunks), relation_count=len(relations)
        )
        return FileMetadata.of(file, chunks=chunks, relations=relations)

    # ------------------------------------------------------------------
    # Chunk removal and count
    # ------------------------------------------------------------------

    def remove_chunk(self, file_id: str, memory_id: str) -> Result[FileMetadata]:
        """Remove a chunk from a file by memory_id via the aggregate.

        Loads the aggregate, calls aggregate.remove_chunk(memory_id),
        persists the updated file and removes the chunk from the repository.
        Returns the updated aggregate on success.
        """
        self._log_info("Removing chunk", method="remove_chunk", file_id=file_id, memory_id=memory_id)
        aggregate_result = self._load_aggregate(file_id, include_chunks=True, include_relations=True)
        if aggregate_result.is_ko:
            return aggregate_result
        self._log_debug("Aggregate loaded", method="remove_chunk", file_id=file_id)
        return self._remove_chunk_from_aggregate(aggregate_result.value, memory_id)

    def _remove_chunk_from_aggregate(
        self,
        file_metadata: FileMetadata,
        memory_id: str,
    ) -> Result[FileMetadata]:
        """Remove chunk from aggregate, then persist through _persist.

        The keep-set prune inside _persist drops the removed chunk's row
        (its memory_id is no longer in the aggregate); surviving rows are
        re-saved unchanged.
        """
        remove_result = file_metadata.remove_chunk(memory_id)
        if remove_result.is_ko:
            return remove_result

        persist_result = self._persist(remove_result.value, write_chunks=True, write_relations=True)
        if persist_result.is_ko:
            return persist_result

        return Result.ok(remove_result.value, events=remove_result.events)

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
        per edge: stub-upsert target File (D4) + upsert relation → rebuild
        projection when the stored file_hash differs from the incoming one
        (spec §4.3, D5). When file_hash is absent on either side the rebuild
        branch never fires — upsert-only, still idempotent on
        file_id + memory_id.

        The file row is mutated via the FileMetadata aggregate (D19): fresh
        files use File.of (status=INDEXED, tags from context); existing files
        are loaded and mutated in place (mark_indexed → update_metadata →
        merge_tags). Chunks and relations are upserted through the aggregate's
        upsert_chunk / upsert_relation (D19a / D19b), which are event-silent
        on idempotent re-materialization (D14). All writes flow through the
        single _persist chokepoint — no direct repository saves in this body.
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

        # 1. Read the stored file BEFORE upserting (rebuild decision + fresh-vs-existing).
        stored_result = self.file_repository.get_file_by_id(file_id)
        if stored_result.is_ko:
            errors.append(ErrorWithDetails("MATERIALIZE_FILE_READ_ERROR", stored_result.errors[0].details))
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        stored_file = stored_result.value

        # 2. Rebuild the projection when the whole-file hash changed (D5).
        #    Runs BEFORE loading the aggregate so stale chunks of this file
        #    and its outbound relations are pruned first.
        rebuilt = False
        if stored_file is not None and stored_file.hash is not None and context.file_hash != stored_file.hash:
            rebuild_result = self.rebuild_projection(file_id, {memory_id})
            if rebuild_result.is_ko:
                errors.extend(rebuild_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            rebuilt = True

        # 3. Build or mutate the File aggregate.
        if stored_file is None:
            # Fresh file: File.of with status=INDEXED, tags from context.
            # total_chunks is projection state — it is re-aggregated from the
            # real chunk set after the upsert below (never copied from the
            # producer's contract claim; spec §2.2).
            file_data = {
                "id": file_id,
                "path": context.file_path,
                "source_type": context.source_type,
                "file_role": context.file_role,
                "hash": context.file_hash,
                "language": context.language,
                "summary": context.summary,
                "total_chunks": 0,
                "metadata": dict(context.extra),
                "status": FileStatus.INDEXED,
                "aggregated_tags": context.tags_list,
            }
            file_result = File.of(file_data)
            if file_result.is_ko:
                errors.extend(file_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            file = file_result.value
            events.extend(file_result.events)
            chunks: list[FileChunk] = []
            relations: list[FileRelation] = []
        else:
            # Existing file: load full aggregate, then mutate in place.
            agg_result = self._load_aggregate(
                file_id, include_chunks=True, include_relations=True,
                method="materialize_file_context",
            )
            if agg_result.is_ko:
                errors.extend(agg_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            aggregate_loaded = agg_result.value
            file = aggregate_loaded.file

            # 3a. Resurrect DELETED → INDEXED (D21), or mark PENDING → INDEXED.
            if file.status != FileStatus.INDEXED:
                index_result = file.mark_indexed()
                if index_result.is_ko:
                    errors.extend(index_result.errors)
                    return Result.ko(errors, events=events)  # type: ignore[return-value]
                file = index_result.value
                events.extend(index_result.events)

            # 3b. Update metadata (hash, role, language, summary, merged
            #     metadata). No-op (zero events) when nothing changed.
            #     total_chunks is NOT touched here — it is re-aggregated from
            #     the real chunk set after the upsert below (spec §2.2).
            merged_metadata = {**file.metadata, **context.extra}
            update_result = file.update_metadata(
                hash=context.file_hash,
                file_role=context.file_role,
                language=context.language,
                summary=context.summary,
                metadata=merged_metadata,
            )
            if update_result.is_ko:
                errors.extend(update_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            file = update_result.value
            events.extend(update_result.events)

            # 3c. Tags union-merge (O5). No-op (zero events) when union == current.
            tags_result = file.merge_tags(context.tags_list)
            if tags_result.is_ko:
                errors.extend(tags_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            file = tags_result.value
            events.extend(tags_result.events)

            chunks = aggregate_loaded.chunks
            relations = aggregate_loaded.relations

        # 4. Upsert the chunk into the aggregate (D19a).
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
            errors.extend(chunk_result.errors)
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        chunk = chunk_result.value

        aggregate = FileMetadata(file=file, chunks=chunks, relations=relations)
        upsert_chunk_result = aggregate.upsert_chunk(chunk)
        if upsert_chunk_result.is_ko:
            errors.extend(upsert_chunk_result.errors)
            return Result.ko(errors, events=events)  # type: ignore[return-value]
        aggregate = upsert_chunk_result.value
        events.extend(upsert_chunk_result.events)

        # 4b. total_chunks is projection state — re-aggregate it from the file's
        #     actual chunk set (the source of truth), never the producer's
        #     contract claim. After the upsert (and any rebuild before it), the
        #     aggregate's chunk list IS the persisted set, so its length is
        #     authoritative (spec §2.2, DDD).
        actual_total = len(aggregate.chunks)
        if aggregate.file.total_chunks != actual_total:
            recompute_result = aggregate.file.update_metadata(total_chunks=actual_total)
            if recompute_result.is_ko:
                errors.extend(recompute_result.errors)
                return Result.ko(errors, events=events)  # type: ignore[return-value]
            aggregate = FileMetadata(
                file=recompute_result.value,
                chunks=aggregate.chunks,
                relations=aggregate.relations,
            )
            events.extend(recompute_result.events)

        # 5. Per edge: stub-upsert target File (D4), then upsert relation (D19b).
        relations_created = 0
        for edge in context.edges_list or []:
            target_file_id = derive_file_id(bank, edge.target_path)

            # Stub-upsert: missing targets get a PENDING stub (D4).
            stub_read = self.file_repository.get_file_by_id(target_file_id)
            if stub_read.is_ko:
                errors.extend(stub_read.errors)
                continue
            if stub_read.value is None:
                stub_data = {
                    "id": target_file_id,
                    "path": edge.target_path,
                    "source_type": SourceType.UNKNOWN,
                    "status": FileStatus.PENDING,
                }
                stub_file_result = File.of(stub_data)
                if stub_file_result.is_ko:
                    errors.extend(stub_file_result.errors)
                    continue
                stub_persist = self._persist(
                    FileMetadata(file=stub_file_result.value, chunks=[], relations=[]),
                    write_chunks=False,
                    write_relations=False,
                )
                if stub_persist.is_ko:
                    errors.extend(stub_persist.errors)
                    continue
                events.extend(stub_file_result.events)

            # Upsert the relation into the aggregate (D19b).
            relation_result = FileRelation.of(
                {
                    "id": f"fr_{file_id}_{target_file_id}_{edge.relation_type.value}",
                    "source_file_id": file_id,
                    "target_file_id": target_file_id,
                    "relation_type": edge.relation_type,
                    "strength": edge.strength,
                    "description": edge.description,
                }
            )
            if relation_result.is_ko:
                errors.extend(relation_result.errors)
                continue
            relation = relation_result.value

            upsert_rel_result = aggregate.upsert_relation(relation)
            if upsert_rel_result.is_ko:
                errors.extend(upsert_rel_result.errors)
                continue
            aggregate = upsert_rel_result.value
            events.extend(upsert_rel_result.events)
            relations_created += 1

        # 6. Single _persist chokepoint for the source file (file → chunks → relations).
        persist_result = self._persist(
            aggregate,
            write_chunks=True,
            write_relations=True,
        )
        if persist_result.is_ko:
            errors.extend(persist_result.errors)
            return Result.ko(errors, events=events)  # type: ignore[return-value]

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

    def get_chunks_by_memory_id(self, memory_id: str) -> Result[list[FileChunk]]:
        """Passthrough to the chunk repository (forget cleanup consumer).

        Plural form: a memory_id may back a chunk row in more than one file,
        so the forget flow resolves ALL of them and cleans each file up.
        """
        self._log_info("Getting chunks by memory id", method="get_chunks_by_memory_id", memory_id=memory_id)
        return self.chunk_repository.get_chunks_by_memory_id(memory_id)

    def get_related_file_by_id(self, file_id: str) -> Result[File | None]:
        """Passthrough resolving a relation's other end (enrichment consumer)."""
        self._log_info("Getting related file by id", method="get_related_file_by_id", file_id=file_id)
        return self.file_repository.get_file_by_id(file_id)

    # ------------------------------------------------------------------
    # Persistence contract (spec §3.2 / §6.1 / §6.2)
    # ------------------------------------------------------------------

    def _persist(
        self,
        file_metadata: FileMetadata,
        write_chunks: bool,
        write_relations: bool,
    ) -> Result[File]:
        """Single write chokepoint for non-materialize flows (spec §3.2 / §6.1).

        FK-safe order: file row → chunk rows → relation rows. The write
        flags mirror what the flow loaded via _load_aggregate — a file-only
        flow never writes child rows, and a loaded collection is always
        re-persisted in full (idempotent merge upserts).

        DELETED cascade (D20, spec §6.3): when the root file is DELETED the
        persist prunes this file's chunk rows AND its relation rows (as source
        OR target) FIRST, then saves the tombstone. Status-driven, single
        location — any future path that persists a DELETED file prunes
        automatically, and the write flags are deliberately ignored here
        (forget symmetry no longer depends on a call-site remembering to
        clean up). Legacy fr_{source}_{target} relation ids converge to the
        canonical fr_{source}_{target}_{type} id for non-DELETED persists
        (spec §6.2) — self-healing, no migration.
        """
        file = file_metadata.file

        if file.status == FileStatus.DELETED:
            return self._persist_deleted_cascade(file)

        file_save_result = self.file_repository.save_file(file)
        if file_save_result.is_ko:
            return file_save_result

        if write_chunks:
            chunks_result = self._persist_chunks(file, file_metadata.chunks)
            if chunks_result.is_ko:
                return chunks_result

        if write_relations:
            relations_result = self._persist_relations(file, file_metadata.relations)
            if relations_result.is_ko:
                return relations_result

        return file_save_result

    def _persist_deleted_cascade(self, file: File) -> Result[File]:
        """DELETED cascade (D20, spec §6.3): prune child rows, then tombstone.

        Deletes this file's ``file_chunks`` rows (empty keep-set) and its
        ``file_relations`` rows (source OR target) BEFORE saving the DELETED
        file row, so the tombstone never outlives its child rows. Returns the
        saved tombstone on success.
        """
        chunk_prune = self.chunk_repository.delete_chunks_by_file_id(file.id, set())
        if chunk_prune.is_ko:
            return chunk_prune

        relation_prune = self.relation_repository.delete_relations_by_file_id(file.id)
        if relation_prune.is_ko:
            return relation_prune

        return self.file_repository.save_file(file)

    def _persist_chunks(self, file: File, chunks: list[FileChunk]) -> Result[None]:
        """Write the file's chunk rows.

        Prunes rows whose memory_id is absent from the aggregate (keep-set
        prune), then upserts every aggregate chunk. Re-saving an unchanged
        loaded chunk is byte-stable: the merge upsert writes the entity's
        own field values, including its timestamps.
        """
        keep_memory_ids = {chunk.memory_id for chunk in chunks}
        prune_result = self.chunk_repository.delete_chunks_by_file_id(file.id, keep_memory_ids)
        if prune_result.is_ko:
            return prune_result
        for chunk in chunks:
            save_result = self.chunk_repository.save_chunk(chunk)
            if save_result.is_ko:
                return save_result
        return Result.ok(None)

    def _persist_relations(self, file: File, relations: list[FileRelation]) -> Result[None]:
        """Write a non-DELETED file's relation rows (spec §6.2).

        Each relation is upserted under its canonical
        fr_{source}_{target}_{type} id. A relation still carrying a legacy
        fr_{source}_{target} id has the stored row for the pair deleted
        first (by id), so the pair never holds both a legacy and a
        canonical row. The DELETED cascade lives in _persist (D20) — this
        method only runs for non-DELETED files.
        """
        for relation in relations:
            canonical_id = (
                f"fr_{relation.source_file_id}_{relation.target_file_id}"
                f"_{relation.relation_type.value}"
            )
            if relation.id != canonical_id:
                stored = self.relation_repository.get_by_pair(
                    relation.source_file_id,
                    relation.target_file_id,
                    relation.relation_type,
                )
                if stored.is_ko:
                    return stored
                legacy_ids = {relation.id}
                if stored.value is not None and stored.value.id != canonical_id:
                    legacy_ids.add(stored.value.id)
                for legacy_id in legacy_ids:
                    delete_result = self.relation_repository.delete_relation(legacy_id)
                    if delete_result.is_ko:
                        return delete_result
                relation = replace(relation, id=canonical_id)
            save_result = self.relation_repository.save_relation(relation)
            if save_result.is_ko:
                return save_result
        return Result.ok(None)
